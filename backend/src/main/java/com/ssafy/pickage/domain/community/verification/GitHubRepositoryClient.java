package com.ssafy.pickage.domain.community.verification;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Base64;
import java.util.Optional;

/**
 * 이 Phase가 필요한 세 가지만 하는 좁은 GitHub 클라이언트 — 저장소 존재·archived 확인, 경로별 {@code package.json} 이름 대조, rate
 * limit 헤더 판독. Issue·댓글 조회는 여기 없다 (Phase 3, {@code S15P21A506-212}의 몫 — Jira 212 "213의 검증 결과를 받은 고정
 * GitHub API 경로만 호출한다").
 *
 * <p>{@code owner}·{@code repo}는 항상 {@link RepositoryUrlParser}가 이미 검증한 값만 들어온다 — 이 클래스가 신뢰할 수 없는
 * host에 연결하는 경로는 없다(항상 {@code api.github.com} 고정).
 */
public class GitHubRepositoryClient {

    private static final String REAL_API_BASE = "https://api.github.com";
    private static final String API_VERSION = "2026-03-10";
    private static final ObjectMapper JSON = new ObjectMapper();

    private final HttpClient httpClient;
    private GitHubRateGate rateGate = new GitHubRateGate();

    public void setRateGate(GitHubRateGate gate) {
        this.rateGate = java.util.Objects.requireNonNull(gate);
    }

    private final String token;
    private final long maxResponseBytes;
    private final String apiBase;

    public GitHubRepositoryClient(HttpClient httpClient, String token, long maxResponseBytes) {
        this(httpClient, token, maxResponseBytes, REAL_API_BASE);
    }

    /** 시험 전용 — 가짜 서버(로컬 loopback)를 향하게 한다. 운영 코드 경로에서는 쓰지 않는다. */
    GitHubRepositoryClient(
            HttpClient httpClient, String token, long maxResponseBytes, String apiBase) {
        this.httpClient = httpClient;
        this.token = token;
        this.maxResponseBytes = maxResponseBytes;
        this.apiBase = apiBase;
    }

    /**
     * @throws GitHubRepositoryNotFoundException 404 또는 rate-limit이 아닌 403
     * @throws GitHubRateLimitException core rate limit 소진
     * @throws UpstreamFetchException 그 외 네트워크·통신 오류
     */
    public boolean isArchived(String owner, String repo) {
        return isArchived(owner, repo, Duration.ofSeconds(10));
    }

    /**
     * 317(orchestrator)의 20초 단일 예산 중 남은 시간을 전달받는다(전체 정밀 리뷰에서 발견 — 213은 원래 이 개념이 없어 {@code
     * verify()}가 최대 30초까지 걸릴 수 있었다). 212의 {@code clampTimeout}과 같은 규칙(설정값·남은 시간 중 짧은 쪽).
     *
     * @throws GitHubRepositoryNotFoundException 404 또는 rate-limit이 아닌 403
     * @throws GitHubRateLimitException core rate limit 소진
     * @throws UpstreamFetchException 그 외 네트워크·통신 오류
     */
    public boolean isArchived(String owner, String repo, Duration remainingBudget) {
        HttpResponse<java.io.InputStream> response =
                send(
                        URI.create(apiBase + "/repos/" + owner + "/" + repo),
                        "GitHub repos",
                        remainingBudget);

        // 리뷰에서 발견: 성공(200) 경로만 BoundedHttpReader 의 try-with-resources 로
        // 스트림을 닫았고, 404/403/429/그 외 응답은 열린 채로 버려져 HttpClient 커넥션
        // 풀이 고갈될 수 있었다. try-with-resources 로 모든 종료 경로(return·throw)에서
        // 반드시 닫히게 한다 — 성공 케이스에서는 BoundedHttpReader 가 같은 스트림을
        // 한 번 더 닫아도(멱등) 문제 없다.
        try (java.io.InputStream body = response.body()) {
            if (response.statusCode() == 404) {
                throw new GitHubRepositoryNotFoundException("저장소 없음: " + owner + "/" + repo);
            }
            checkRateLimit(response);
            if (response.statusCode() == 403) {
                throw new GitHubRepositoryNotFoundException("접근 거부(비공개 등): " + owner + "/" + repo);
            }
            if (response.statusCode() != 200) {
                throw new UpstreamFetchException("GitHub repos 오류 상태: " + response.statusCode());
            }

            String json = BoundedHttpReader.readBounded(body, maxResponseBytes, "GitHub repos");
            JsonNode metadata = readTree(json);
            if (!metadata.path("private").isBoolean() || !metadata.path("archived").isBoolean())
                throw new UpstreamFetchException("Invalid repository metadata");
            if (metadata.path("private").asBoolean())
                throw new GitHubRepositoryNotFoundException("Repository is not public");
            return metadata.path("archived").asBoolean();
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub repos 응답 스트림 종료 오류", e);
        }
    }

    /**
     * {@code directory}가 {@code null}이면 저장소 루트의 {@code package.json}을 본다.
     *
     * @throws GitHubRateLimitException core rate limit 소진
     * @throws UpstreamFetchException 404·403이 아닌 통신 오류
     */
    public PackageJsonNameCheck checkPackageJsonName(
            String owner, String repo, String directory, String expectedName) {
        return checkPackageJsonName(owner, repo, directory, expectedName, Duration.ofSeconds(10));
    }

    /** {@link #isArchived(String, String, Duration)}와 같은 이유. */
    public PackageJsonNameCheck checkPackageJsonName(
            String owner,
            String repo,
            String directory,
            String expectedName,
            Duration remainingBudget) {
        if (!RepositoryUrlParser.safeDirectory(directory))
            throw new UpstreamFetchException("Invalid repository directory");
        String path =
                (directory == null || directory.isBlank())
                        ? "package.json"
                        : trimSlashes(directory) + "/package.json";
        HttpResponse<java.io.InputStream> response =
                send(
                        URI.create(apiBase + "/repos/" + owner + "/" + repo + "/contents/" + path),
                        "GitHub contents",
                        remainingBudget);

        // isArchived 와 같은 이유(리뷰 발견) — 모든 종료 경로에서 스트림을 닫는다.
        try (java.io.InputStream body = response.body()) {
            if (response.statusCode() == 404) {
                return PackageJsonNameCheck.NOT_FOUND;
            }
            checkRateLimit(response);
            if (response.statusCode() != 200) {
                throw new UpstreamFetchException("GitHub contents 오류 상태: " + response.statusCode());
            }

            String json = BoundedHttpReader.readBounded(body, maxResponseBytes, "GitHub contents");
            JsonNode contentNode = readTree(json);
            String encoding = contentNode.path("encoding").asText("");
            String content = contentNode.path("content").asText("");
            if (!"base64".equals(encoding) || content.isBlank()) {
                return PackageJsonNameCheck.NOT_FOUND;
            }

            String decoded;
            try {
                decoded =
                        new String(
                                Base64.getMimeDecoder().decode(content),
                                java.nio.charset.StandardCharsets.UTF_8);
            } catch (IllegalArgumentException e) {
                return PackageJsonNameCheck.NOT_FOUND;
            }

            Optional<String> nameField = readPackageJsonName(decoded);
            if (nameField.isEmpty()) {
                return PackageJsonNameCheck.NOT_FOUND;
            }
            if (!nameField.get().equals(expectedName)) return PackageJsonNameCheck.MISMATCH;
            return readTree(decoded).hasNonNull("workspaces")
                    ? PackageJsonNameCheck.MATCH_WORKSPACES
                    : PackageJsonNameCheck.MATCH;
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub contents 응답 스트림 종료 오류", e);
        }
    }

    private Optional<String> readPackageJsonName(String packageJsonText) {
        try {
            JsonNode node = JSON.readTree(packageJsonText);
            JsonNode name = node.path("name");
            return name.isTextual() ? Optional.of(name.asText()) : Optional.empty();
        } catch (IOException e) {
            return Optional.empty();
        }
    }

    private HttpResponse<java.io.InputStream> send(
            URI uri, String sourceForLogging, Duration remainingBudget) {
        rateGate.check("core");
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(uri)
                        .GET()
                        .timeout(clampTimeout(remainingBudget))
                        .header("Accept", "application/vnd.github+json")
                        .header("X-GitHub-Api-Version", API_VERSION);
        if (token != null && !token.isBlank()) {
            builder.header("Authorization", "Bearer " + token);
        }

        try {
            return BoundedHttpReader.send(httpClient, builder.build(), maxResponseBytes);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            // 원인 메시지에 인증 헤더가 들어갈 일은 없지만, 혹시 모를 노출을 막기 위해
            // sourceForLogging(호출 종류)만 남기고 cause 는 별도 필드로만 보존한다.
            throw new UpstreamFetchException(sourceForLogging + " 통신 오류", e);
        }
    }

    private void checkRateLimit(HttpResponse<?> response) {
        rateGate.observe("core", response);
    }

    private JsonNode readTree(String json) {
        try {
            return JSON.readTree(json);
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub 응답 JSON 파싱 실패", e);
        }
    }

    /** 212 클라이언트들과 같은 규칙 — 설정값(10초)과 남은 예산 중 짧은 쪽. */
    private static Duration clampTimeout(Duration remainingBudget) {
        Duration perCallCap = Duration.ofSeconds(10);
        return remainingBudget.compareTo(perCallCap) < 0 ? remainingBudget : perCallCap;
    }

    private static String trimSlashes(String path) {
        String trimmed = path;
        if (trimmed.startsWith("/")) {
            trimmed = trimmed.substring(1);
        }
        if (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }
}
