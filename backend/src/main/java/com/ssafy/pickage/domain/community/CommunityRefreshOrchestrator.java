package com.ssafy.pickage.domain.community;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.collection.IssueCollectionService;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;
import com.ssafy.pickage.domain.community.payload.RepositoryPayload;
import com.ssafy.pickage.domain.community.payload.TopicPayload;
import com.ssafy.pickage.domain.community.refresh.RefreshStage;
import com.ssafy.pickage.domain.community.refresh.RefreshTask;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * Spec §3.3 그대로 213 → 212 → (fake) GMS → 314 순서를 실행하는 작업 본체.
 * {@link com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator}가 넘긴
 * worker 스레드 안에서 {@link #run}이 통째로 돈다 — task의 {@link RefreshTask#timeLeft()}가
 * 그 스레드가 쓸 수 있는 남은 예산이다.
 *
 * <p><b>일시적 실패는 314에 아무것도 쓰지 않는다</b>(구현계획 "일시적 실패는 DB 결과를
 * 덮어쓰지 않는다") — {@link #fail}만 호출하고 {@link #publish}는 부르지 않는다. 반대로
 * 213/212가 <b>확정적으로</b> 분류한 결과(저장소 미확인·범위 모호·미지원 host·논의 없음·
 * 부분/전체 성공)는 전부 실제 게시 대상이다 — "결과가 있다"는 뜻이지 "성공"이라는 뜻이
 * 아니다.
 *
 * <h2>알려진 단순화 (완료 기록에도 남긴다)</h2>
 * <ul>
 *   <li>{@link RefreshStage#ISSUE_SEARCH}를 실제로 쓰지 않는다 — 212의
 *       {@code IssueCollectionService.collect()}가 검색과 댓글 수집을 한 호출로 묶어 두어
 *       그 안의 경계를 이 Phase가 관찰할 수 없다. {@link RefreshStage#COMMENTS} 하나로
 *       두 활동을 함께 나타낸다.</li>
 *   <li>{@code lookbackDays}는 항상 180으로 기록한다 — 212의 공개 계약({@link IssueCollectionResult})이
 *       365일 확장 여부를 노출하지 않고, 이 값은 API 응답에도 없는 저장 전용 감사 필드라
 *       213/212 파일을 고치지 않는 이번 Phase 제약 안에서는 정확히 복원할 수 없다.</li>
 *   <li>213/212의 {@code FetchLimited.reason()}은 자유 텍스트라 {@link CommunityErrorCode}로
 *       정확히 분류할 표준 필드가 없다 — {@code retryAt} 유무(rate limit 전용 신호)와 일부
 *       문자열만으로 최선을 다해 분류한다({@link #classify}).</li>
 * </ul>
 */
@Slf4j
@RequiredArgsConstructor
public class CommunityRefreshOrchestrator {

	private static final int LOOKBACK_DAYS_RECORDED = 180;
	private static final int POLICY_VERSION = 1;
	private static final short PAYLOAD_VERSION = 1;

	private final RepositoryVerificationService verificationService;
	private final IssueCollectionService collectionService;
	private final CommunitySummarizer summarizer;
	private final CommunitySnapshotRepository snapshotRepository;

	public void run(RefreshTask task, String packageName, int packageId, String dbRepoUrl) {
		try {
			task.advanceStage(RefreshStage.REPOSITORY_VERIFY);
			RepositoryVerificationResult verification = verificationService.verify(packageName, dbRepoUrl);
			handleVerification(task, packageId, verification);
		} catch (RuntimeException e) {
			log.error("커뮤니티 refresh 처리 중 예상하지 못한 예외: packageId={}", packageId, e);
			fail(task, CommunityErrorCode.GITHUB_UNAVAILABLE, null);
		}
	}

	private void handleVerification(RefreshTask task, int packageId, RepositoryVerificationResult verification) {
		if (verification instanceof RepositoryVerificationResult.FetchLimited limited) {
			fail(task, classify(limited.reason(), limited.retryAt()), limited.retryAt());
			return;
		}
		if (verification instanceof RepositoryVerificationResult.UnverifiedRepository) {
			publishTerminal(task, packageId, null, DataStatus.UNVERIFIED_REPOSITORY, List.of(), List.of());
			return;
		}
		if (verification instanceof RepositoryVerificationResult.UnsupportedHost) {
			publishTerminal(task, packageId, null, DataStatus.UNSUPPORTED_HOST, List.of(), List.of());
			return;
		}
		if (verification instanceof RepositoryVerificationResult.AmbiguousScope ambiguous) {
			RepositoryPayload repository = new RepositoryPayload(
				ambiguous.owner() + "/" + ambiguous.repo(), "AMBIGUOUS_SCOPE");
			publishTerminal(task, packageId, repository, DataStatus.AMBIGUOUS_SCOPE, List.of(), List.of());
			return;
		}

		RepositoryVerificationResult.Verified verified = (RepositoryVerificationResult.Verified) verification;
		collectIssues(task, packageId, verified);
	}

	private void collectIssues(RefreshTask task, int packageId, RepositoryVerificationResult.Verified verified) {
		RepositoryPayload repository = new RepositoryPayload(
			verified.owner() + "/" + verified.repo(), verified.scope().name());

		List<String> scopeLimitations = new ArrayList<>();
		if (verified.scopeLimited()) {
			scopeLimitations.add("REPOSITORY_WIDE");
		}
		if (verified.repositoryArchived()) {
			scopeLimitations.add("ARCHIVED");
		}

		if (task.timeLeft().isZero()) {
			fail(task, CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, null);
			return;
		}

		task.advanceStage(RefreshStage.COMMENTS);
		IssueCollectionResult collection =
			collectionService.collect(verified.owner(), verified.repo(), task.timeLeft());

		if (collection instanceof IssueCollectionResult.FetchLimited limited) {
			fail(task, classify(limited.reason(), limited.retryAt()), limited.retryAt());
			return;
		}
		if (collection instanceof IssueCollectionResult.NoDiscussionData) {
			publishTerminal(task, packageId, repository, DataStatus.NO_DISCUSSION_DATA, List.of(), scopeLimitations);
			return;
		}

		IssueCollectionResult.Success success = (IssueCollectionResult.Success) collection;
		summarizeAndPublish(task, packageId, repository, scopeLimitations, success);
	}

	private void summarizeAndPublish(RefreshTask task, int packageId, RepositoryPayload repository,
			List<String> scopeLimitations, IssueCollectionResult.Success success) {
		task.advanceStage(RefreshStage.GMS);

		List<TopicPayload> topics = new ArrayList<>();
		List<String> limitations = new ArrayList<>(scopeLimitations);
		limitations.addAll(success.limitations());
		boolean anySummaryFailed = false;

		for (CollectedIssue issue : success.topics()) {
			TopicSummary summary = summarizeSafely(issue);
			topics.add(new TopicPayload(
				issue.issueNumber(), issue.state().toUpperCase(Locale.ROOT), issue.updatedAt(), issue.title(),
				summary.titleKo(),
				issue.totalCommentCount(), issue.reactionCount(),
				issue.collectionStatus().name(), summary.status().name(), summary.summaryKo(),
				summary.discussionFlow(), summary.messages()));
			limitations.addAll(issue.limitations());
			anySummaryFailed |= summary.status() == SummaryStatus.FAILED;
		}

		DataStatus dataStatus = limitations.isEmpty() ? DataStatus.AVAILABLE : DataStatus.PARTIAL;
		Instant summaryRetryAt = anySummaryFailed
			? Instant.now().plus(CommunityProperties.FAILURE_COOLDOWN)
			: null;

		task.advanceStage(RefreshStage.PUBLISHING);
		publish(task, packageId, repository, dataStatus, topics, limitations, summaryRetryAt);
	}

	/** GMS 실패는 이 이슈 하나만 SKIPPED로 두고 나머지는 계속 진행한다(topic 단위 격리). */
	private TopicSummary summarizeSafely(CollectedIssue issue) {
		try {
			return summarizer.summarize(issue);
		} catch (RuntimeException e) {
			log.warn("이슈 요약 실패: issue={}, cause={}", issue.issueNumber(), e.getMessage());
			return new TopicSummary(null, null, List.of(), List.of(), SummaryStatus.FAILED);
		}
	}

	private void publishTerminal(RefreshTask task, int packageId, RepositoryPayload repository,
			DataStatus dataStatus, List<TopicPayload> topics, List<String> limitations) {
		publish(task, packageId, repository, dataStatus, topics, limitations, null);
	}

	private void publish(RefreshTask task, int packageId, RepositoryPayload repository, DataStatus dataStatus,
			List<TopicPayload> topics, List<String> limitations, Instant summaryRetryAt) {
		try {
			CommunityResultPayload payload = new CommunityResultPayload(
				repository, POLICY_VERSION, LOOKBACK_DAYS_RECORDED, summaryRetryAt, topics, limitations);
			CommunitySnapshotRow row = new CommunitySnapshotRow(
				packageId, task.snapshot().refreshId(), PAYLOAD_VERSION, Instant.now(), dataStatus, payload);
			snapshotRepository.upsert(row);
			task.markCompleted();
		} catch (RuntimeException e) {
			log.error("커뮤니티 결과 게시 실패: packageId={}", packageId, e);
			fail(task, CommunityErrorCode.PUBLISH_FAILED, null);
		}
	}

	private void fail(RefreshTask task, CommunityErrorCode errorCode, Instant retryAt) {
		Instant effectiveRetryAt = retryAt != null ? retryAt : Instant.now().plus(CommunityProperties.FAILURE_COOLDOWN);
		log.warn("커뮤니티 refresh 실패: packageId={}, errorCode={}", task.packageId(), errorCode);
		task.markFailed(errorCode, effectiveRetryAt);
	}

	/** {@code retryAt}이 있으면(GitHub rate limit 전용 신호) 그것으로, 없으면 문구로 최선을 다해 분류한다. */
	private static CommunityErrorCode classify(String reason, Instant retryAt) {
		if (retryAt != null) {
			return CommunityErrorCode.GITHUB_RATE_LIMITED;
		}
		if (reason != null && reason.contains("시간 예산 소진")) {
			return CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED;
		}
		if (reason != null && reason.contains("npm")) {
			return CommunityErrorCode.NPM_UNAVAILABLE;
		}
		return CommunityErrorCode.GITHUB_UNAVAILABLE;
	}
}
