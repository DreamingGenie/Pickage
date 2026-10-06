package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpClient;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

class GitHubRepositoryClientTest {

    private static final long MAX_BYTES = 2L * 1024 * 1024;

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

    private GitHubRepositoryClient client() {
        return new GitHubRepositoryClient(httpClient, "fake-token", MAX_BYTES, server.baseUrl());
    }

    @Test
    void 존재하는_저장소의_archived_여부를_읽는다() {
        server.respond(
                "/repos/pinojs/pino", 200, "{\"private\":false,\"archived\":false}", Map.of());
        assertThat(client().isArchived("pinojs", "pino")).isFalse();
    }

    @Test
    void archived_true도_그대로_읽는다() {
        server.respond("/repos/old/repo", 200, "{\"private\":false,\"archived\":true}", Map.of());
        assertThat(client().isArchived("old", "repo")).isTrue();
    }

    @Test
    void 저장소_404는_GitHubRepositoryNotFoundException이다() {
        server.respond("/repos/ghost/repo", 404, "not found", Map.of());
        assertThatThrownBy(() -> client().isArchived("ghost", "repo"))
                .isInstanceOf(GitHubRepositoryNotFoundException.class);
    }

    @Test
    void rate_limit_아닌_403은_GitHubRepositoryNotFoundException이다() {
        // X-RateLimit-Remaining 이 0이 아니고 Retry-After 도 없으면 "접근 거부"(비공개 등)로 본다.
        server.respond(
                "/repos/private/repo", 403, "forbidden", Map.of("X-RateLimit-Remaining", "42"));
        assertThatThrownBy(() -> client().isArchived("private", "repo"))
                .isInstanceOf(GitHubRepositoryNotFoundException.class);
    }

    @Test
    void remaining_0인_403은_GitHubRateLimitException이다() {
        server.respond(
                "/repos/limited/repo",
                403,
                "rate limited",
                Map.of("X-RateLimit-Remaining", "0", "X-RateLimit-Reset", "9999999999"));
        assertThatThrownBy(() -> client().isArchived("limited", "repo"))
                .isInstanceOf(GitHubRateLimitException.class);
    }

    @Test
    void HTTP_429는_항상_GitHubRateLimitException이고_Retry_After를_읽는다() {
        server.respond("/repos/busy/repo", 429, "too many requests", Map.of("Retry-After", "30"));
        assertThatThrownBy(() -> client().isArchived("busy", "repo"))
                .isInstanceOfSatisfying(
                        GitHubRateLimitException.class, e -> assertThat(e.retryAt()).isNotNull());
    }

    @Test
    void 그_외_오류_상태는_UpstreamFetchException이다() {
        server.respond("/repos/broken/repo", 500, "boom", Map.of());
        assertThatThrownBy(() -> client().isArchived("broken", "repo"))
                .isInstanceOf(UpstreamFetchException.class);
    }

    @Test
    void 루트_package_json_이름이_일치하면_MATCH다() {
        respondPackageJson("/repos/pinojs/pino/contents/package.json", "{\"name\":\"pino\"}");
        assertThat(client().checkPackageJsonName("pinojs", "pino", null, "pino"))
                .isEqualTo(PackageJsonNameCheck.MATCH);
    }

    @Test
    void 루트_package_json_이름이_다르면_MISMATCH다() {
        respondPackageJson("/repos/someorg/repo/contents/package.json", "{\"name\":\"다른-이름\"}");
        assertThat(client().checkPackageJsonName("someorg", "repo", null, "pino"))
                .isEqualTo(PackageJsonNameCheck.MISMATCH);
    }

    @Test
    void directory_경로의_package_json도_같은_방식으로_확인한다() {
        respondPackageJson(
                "/repos/facebook/react/contents/packages/react/package.json",
                "{\"name\":\"react\"}");
        assertThat(client().checkPackageJsonName("facebook", "react", "packages/react", "react"))
                .isEqualTo(PackageJsonNameCheck.MATCH);
    }

    @Test
    void package_json_경로가_404면_NOT_FOUND다() {
        server.respond("/repos/no-pkg/repo/contents/package.json", 404, "not found", Map.of());
        assertThat(client().checkPackageJsonName("no-pkg", "repo", null, "pino"))
                .isEqualTo(PackageJsonNameCheck.NOT_FOUND);
    }

    @Test
    void package_json_조회도_rate_limit을_구분한다() {
        server.respond(
                "/repos/limited/repo/contents/package.json",
                403,
                "rate limited",
                Map.of("X-RateLimit-Remaining", "0"));
        assertThatThrownBy(() -> client().checkPackageJsonName("limited", "repo", null, "x"))
                .isInstanceOf(GitHubRateLimitException.class);
    }

    @Test
    void X_GitHub_Api_Version_헤더를_보낸다() {
        AtomicReference<String> captured = new AtomicReference<>();
        server.respondCapturingHeader(
                "/repos/version-check/repo", "X-GitHub-Api-Version", captured::set);

        client().isArchived("version-check", "repo");

        assertThat(captured.get()).isEqualTo("2026-03-10");
    }

    private void respondPackageJson(String path, String packageJsonContent) {
        String base64 =
                Base64.getEncoder()
                        .encodeToString(
                                packageJsonContent.getBytes(
                                        java.nio.charset.StandardCharsets.UTF_8));
        server.respond(
                path, 200, "{\"encoding\":\"base64\",\"content\":\"" + base64 + "\"}", Map.of());
    }
}
