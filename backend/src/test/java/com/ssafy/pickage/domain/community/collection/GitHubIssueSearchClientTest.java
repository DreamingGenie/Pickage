package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.pickage.domain.community.verification.FakeHttpServer;
import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;

class GitHubIssueSearchClientTest {

    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final Duration BUDGET = Duration.ofSeconds(20);

    private FakeHttpServer server;
    private HttpClient httpClient;

    @BeforeEach
    void setUp() {
        server = FakeHttpServer.start();
        httpClient = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
    }

    @AfterEach
    void tearDown() {
        server.close();
    }

    private GitHubIssueSearchClient client() {
        return new GitHubIssueSearchClient(httpClient, "fake-token", MAX_BYTES, server.baseUrl());
    }

    @Test
    void 정상_응답을_파싱한다() {
        server.respond(
                "/search/issues",
                200,
                """
{
  "total_count": 2,
  "incomplete_results": false,
  "items": [
    {"id": 1001, "created_at": "2025-01-01T00:00:00Z", "number": 1, "title": "a", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
     "comments": 10, "locked": false, "user": {"login": "u1", "type": "User"},
     "reactions": {"total_count": 2}},
    {"id": 1002, "created_at": "2025-01-01T00:00:00Z", "number": 2, "title": "b (PR)", "state": "open", "updated_at": "2026-01-02T00:00:00Z",
     "comments": 5, "locked": false, "user": {"login": "u2", "type": "User"},
     "pull_request": {"url": "..."}, "reactions": {"total_count": 0}}
  ]
}
""",
                Map.of());

        SearchPage page = client().searchActiveIssues("owner", "repo", 180, BUDGET);

        assertThat(page.totalCount()).isEqualTo(2);
        assertThat(page.incompleteResults()).isFalse();
        assertThat(page.items()).hasSize(2);
        assertThat(page.items().get(1).isPullRequest()).isTrue();
    }

    // ---- 저장소 전체 Issue 수 (S15P21A506-413)

    /** 전체 조회와 열린 조회를 쿼리 문자열로 구분해 다른 값을 준다. */
    private void countsReturn(int total, int open) {
        server.respondDynamic(
                "/search/issues",
                query -> {
                    String q = FakeHttpServer.queryParam(query, "q");
                    int count = q != null && q.contains("is:open") ? open : total;
                    return new FakeHttpServer.Answer(
                            200,
                            "{\"total_count\": " + count + ", \"incomplete_results\": false, \"items\": []}",
                            Map.of());
                });
    }

    @Test
    void 저장소_전체와_열린_Issue_수를_쿼리로_구분해_센다() {
        countsReturn(1234, 56);

        assertThat(client().countIssues("owner", "repo", false, BUDGET)).isEqualTo(1234);
        assertThat(client().countIssues("owner", "repo", true, BUDGET)).isEqualTo(56);
    }

    @Test
    void 카운트_쿼리는_PR을_빼고_저장소를_한정하며_한_건만_받아온다() {
        java.util.List<String> queries = new java.util.ArrayList<>();
        server.respondDynamic(
                "/search/issues",
                query -> {
                    queries.add(query);
                    return new FakeHttpServer.Answer(
                            200, "{\"total_count\": 7, \"incomplete_results\": false, \"items\": []}", Map.of());
                });

        client().countIssues("acme", "widget", true, BUDGET);
        client().countIssues("acme", "widget", false, BUDGET);

        assertThat(FakeHttpServer.queryParam(queries.get(0), "q")).isEqualTo("repo:acme/widget is:issue is:open");
        assertThat(FakeHttpServer.queryParam(queries.get(1), "q")).isEqualTo("repo:acme/widget is:issue");
        assertThat(FakeHttpServer.queryParam(queries.get(0), "per_page")).isEqualTo("1");
    }

    @Test
    void 결과가_불완전하면_카운트를_믿지_않고_null이다() {
        server.respond(
                "/search/issues",
                200,
                "{\"total_count\": 99, \"incomplete_results\": true, \"items\": []}",
                Map.of());

        assertThat(client().countIssues("owner", "repo", false, BUDGET)).isNull();
    }

    private void assertCountRejected(String body) {
        server.respond("/search/issues", 200, body, Map.of());
        assertThatThrownBy(() -> client().countIssues("owner", "repo", false, BUDGET))
                .isInstanceOf(UpstreamFetchException.class);
    }

    @Test
    void 카운트가_음수이면_통신_실패로_다룬다() {
        assertCountRejected("{\"total_count\": -3, \"incomplete_results\": false}");
    }

    @Test
    void 카운트가_숫자가_아니면_통신_실패로_다룬다() {
        assertCountRejected("{\"total_count\": \"12\", \"incomplete_results\": false}");
    }

    @Test
    void 카운트_응답에_incomplete_results가_없으면_통신_실패로_다룬다() {
        assertCountRejected("{\"total_count\": 5}");
    }

    @Test
    void 카운트_조회의_HTTP_오류는_통신_실패다() {
        server.respond("/search/issues", 500, "{}", Map.of());

        assertThatThrownBy(() -> client().countIssues("owner", "repo", false, BUDGET))
                .isInstanceOf(UpstreamFetchException.class);
    }

    @Test
    void incomplete_results를_읽는다() {
        server.respond(
                "/search/issues",
                200,
                "{\"total_count\": 0, \"incomplete_results\": true, \"items\": []}",
                Map.of());

        assertThat(client().searchActiveIssues("owner", "repo", 180, BUDGET).incompleteResults())
                .isTrue();
    }

    @Test
    void Bot_작성자를_구분한다() {
        server.respond(
                "/search/issues",
                200,
                """
{"total_count": 1, "incomplete_results": false, "items": [
  {"id": 1001, "created_at": "2025-01-01T00:00:00Z", "number": 1, "title": "a", "state": "open", "updated_at": "2026-01-01T00:00:00Z",
   "reactions": {"total_count": 0}, "comments": 1, "locked": false, "user": {"login": "bot", "type": "Bot"}}
]}
""",
                Map.of());

        assertThat(
                        client().searchActiveIssues("owner", "repo", 180, BUDGET)
                                .items()
                                .getFirst()
                                .authorIsBot())
                .isTrue();
    }

    @Test
    void remaining_0인_403은_rate_limit_예외다() {
        server.respond("/search/issues", 403, "rate limited", Map.of("X-RateLimit-Remaining", "0"));

        assertThatThrownBy(() -> client().searchActiveIssues("owner", "repo", 180, BUDGET))
                .isInstanceOf(GitHubRateLimitException.class);
    }

    @Test
    void HTTP_429는_rate_limit_예외다() {
        server.respond("/search/issues", 429, "too many", Map.of("Retry-After", "10"));

        assertThatThrownBy(() -> client().searchActiveIssues("owner", "repo", 180, BUDGET))
                .isInstanceOfSatisfying(
                        GitHubRateLimitException.class, e -> assertThat(e.retryAt()).isNotNull());
    }

    @Test
    void 그_외_오류_상태는_UpstreamFetchException이다() {
        server.respond("/search/issues", 500, "boom", Map.of());

        assertThatThrownBy(() -> client().searchActiveIssues("owner", "repo", 180, BUDGET))
                .isInstanceOf(UpstreamFetchException.class);
    }

    @Test
    void 응답이_byte_상한을_넘으면_UpstreamFetchException이다() {
        server.respond(
                "/search/issues",
                200,
                "{\"total_count\": 0, \"incomplete_results\": false, \"items\": [], \"padding\": \""
                        + "x".repeat(200)
                        + "\"}",
                Map.of());

        assertThatThrownBy(
                        () ->
                                new GitHubIssueSearchClient(
                                                httpClient, "fake-token", 50, server.baseUrl())
                                        .searchActiveIssues("owner", "repo", 180, BUDGET))
                .isInstanceOf(UpstreamFetchException.class);
    }
}
