package com.ssafy.pickage.domain.community.collection;

import com.ssafy.pickage.domain.community.verification.*;

import java.time.*;
import java.util.*;

/** 선택한 topic 집합의 사실 수치와 수집 한계를 끝까지 함께 전달한다. */
public class IssueCollectionService {
    private final GitHubIssueSearchClient searchClient;
    private final GitHubIssueCommentsClient commentsClient;

    public IssueCollectionService(
            GitHubIssueSearchClient searchClient, GitHubIssueCommentsClient commentsClient) {
        this.searchClient = searchClient;
        this.commentsClient = commentsClient;
    }

    public IssueCollectionResult collect(String owner, String repo, Duration budget) {
        return collect(owner, repo, budget, () -> {});
    }

    public IssueCollectionResult collect(
            String owner, String repo, Duration budget, Runnable commentsStage) {
        Instant deadline = Instant.now().plus(budget);
        int lookback = 180;
        var limitations = new ArrayList<String>();
        try {
            checkTime(deadline);
            SearchPage page =
                    searchClient.searchActiveIssues(owner, repo, lookback, timeLeft(deadline));
            if (page.totalCount() == 0 && !page.incompleteResults()) {
                checkTime(deadline);
                lookback = 365;
                page = searchClient.searchActiveIssues(owner, repo, lookback, timeLeft(deadline));
            }
            if (page.incompleteResults()) limitations.add("SEARCH_INCOMPLETE");
            var selected = IssueSelectionPolicy.select(page.items());
            if (page.items().stream()
                    .anyMatch(i -> i.isPullRequest() || i.locked() || i.authorIsBot()))
                limitations.add("ISSUE_FILTERED");
            if (selected.isEmpty()) {
                if (page.incompleteResults())
                    return new IssueCollectionResult.Success(List.of(), limitations, lookback);
                return new IssueCollectionResult.NoDiscussionData(lookback, limitations);
            }
            commentsStage.run();
            var topics = new ArrayList<CollectedIssue>();
            for (var item : selected) topics.add(collectIssue(owner, repo, item, deadline));
            return new IssueCollectionResult.Success(topics, limitations, lookback);
        } catch (GitHubRateLimitException e) {
            return new IssueCollectionResult.FetchLimited("GitHub rate limit", e.retryAt());
        } catch (UpstreamFetchException e) {
            return new IssueCollectionResult.FetchLimited(
                    timeLeft(deadline).isZero() ? "시간 예산 소진" : "GitHub collection unavailable",
                    null);
        }
    }

    private CollectedIssue collectIssue(
            String owner, String repo, SearchResultItem item, Instant deadline) {
        var candidates = new ArrayList<CollectedComment>();
        boolean failed = false, sizeLimited = false;
        try {
            checkTime(deadline);
            var first = commentsClient.fetchPage(owner, repo, item.number(), 1, timeLeft(deadline));
            candidates.addAll(first.comments());
            int last = first.lastPageNumber();
            failed = last != (int) Math.max(1, (item.commentCount() + 99L) / 100);
            if (last > 1) {
                CommentsPage tail = null;
                try {
                    checkTime(deadline);
                    tail =
                            commentsClient.fetchPage(
                                    owner, repo, item.number(), last, timeLeft(deadline));
                    candidates.addAll(tail.comments());
                    if (tail.lastPageNumber() != last) failed = true;
                } catch (UpstreamFetchException e) {
                    failed = true;
                    sizeLimited |= e.sizeLimited();
                }
                if (last > 2 && (tail == null || tail.comments().size() < 100)) {
                    try {
                        checkTime(deadline);
                        var previous =
                                commentsClient.fetchPage(
                                        owner, repo, item.number(), last - 1, timeLeft(deadline));
                        candidates.addAll(previous.comments());
                        if (previous.lastPageNumber() != last) failed = true;
                    } catch (UpstreamFetchException e) {
                        failed = true;
                        sizeLimited |= e.sizeLimited();
                    }
                }
                if (tail != null
                        && (long) (last - 1) * 100 + tail.comments().size() != item.commentCount())
                    failed = true;
            } else if (first.comments().size() != item.commentCount()) failed = true;
        } catch (UpstreamFetchException e) {
            failed = true;
            sizeLimited |= e.sizeLimited();
        }
        var comments = CommentWindowResolver.selectLatest(candidates);
        if (candidates.stream().map(CollectedComment::sourceCommentId).distinct().count()
                != candidates.size()) failed = true;
        boolean truncated =
                failed
                        || item.commentCount() > 100
                        || comments.size() < Math.min(100, item.commentCount());
        CommentCollectionStatus status =
                failed && comments.isEmpty()
                        ? CommentCollectionStatus.FAILED
                        : truncated
                                ? CommentCollectionStatus.TRUNCATED
                                : CommentCollectionStatus.COMPLETE;
        var limitations = new ArrayList<String>();
        if (status != CommentCollectionStatus.COMPLETE)
            limitations.add(
                    status == CommentCollectionStatus.FAILED
                            ? "COMMENTS_UNAVAILABLE"
                            : "COMMENTS_TRUNCATED");
        if (sizeLimited) limitations.add("RESPONSE_SIZE_LIMITED");
        return new CollectedIssue(
                item.number(),
                item.title(),
                item.state(),
                item.updatedAt(),
                item.authorLogin(),
                item.commentCount(),
                item.reactionCount(),
                status,
                comments,
                limitations,
                item.sourceIssueId(),
                item.createdAt(),
                item.authorId(),
                item.body());
    }

    private static void checkTime(Instant deadline) {
        if (timeLeft(deadline).isZero() || Thread.currentThread().isInterrupted())
            throw new UpstreamFetchException("시간 예산 소진");
    }

    private static Duration timeLeft(Instant deadline) {
        var d = Duration.between(Instant.now(), deadline);
        return d.isNegative() ? Duration.ZERO : d;
    }
}
