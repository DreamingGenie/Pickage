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
