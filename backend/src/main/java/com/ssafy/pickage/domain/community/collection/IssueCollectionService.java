package com.ssafy.pickage.domain.community.collection;

import com.ssafy.pickage.domain.community.CommunityAsync;
import com.ssafy.pickage.domain.community.verification.*;

import java.time.*;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

/** 선택한 topic 집합의 사실 수치와 수집 한계를 끝까지 함께 전달한다. */
public class IssueCollectionService {
    private static final org.slf4j.Logger log =
            org.slf4j.LoggerFactory.getLogger(IssueCollectionService.class);
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
            // 이슈별 댓글 수집을 동시에 디스패치한다(S15P21A506-373 4단계 후속 — GMS 호출을
            // 병렬화한 것과 같은 이유. 순차로 돌면 이슈1이 예산을 다 쓰고 이슈2는 시작하자마자
            // 시간 확인에서 걸리는 문제가 GMS 쪽에서 실제로 재현됐던 것과 같은 종류다).
            // collectIssue는 UpstreamFetchException은 내부에서 흡수하지만
            // GitHubRateLimitException은 그대로 던진다 — join()이 이걸 CompletionException으로
            // 감싸므로 joinUnwrapping이 원래 타입으로 풀어서 아래 catch가 그대로 잡게 한다.
            var futures =
                    selected.stream()
                            .map(
                                    item ->
                                            // 댓글 수집은 GitHub 응답을 기다리는 블로킹 I/O 다 — 공용 풀이 아니라 전용 실행기다
                                            // (S15P21A506-415, {@link CommunityAsync} 참고).
                                            CompletableFuture.supplyAsync(
                                                    () -> collectIssue(owner, repo, item, deadline),
                                                    CommunityAsync.EXECUTOR))
                            .toList();
            var topics = futures.stream().map(IssueCollectionService::joinUnwrapping).toList();
            return new IssueCollectionResult.Success(topics, limitations, lookback);
        } catch (GitHubRateLimitException e) {
            return new IssueCollectionResult.FetchLimited("GitHub rate limit", e.retryAt());
        } catch (UpstreamFetchException e) {
            return new IssueCollectionResult.FetchLimited(
                    timeLeft(deadline).isZero() ? "시간 예산 소진" : "GitHub collection unavailable",
                    null);
        }
    }

    /**
     * 저장소 전체 Issue 수와 열린 Issue 수(S15P21A506-413). **어떤 실패도 예외로 내보내지 않는다** — 이 값은 수치 카드용 보조
     * 정보라 못 구해도 커뮤니티 결과는 게시돼야 한다. 못 구한 값은 {@code null} 이다.
     *
     * <p><b>순차로 조회한다.</b> 예전에는 두 조회를 공용 풀에 얹어 함께 보냈는데(S15P21A506-413), 그 풀이 GMS 응답을 기다리는
     * 작업에 다 잡히면 이 조회가 GMS 가 끝난 뒤에야 시작해 예산이 바닥났고, 그래서 코어가 적은 배포 서버에서만 <b>모든 패키지의 수치가
     * 비었다</b>(S15P21A506-415). 각 조회는 수백 ms 라 순차로 돌려도 합쳐 1초 안팎이고, 스레드 풀에 기대지 않는다.
     *
     * <p>열린 수가 전체 수보다 크면(두 조회 사이에 Issue 가 새로 열림) 전체 수를 열린 수로 맞춘다.
     */
    public RepositoryIssueCounts repositoryIssueCounts(String owner, String repo, Duration budget) {
        Instant deadline = Instant.now().plus(budget);
        Integer totalCount = countOrNull(owner, repo, false, deadline);
        Integer openCount = countOrNull(owner, repo, true, deadline);
        if (totalCount != null && openCount != null && openCount > totalCount)
            totalCount = openCount;
        return new RepositoryIssueCounts(totalCount, openCount);
    }

    /**
     * 못 구하면 {@code null} 이다. <b>이유는 반드시 로그에 남긴다</b> — 예전에는 예산이 없어 건너뛴 경우에 로그가 아예 없었고,
     * 그 밖의 실패도 예외 클래스 이름만 남겨서 배포 서버에서 왜 비는지 알 수 없었다. 예외 메시지에는 상태 코드·제한 해제
     * 시각만 있고 토큰·응답 본문은 없다.
     */
    private Integer countOrNull(String owner, String repo, boolean openOnly, Instant deadline) {
        String which = openOnly ? "열린 Issue" : "전체 Issue";
        try {
            Duration left = timeLeft(deadline);
            if (left.isZero()) {
                log.warn("저장소 {} 수 조회 건너뜀(수치 카드는 비워 둔다): 시간 예산 소진", which);
                return null;
            }
            Integer count = searchClient.countIssues(owner, repo, openOnly, left);
            if (count == null)
                log.warn("저장소 {} 수 조회 결과를 쓰지 않음(수치 카드는 비워 둔다): GitHub 가 불완전한 결과를 돌려줌", which);
            return count;
        } catch (GitHubRateLimitException e) {
            log.warn("저장소 {} 수 조회 실패(수치 카드는 비워 둔다): GitHub 호출 제한, 해제 {}", which, e.retryAt());
            return null;
        } catch (RuntimeException e) {
            log.warn(
                    "저장소 {} 수 조회 실패(수치 카드는 비워 둔다): {} — {}",
                    which,
                    e.getClass().getSimpleName(),
                    e.getMessage());
            return null;
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

    /** future.join()이 CompletionException으로 감싸는 원래 예외를 풀어서 그대로 다시 던진다. */
    private static <T> T joinUnwrapping(CompletableFuture<T> future) {
        try {
            return future.join();
        } catch (CompletionException e) {
            switch (e.getCause()) {
                case RuntimeException re -> throw re;
                case null, default -> throw e;
            }
        }
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
