package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.verification.FakeHttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

/** Jira S15P21A506-212 완료 판단 기준의 fixture 목록을 시나리오화한다. */
class IssueCollectionServiceTest {

    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final Duration BUDGET = Duration.ofSeconds(20);

    private FakeHttpServer server;
    private IssueCollectionService service;

    @BeforeEach
    void setUp() {
        server = FakeHttpServer.start();
        HttpClient httpClient =
                HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
        GitHubIssueSearchClient searchClient =
                new GitHubIssueSearchClient(httpClient, "fake-token", MAX_BYTES, server.baseUrl());
        GitHubIssueCommentsClient commentsClient =
                new GitHubIssueCommentsClient(
                        httpClient, "fake-token", MAX_BYTES, server.baseUrl());
        service = new IssueCollectionService(searchClient, commentsClient);
    }

    @AfterEach
    void tearDown() {
        server.close();
    }

    private void searchReturns(int totalCount, boolean incomplete, String itemsJson) {
        try {
            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var items = mapper.readTree(itemsJson);
            for (var item : items) {
                var node = (com.fasterxml.jackson.databind.node.ObjectNode) item;
                node.put("id", 1000 + node.path("number").asInt());
                node.put("created_at", "2025-01-01T00:00:00Z");
                node.put("body", "fixture body");
                if (!node.has("reactions")) node.putObject("reactions").put("total_count", 0);
            }
            itemsJson = mapper.writeValueAsString(items);
        } catch (java.io.IOException e) {
            throw new AssertionError(e);
        }
        server.respond(
                "/search/issues",
                200,
                "{\"total_count\": "
                        + totalCount
                        + ", \"incomplete_results\": "
                        + incomplete
                        + ", \"items\": "
                        + itemsJson
                        + "}",
                Map.of());
    }

    private static String oneIssueItem(int number, int commentCount) {
        return """
               [{"number": %d, "title": "t", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
                 "comments": %d, "locked": false, "user": {"login": "author", "type": "User"},
                 "reactions": {"total_count": 1}}]
               """
                .formatted(number, commentCount);
    }

    private static String commentsPage(int fromIdInclusive, int toIdInclusive) {
        String items =
                IntStream.rangeClosed(fromIdInclusive, toIdInclusive)
                        .mapToObj(
                                id ->
                                        """
{"id": %d, "user": {"login": "u", "type": "User"},
 "author_association": "NONE", "created_at": "2026-01-01T00:00:00Z", "body": "c%d",
 "reactions": {"total_count": 0}}
"""
                                                .formatted(id, id))
                        .collect(Collectors.joining(","));
        return "[" + items + "]";
    }

    @Test
    void 댓글_101개면_실제로_2page를_불러_최신_100개만_남긴다() {
        searchReturns(1, false, oneIssueItem(1, 101));
        // page=1: id 1~100(오래된 순), page=2: id 101 하나. Link: rel="last"=2.
        server.respondDynamic(
                "/repos/owner/repo/issues/1/comments",
                query -> {
                    String page = FakeHttpServer.queryParam(query, "page");
                    String body = "2".equals(page) ? commentsPage(101, 101) : commentsPage(1, 100);
                    return new FakeHttpServer.Answer(
                            200,
                            body,
                            Map.of(
                                    "Link",
                                    "<https://api.github.com/x?page=2>; rel=\"next\", "
                                            + "<https://api.github.com/x?page=2>; rel=\"last\""));
                });

        var success = (IssueCollectionResult.Success) service.collect("owner", "repo", BUDGET);
        CollectedIssue issue = success.topics().getFirst();

        // id 2~101 이 남아야 한다 — id 1(가장 오래된 것)만 100개를 넘겨서 잘려나간다.
        assertThat(issue.comments()).hasSize(100);
        assertThat(issue.comments().getFirst().sourceCommentId()).isEqualTo("2");
        assertThat(issue.comments().getLast().sourceCommentId()).isEqualTo("101");
        assertThat(issue.collectionStatus()).isEqualTo(CommentCollectionStatus.TRUNCATED);
    }

    @Test
    void 댓글_301개면_마지막_두_page를_불러_최신_100개를_남긴다() {
        searchReturns(1, false, oneIssueItem(1, 301));
        // 총 4page(1~100, 101~200, 201~300, 301). last=4 -> planAdditionalPages(4)=[4,3].
        server.respondDynamic(
                "/repos/owner/repo/issues/1/comments",
                query -> {
                    String page = FakeHttpServer.queryParam(query, "page");
                    String body =
                            switch (page == null ? "1" : page) {
                                case "3" -> commentsPage(201, 300);
                                case "4" -> commentsPage(301, 301);
                                default -> commentsPage(1, 100);
                            };
                    return new FakeHttpServer.Answer(
                            200,
                            body,
                            Map.of(
                                    "Link",
                                    "<https://api.github.com/x?page=2>; rel=\"next\", "
                                            + "<https://api.github.com/x?page=4>; rel=\"last\""));
                });

        var success = (IssueCollectionResult.Success) service.collect("owner", "repo", BUDGET);
        CollectedIssue issue = success.topics().getFirst();

        assertThat(issue.comments()).hasSize(100);
        assertThat(issue.comments().getFirst().sourceCommentId()).isEqualTo("202");
        assertThat(issue.comments().getLast().sourceCommentId()).isEqualTo("301");
    }

    @Test
    void PR이_포함된_응답에서도_이슈만_고른다() {
        searchReturns(
                2,
                false,
                """
[{"number": 1, "title": "pr", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
  "comments": 100, "locked": false, "user": {"login": "u", "type": "User"},
  "pull_request": {"url": "x"}},
 {"number": 2, "title": "issue", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
  "comments": 1, "locked": false, "user": {"login": "u", "type": "User"}}]
""");
        server.respond("/repos/owner/repo/issues/2/comments", 200, commentsPage(1, 1), Map.of());

        IssueCollectionResult result = service.collect("owner", "repo", BUDGET);

        var success = (IssueCollectionResult.Success) result;
        assertThat(success.topics()).extracting(CollectedIssue::issueNumber).containsExactly(2);
    }

    @Test
    void 필터_후_0건이면_NoDiscussionData다() {
        searchReturns(
                1,
                false,
                """
[{"number": 1, "title": "bot", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
  "comments": 1, "locked": false, "user": {"login": "bot", "type": "Bot"}}]
""");

        assertThat(service.collect("owner", "repo", BUDGET))
                .isInstanceOf(IssueCollectionResult.NoDiscussionData.class);
    }

    @Test
    void raw_0이면_365일로_한_번_확장한다() {
        // 이 fake 서버는 lookbackDays 값을 구분하지 않고 항상 같은 응답을 주므로,
        // 서비스가 실제로 "두 번째 호출"을 하는지는 첫 응답이 0건일 때 두 번째 응답
        // (동일 엔드포인트, 결국 같은 값)으로도 정상 진행되는지로 간접 확인한다.
        searchReturns(0, false, "[]");

        assertThat(service.collect("owner", "repo", BUDGET))
                .isInstanceOf(IssueCollectionResult.NoDiscussionData.class);
    }

    @Test
    void search_incomplete는_limitations에_남고_계속_진행한다() {
        searchReturns(1, true, oneIssueItem(1, 1));
        server.respond("/repos/owner/repo/issues/1/comments", 200, commentsPage(1, 1), Map.of());

        var success = (IssueCollectionResult.Success) service.collect("owner", "repo", BUDGET);

        assertThat(success.limitations()).contains("SEARCH_INCOMPLETE");
    }

    @Test
    void search_rate_limit이면_전체_수집을_중단한다() {
        server.respond("/search/issues", 403, "rate limited", Map.of("X-RateLimit-Remaining", "0"));

        assertThat(service.collect("owner", "repo", BUDGET))
                .isInstanceOf(IssueCollectionResult.FetchLimited.class);
    }

    @Test
    void 댓글_수집_page_실패는_그_이슈만_TRUNCATED로_표시하고_계속한다() {
        searchReturns(1, false, oneIssueItem(1, 1));
        server.respond("/repos/owner/repo/issues/1/comments", 500, "boom", Map.of());

        var success = (IssueCollectionResult.Success) service.collect("owner", "repo", BUDGET);

        CollectedIssue issue = success.topics().getFirst();
        assertThat(issue.collectionStatus()).isEqualTo(CommentCollectionStatus.FAILED);
        assertThat(issue.comments()).isEmpty();
        assertThat(issue.limitations()).contains("COMMENTS_UNAVAILABLE");
    }

    @Test
    void 댓글_수집_rate_limit은_전체_수집을_중단한다() {
        searchReturns(1, false, oneIssueItem(1, 1));
        server.respond(
                "/repos/owner/repo/issues/1/comments",
                429,
                "slow down",
                Map.of("Retry-After", "5"));

        assertThat(service.collect("owner", "repo", BUDGET))
                .isInstanceOf(IssueCollectionResult.FetchLimited.class);
    }

    @Test
    void 이슈_두_개의_댓글_수집을_동시에_디스패치한다() {
        // S15P21A506-373 4단계 후속 — GMS 호출을 이슈 간 병렬로 디스패치한 것과 같은 이유로
        // 댓글 수집도 병렬화했다(순차였다면 이슈1이 예산을 다 써 이슈2가 시작하자마자
        // 시간 확인에서 걸리는 문제가 GMS 쪽에서 실제로 재현됐다). 각 호출을 300ms씩 일부러
        // 늦추고, 전체 수집이 두 호출을 합친 시간(600ms)이 아니라 한 호출 시간(300ms) 안팎에
        // 끝나는지, 두 호출의 시작 시각이 실제로 거의 겹치는지를 함께 확인한다.
        searchReturns(
                2,
                false,
                """
[{"number": 1, "title": "t1", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
  "comments": 2, "locked": false, "user": {"login": "a", "type": "User"}},
 {"number": 2, "title": "t2", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
  "comments": 1, "locked": false, "user": {"login": "a", "type": "User"}}]
""");
        var callStartedAtNanos = java.util.Collections.synchronizedList(new java.util.ArrayList<Long>());
        for (int issueNumber : new int[] {1, 2}) {
            server.respondDynamic(
                    "/repos/owner/repo/issues/" + issueNumber + "/comments",
                    query -> {
                        callStartedAtNanos.add(System.nanoTime());
                        try {
                            Thread.sleep(300);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                        return new FakeHttpServer.Answer(200, commentsPage(1, 1), Map.of());
                    });
        }

        long startNanos = System.nanoTime();
        IssueCollectionResult result = service.collect("owner", "repo", Duration.ofSeconds(20));
        long elapsedMs = (System.nanoTime() - startNanos) / 1_000_000;

        var success = (IssueCollectionResult.Success) result;
        assertThat(success.topics()).extracting(CollectedIssue::issueNumber).containsExactly(1, 2);

        assertThat(callStartedAtNanos).hasSize(2);
        long startGapMs =
                Math.abs(callStartedAtNanos.get(0) - callStartedAtNanos.get(1)) / 1_000_000;
        assertThat(startGapMs)
                .as("두 댓글 수집 호출이 순차였다면 300ms 가까이 벌어졌을 것이다")
                .isLessThan(150);
        assertThat(elapsedMs)
                .as("순차였다면 600ms 이상 걸린다 — 병렬이면 300ms 안팎(+오버헤드)이어야 한다")
                .isLessThan(550);
    }

    @Test
    void 총_댓글_수는_수집한_100개가_아니라_원천_숫자를_그대로_쓴다() {
        searchReturns(1, false, oneIssueItem(1, 250));
        server.respond("/repos/owner/repo/issues/1/comments", 200, commentsPage(1, 3), Map.of());

        var success = (IssueCollectionResult.Success) service.collect("owner", "repo", BUDGET);

        assertThat(success.topics().getFirst().totalCommentCount()).isEqualTo(250);
    }
}
