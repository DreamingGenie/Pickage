package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.*;
import com.ssafy.pickage.domain.community.dto.*;
import com.ssafy.pickage.domain.community.payload.*;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.*;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/** 검증→수집→제한된 요약→검증→원자 게시. source 원문은 run의 지역 변수로만 보유한다. */
public class CommunityRefreshOrchestrator {
    private static final Logger log = LoggerFactory.getLogger(CommunityRefreshOrchestrator.class);
    private final RepositoryVerificationService verification;
    private final IssueCollectionService collection;
    private final CommunityHighlightSummarizer summarizer;
    private final CommunitySnapshotPublisher publisher;

    public CommunityRefreshOrchestrator(
            RepositoryVerificationService verification,
            IssueCollectionService collection,
            CommunityHighlightSummarizer summarizer,
            CommunitySnapshotPublisher publisher) {
        this.verification = verification;
        this.collection = collection;
        this.summarizer = summarizer;
        this.publisher = publisher;
    }

    public void run(RefreshTask task, String name, int packageId, String dbRepoUrl) {
        try {
            task.requirePublishable();
            if (task.collectionTimeLeft().isZero()) {
                fail(task, CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, null);
                return;
            }
            task.advanceStage(RefreshStage.REPOSITORY_VERIFY);
            var verified = verification.verify(name, dbRepoUrl, task.collectionTimeLeft());
            if (verified instanceof RepositoryVerificationResult.FetchLimited limited) {
                fail(task, classify(limited.reason(), limited.retryAt(), task), limited.retryAt());
                return;
            }
            if (!(verified instanceof RepositoryVerificationResult.Verified v)) {
                DataStatus status =
                        verified instanceof RepositoryVerificationResult.UnsupportedHost
                                ? DataStatus.UNSUPPORTED_HOST
                                : verified instanceof RepositoryVerificationResult.AmbiguousScope
                                        ? DataStatus.AMBIGUOUS_SCOPE
                                        : DataStatus.UNVERIFIED_REPOSITORY;
                publish(
                        task,
                        packageId,
                        new CommunityResultPayload(
                                null, CommunityPolicy.VERSION, 180, null, List.of(), List.of()),
                        status);
                return;
            }
            var repository =
                    new RepositoryPayload(
                            v.owner(),
                            v.repo(),
                            v.owner() + "/" + v.repo(),
                            v.scope().name(),
                            v.repositoryArchived());
            task.advanceStage(RefreshStage.ISSUE_SEARCH);
            var collected =
                    collection.collect(
                            v.owner(),
                            v.repo(),
                            task.collectionTimeLeft(),
                            () -> task.advanceStage(RefreshStage.COMMENTS));
            if (collected instanceof IssueCollectionResult.FetchLimited limited) {
                fail(task, classify(limited.reason(), limited.retryAt(), task), limited.retryAt());
                return;
            }
            var limitations = new ArrayList<>(v.limitations());
            if (collected instanceof IssueCollectionResult.NoDiscussionData empty) {
                empty.limitations()
                        .forEach(c -> limitations.add(CommunityPolicy.limitation(c, null)));
                publish(
                        task,
                        packageId,
                        new CommunityResultPayload(
                                repository,
                                CommunityPolicy.VERSION,
                                empty.lookbackDays(),
                                null,
                                List.of(),
                                limitations),
                        DataStatus.NO_DISCUSSION_DATA);
                return;
            }
            var success = (IssueCollectionResult.Success) collected;
            success.limitations()
                    .forEach(c -> limitations.add(CommunityPolicy.limitation(c, null)));
            record PendingTopic(CollectedIssue issue, CommunitySummarySourceBundle sources) {}
            var pending = new ArrayList<PendingTopic>();
            for (var issue : success.topics()) {
                var sources = CommunitySummarySourceBundle.highlights(issue);
                if (sources.limited())
                    limitations.add(
                            CommunityPolicy.limitation(
                                    "SUMMARY_INPUT_LIMITED", issue.issueNumber()));
                pending.add(new PendingTopic(issue, sources));
            }

            // 이슈별 GMS 호출을 동시에 디스패치한다(S15P21A506-368 후속) — 순차로 돌면 이슈1이
            // 시간을 다 쓰고 이슈2는 시작하자마자 예산이 바닥나는 문제가 실제로 재현됐다. 남은
            // 예산은 디스패치 시점에 한 번만 읽어 두 호출이 같은 창을 공정하게 나눠 쓰게 한다.
            task.advanceStage(RefreshStage.GMS);
            var budget = task.collectionTimeLeft();
            var futures =
                    pending.stream().map(p -> summarizer.summarizeAsync(p.issue(), budget)).toList();
            var attempts = futures.stream().map(CompletableFuture::join).toList();

            task.advanceStage(RefreshStage.VALIDATING);
            var topics = new ArrayList<TopicPayload>();
            for (int i = 0; i < pending.size(); i++) {
                var issue = pending.get(i).issue();
                var attempt = attempts.get(i);
                var summary = CommunitySummaryValidator.validate(attempt.bundle(), attempt.raw());
                if (summary.status() == SummaryStatus.FAILED)
                    limitations.add(
                            CommunityPolicy.limitation("SUMMARY_UNAVAILABLE", issue.issueNumber()));
                issue.limitations()
                        .forEach(
                                c ->
                                        limitations.add(
                                                CommunityPolicy.limitation(
                                                        c, issue.issueNumber())));
                String title = issue.title();
                if (title.codePointCount(0, title.length()) > 200)
                    title = CommunitySummarySourceBundle.clip(title, 199) + "…";
                topics.add(
                        new TopicPayload(
                                issue.sourceIssueId(),
                                issue.issueNumber(),
                                issue.state().toUpperCase(Locale.ROOT),
                                issue.updatedAt(),
                                issue.createdAt(),
                                title,
                                summary.titleKo(),
                                issue.totalCommentCount(),
                                issue.reactionCount(),
                                issue.collectionStatus().name(),
                                summary.status().name(),
                                summary.summaryKo(),
                                summary.messages(),
                                summary.summaryMarks()));
            }
            Instant retry =
                    CommunityPolicy.summaryStatus(topics) == SummaryStatus.FAILED
                            ? Instant.now().plus(CommunityProperties.FAILURE_COOLDOWN)
                            : null;
            var payload =
                    new CommunityResultPayload(
                            repository,
                            CommunityPolicy.VERSION,
                            success.lookbackDays(),
                            retry,
                            topics,
                            limitations.stream().distinct().toList());
            publish(
                    task,
                    packageId,
                    payload,
                    CommunityPolicy.incompleteData(limitations)
                            ? DataStatus.PARTIAL
                            : DataStatus.AVAILABLE);
        } catch (RuntimeException e) {
            fail(
                    task,
                    task.isPastDeadline()
                            ? CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED
                            : CommunityErrorCode.GITHUB_UNAVAILABLE,
                    null);
        }
    }

    private void publish(
            RefreshTask task, int packageId, CommunityResultPayload payload, DataStatus status) {
        try {
            task.advanceStage(RefreshStage.PUBLISHING);
            var snapshot = task.snapshot();
            var row =
                    new CommunitySnapshotRow(
                            packageId,
                            snapshot.refreshId(),
                            CommunityPolicy.PAYLOAD_VERSION,
                            snapshot.startedAt(),
                            status,
                            payload);
            CommunitySnapshotValidator.validate(row);
            publisher.publish(row, task);
        } catch (RuntimeException e) {
            fail(
                    task,
                    task.isPastDeadline()
                            ? CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED
                            : CommunityErrorCode.PUBLISH_FAILED,
                    null);
        }
    }

    private void fail(RefreshTask task, CommunityErrorCode code, Instant externalRetry) {
        Instant retry = Instant.now().plus(CommunityProperties.FAILURE_COOLDOWN);
        if (externalRetry != null && externalRetry.isAfter(retry)) retry = externalRetry;
        task.markFailed(code, retry);
        log.warn(
                "community refresh failed: refreshId={}, packageId={}, code={}",
                task.snapshot().refreshId(),
                task.packageId(),
                code);
    }

    private CommunityErrorCode classify(String reason, Instant retry, RefreshTask task) {
        if (retry != null) return CommunityErrorCode.GITHUB_RATE_LIMITED;
        if (task.collectionTimeLeft().isZero() || (reason != null && reason.contains("시간 예산")))
            return CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED;
        return reason != null && reason.contains("npm")
                ? CommunityErrorCode.NPM_UNAVAILABLE
                : CommunityErrorCode.GITHUB_UNAVAILABLE;
    }
}
