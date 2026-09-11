package com.ssafy.pickage.domain.community.verification;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.Test;

import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;

class VerificationContractReviewTest {
    @Test
    void R09_successfulLastTokenBlocksOnlyItsResourceAndIsShared() {
        Instant now = Instant.parse("2026-09-01T00:00:00Z");
        var gate = new GitHubRateGate(Clock.fixed(now, ZoneOffset.UTC));
        gate.observe(
                "core",
                response(
                        200,
                        java.util.Map.of(
                                "X-RateLimit-Remaining",
                                java.util.List.of("0"),
                                "X-RateLimit-Reset",
                                java.util.List.of(
                                        Long.toString(now.plusSeconds(120).getEpochSecond()))),
                        "{}"));
        assertThrows(GitHubRateLimitException.class, () -> gate.check("core"));
        assertDoesNotThrow(() -> gate.check("search"));
        assertEquals(now.plusSeconds(120), gate.retryAt());
    }

    @Test
    void R09_secondaryWithoutHeadersBlocksAllResources() {
        Instant now = Instant.parse("2026-09-01T00:00:00Z");
        var gate = new GitHubRateGate(Clock.fixed(now, ZoneOffset.UTC));
        assertThrows(
                GitHubRateLimitException.class,
                () ->
                        gate.observe(
                                "core",
                                response(
                                        403,
                                        java.util.Map.of(),
                                        "{\"message\":\"You have exceeded a secondary rate"
                                            + " limit.\"}")));
        assertThrows(GitHubRateLimitException.class, () -> gate.check("search"));
        assertEquals(now.plusSeconds(60), gate.retryAt());
    }

    @Test
    void R09_plainForbiddenDoesNotPoisonTokenGate() {
        var gate = new GitHubRateGate();
        assertDoesNotThrow(
                () ->
                        gate.observe(
                                "core",
                                response(403, java.util.Map.of(), "{\"message\":\"Forbidden\"}")));
        assertNull(gate.retryAt());
    }

    @SuppressWarnings("unchecked")
    static HttpResponse<java.io.InputStream> response(
            int status, java.util.Map<String, java.util.List<String>> headers, String body) {
        HttpResponse<java.io.InputStream> r = org.mockito.Mockito.mock(HttpResponse.class);
        org.mockito.Mockito.when(r.statusCode()).thenReturn(status);
        org.mockito.Mockito.when(r.headers()).thenReturn(HttpHeaders.of(headers, (a, b) -> true));
        org.mockito.Mockito.when(r.body())
                .thenReturn(
                        new java.io.ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8)));
        return r;
    }

    @Test
    void R01_malformedNpmMustNotFallBackToDb() {
        var db = RepositoryUrlParser.parse("https://github.com/fixture/repo", null);
        var npm = RepositoryUrlParser.parse("malformed repository", null);
        assertFalse(
                RepositoryCandidatePolicy.resolve(db, npm) instanceof CandidateSelection.Proceed);
    }

    @Test
    void R01_httpsCredentialsMustBeRejected() {
        assertFalse(
                RepositoryUrlParser.parse("https://user:pass@github.com/fixture/repo", null)
                        instanceof CandidateSource.GitHubUrl);
    }

    @Test
    void R01_directoryTraversalMustBeRejected() {
        assertFalse(
                RepositoryUrlParser.parse("https://github.com/fixture/repo", "../../../../search")
                        instanceof CandidateSource.GitHubUrl);
    }

    @Test
    void R01_dbOnlyNameMismatchMustBeAmbiguous() {
        assertInstanceOf(
                RepositoryVerificationResult.AmbiguousScope.class,
                RepositoryScopePolicy.classify(
                        new ResolvedCandidate("fixture", "repo", null, false, false),
                        PackageJsonNameCheck.MISMATCH,
                        PackageJsonNameCheck.NOT_FOUND,
                        false));
    }

    @Test
    void R01_privateRepositoryMustNotBeAcceptedAsPublic() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
                "/repos/fixture/repo",
                exchange -> {
                    byte[] body =
                            "{\"private\":true,\"archived\":false}"
                                    .getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                    exchange.close();
                });
        server.start();
        try (var http = HttpClient.newHttpClient()) {
            var client =
                    new GitHubRepositoryClient(
                            http, null, 1000, "http://127.0.0.1:" + server.getAddress().getPort());
            assertThrows(
                    GitHubRepositoryNotFoundException.class,
                    () -> client.isArchived("fixture", "repo"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void R10_bodyReadMustRespectRequestBudget() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
                "/fixture/latest",
                exchange -> {
                    exchange.sendResponseHeaders(200, 0);
                    exchange.getResponseBody().write('{');
                    exchange.getResponseBody().flush();
                    try {
                        Thread.sleep(700);
                        exchange.getResponseBody().write('}');
                    } catch (Exception ignored) {
                    } finally {
                        exchange.close();
                    }
                });
        server.start();
        try (var http = HttpClient.newHttpClient()) {
            var client =
                    new NpmRepositoryLookup(
                            http, 1000, "http://127.0.0.1:" + server.getAddress().getPort());
            assertThrows(
                    UpstreamFetchException.class,
                    () -> client.fetchRepositoryField("fixture", Duration.ofMillis(150)));
        } finally {
            server.stop(0);
        }
    }
}
