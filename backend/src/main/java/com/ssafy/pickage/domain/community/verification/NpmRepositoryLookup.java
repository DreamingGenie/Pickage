package com.ssafy.pickage.domain.community.verification;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * npm latest metadata에서 {@code repository} 필드 <b>하나만</b> 읽는다. 일반 registry 클라이언트가 아니다 — 버전
 * 목록·dist·의존성 등은 다루지 않는다. 그건 별도 인프라 티켓
 * [S15P21A506-221](https://ssafy.atlassian.net/browse/S15P21A506-221)(아직 미착수)의 몫이며, 이 클래스는 그 티켓을
 * 앞지르거나 대체하지 않는다(Spec §2).
 */
public class NpmRepositoryLookup {

    private static final String REAL_REGISTRY_BASE = "https://registry.npmjs.org";
    private static final ObjectMapper JSON = new ObjectMapper();

    private final HttpClient httpClient;
    private final long maxResponseBytes;
    private final String registryBase;

    public NpmRepositoryLookup(HttpClient httpClient, long maxResponseBytes) {
        this(httpClient, maxResponseBytes, REAL_REGISTRY_BASE);
    }

    /** 시험 전용 — 가짜 서버(로컬 loopback)를 향하게 한다. 운영 코드 경로에서는 쓰지 않는다. */
    NpmRepositoryLookup(HttpClient httpClient, long maxResponseBytes, String registryBase) {
        this.httpClient = httpClient;
        this.maxResponseBytes = maxResponseBytes;
        this.registryBase = registryBase;
    }

    /**
     * @throws UpstreamFetchException 네트워크 오류·404가 아닌 오류 상태·응답 byte 상한 초과
     */
    public NpmLookupOutcome fetchRepositoryField(String packageName) {
        return fetchRepositoryField(packageName, Duration.ofSeconds(10));
    }

    /**
     * 317(orchestrator)의 20초 단일 예산 중 남은 시간을 전달받는다 — 212의 {@code
     * GitHubIssueSearchClient.clampTimeout}과 같은 방식(설정값·남은 시간 중 짧은 쪽)으로 이 호출 하나의 상한을 정한다(전체 정밀 리뷰에서
     * 발견 — 213은 원래 이 예산 개념이 전혀 없어 고정 10초씩 최대 3회 호출이 20초 전체 예산을 넘길 수 있었다).
     *
     * @throws UpstreamFetchException 네트워크 오류·404가 아닌 오류 상태·응답 byte 상한 초과
     */
    public NpmLookupOutcome fetchRepositoryField(String packageName, Duration remainingBudget) {
        URI uri =
                URI.create(
                        registryBase
                                + "/"
                                + URLEncoder.encode(packageName, StandardCharsets.UTF_8)
                                + "/latest");
        HttpRequest request =
                HttpRequest.newBuilder(uri)
                        .GET()
                        .timeout(clampTimeout(remainingBudget))
                        .header("Accept", "application/json")
                        .build();

        HttpResponse<java.io.InputStream> response;
        try {
            response = BoundedHttpReader.send(httpClient, request, maxResponseBytes);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new UpstreamFetchException("npm registry 통신 오류: " + packageName, e);
        }

        // 리뷰에서 발견: `response.body();` 는 스트림을 반환만 할 뿐 읽거나 닫지 않는다 —
        // "스트림 자원 정리"라는 원래 주석은 틀렸다. try-with-resources 로 404·오류·성공
        // 모든 종료 경로에서 실제로 닫는다. 안 닫으면 npm에 없는 패키지를 여러 개 조회할
        // 때마다 HttpClient 커넥션 풀이 하나씩 고갈된다.
        try (java.io.InputStream body = response.body()) {
            if (response.statusCode() == 404) {
                return new NpmLookupOutcome.NotFound();
            }
            if (response.statusCode() != 200) {
                throw new UpstreamFetchException("npm registry 오류 상태: " + response.statusCode());
            }

            String json = BoundedHttpReader.readBounded(body, maxResponseBytes, "npm registry");
            return parseRepositoryField(json, packageName);
        } catch (IOException e) {
            throw new UpstreamFetchException("npm registry 응답 스트림 종료 오류", e);
        }
    }

    private NpmLookupOutcome parseRepositoryField(String json, String expectedName) {
        JsonNode root;
        try {
            root = JSON.readTree(json);
        } catch (IOException e) {
            throw new UpstreamFetchException("npm registry 응답 JSON 파싱 실패", e);
        }

        if (root == null || !root.isObject())
            throw new UpstreamFetchException("Invalid npm metadata");
        if (!expectedName.equals(root.path("name").asText()))
            return new NpmLookupOutcome.NotFound();
        JsonNode repository = root.path("repository");
        if (repository.isMissingNode() || repository.isNull()) {
            return new NpmLookupOutcome.NoRepositoryField();
        }
        if (repository.isTextual()) {
            return new NpmLookupOutcome.Found(repository.asText(), null);
        }
        if (repository.isObject()) {
            JsonNode url = repository.path("url");
            if (url.isMissingNode() || !url.isTextual()) {
                return new NpmLookupOutcome.Found("", null);
            }
            JsonNode directory = repository.path("directory");
            return new NpmLookupOutcome.Found(
                    url.asText(),
                    directory.isMissingNode() || directory.isNull()
                            ? null
                            : directory.isTextual() ? directory.asText() : "");
        }
        return new NpmLookupOutcome.Found("", null);
    }

    /** 212 클라이언트들과 같은 규칙 — 설정값(10초)과 남은 예산 중 짧은 쪽. */
    private static Duration clampTimeout(Duration remainingBudget) {
        Duration perCallCap = Duration.ofSeconds(10);
        return remainingBudget.compareTo(perCallCap) < 0 ? remainingBudget : perCallCap;
    }
}
