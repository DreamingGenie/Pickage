package com.ssafy.pickage.domain.community.collection;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.verification.BoundedHttpReader;
import com.ssafy.pickage.domain.community.verification.GitHubRateGate;
import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * {@code GET /search/issues}만 호출하는 좁은 클라이언트(github-active-v1 정책의 원천 조회).
 *
 * <p>Search API는 core API(213의 {@link
 * com.ssafy.pickage.domain.community.verification.GitHubRepositoryClient})와 <b>별도 rate limit
 * quota</b>다(비인증 10/분, 인증 30/분 — 구현계획 §설정과 보안). 그래서 {@code send()}/rate-limit 판정 코드를 213에서 가져다 쓰지
 * 않고 이 클래스 안에 다시 작게 둔다 — 이미 병합·리뷰된 213 파일은 건드리지 않는다는 2026-09-11 사용자 결정 ({@code
 * docs/history/0923_0917_pickage_final_set_archive/for_community/specs/S15P21A506-212.md} §7).
 */
public class GitHubIssueSearchClient {

    private static final String REAL_API_BASE = "https://api.github.com";
    private static final String API_VERSION = "2026-03-10";
    private static final DateTimeFormatter DATE_FORMAT = DateTimeFormatter.ISO_LOCAL_DATE;
    private static final ObjectMapper JSON = new ObjectMapper();

    private final HttpClient httpClient;
    private GitHubRateGate rateGate = new GitHubRateGate();

    public void setRateGate(GitHubRateGate gate) {
        this.rateGate = java.util.Objects.requireNonNull(gate);
    }

    private final String token;
    private final long maxResponseBytes;
    private final String apiBase;

    public GitHubIssueSearchClient(HttpClient httpClient, String token, long maxResponseBytes) {
        this(httpClient, token, maxResponseBytes, REAL_API_BASE);
    }

    /** 시험 전용 — 가짜 서버를 향하게 한다. */
    GitHubIssueSearchClient(
            HttpClient httpClient, String token, long maxResponseBytes, String apiBase) {
        this.httpClient = httpClient;
        this.token = token;
        this.maxResponseBytes = maxResponseBytes;
        this.apiBase = apiBase;
    }

    /**
     * @param lookbackDays 180 또는 365(raw 0일 때 한 번 확장 — 호출자가 결정해 넘긴다)
     * @param remainingBudget 이 호출에 쓸 수 있는 남은 시간. Phase 4가 생기기 전까지는 호출자가 직접 정해서 넘긴다(2026-09-11 사용자
     *     결정, §7)
     * @throws GitHubRateLimitException search rate limit 소진
     * @throws UpstreamFetchException 그 외 통신 오류·byte 상한 초과
     */
    public SearchPage searchActiveIssues(
            String owner, String repo, int lookbackDays, Duration remainingBudget) {
        String since = LocalDate.now(ZoneOffset.UTC).minusDays(lookbackDays).format(DATE_FORMAT);
        String query = "repo:" + owner + "/" + repo + " is:issue updated:>=" + since;
        URI uri =
                URI.create(
                        apiBase
                                + "/search/issues?q="
                                + URLEncoder.encode(query, StandardCharsets.UTF_8)
                                + "&sort=comments&order=desc&per_page=30");
        return parseSearchPage(fetchSearchJson(uri, remainingBudget));
    }

    /**
     * 저장소 전체 Issue 수(PR 제외). {@code openOnly} 면 열려 있는 것만 센다(S15P21A506-413).
     *
     * <p>{@code per_page=1} 이라 본문은 작고, 필요한 것은 {@code total_count} 뿐이다. 이 값은 요약 수치 카드에 쓰이는 보조 정보라
     * **결과가 불완전({@code incomplete_results})하면 믿지 않고 {@code null}** 을 돌려준다 — 틀린 숫자를 보여주느니 비워 둔다.
     *
     * @throws GitHubRateLimitException search rate limit 소진
     * @throws UpstreamFetchException 그 외 통신 오류·byte 상한 초과·형식 오류
     */
    public Integer countIssues(String owner, String repo, boolean openOnly, Duration remainingBudget) {
        String query = "repo:" + owner + "/" + repo + " is:issue" + (openOnly ? " is:open" : "");
        URI uri =
                URI.create(
                        apiBase
                                + "/search/issues?q="
                                + URLEncoder.encode(query, StandardCharsets.UTF_8)
                                + "&per_page=1");
        JsonNode root;
        try {
            root = JSON.readTree(fetchSearchJson(uri, remainingBudget));
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub search 응답 JSON 파싱 실패", e);
        }
        if (root == null
                || !root.path("total_count").isIntegralNumber()
                || !root.path("total_count").canConvertToInt()
                || root.path("total_count").asInt(-1) < 0
                || !root.path("incomplete_results").isBoolean())
            throw new UpstreamFetchException("Invalid search count shape");
        if (root.path("incomplete_results").asBoolean(false)) return null;
        return root.path("total_count").asInt();
    }

    /** search 엔드포인트 하나를 호출해 본문 JSON 문자열을 돌려준다. rate limit·상태 코드·크기 상한을 여기서 한 번에 처리한다. */
    private String fetchSearchJson(URI uri, Duration remainingBudget) {
        rateGate.check("search");
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(uri)
                        .GET()
                        .timeout(clampTimeout(remainingBudget))
                        .header("Accept", "application/vnd.github+json")
                        .header("X-GitHub-Api-Version", API_VERSION);
        if (token != null && !token.isBlank()) {
            builder.header("Authorization", "Bearer " + token);
        }

        HttpResponse<InputStream> response;
        try {
            response =
                    BoundedHttpReader.send(
                            httpClient,
                            builder.build(),
                            maxResponseBytes,
                            info -> rateGate.observeHeaders("search", info));
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            rateGate.check("search");
            throw new UpstreamFetchException("GitHub search 통신 오류", e);
        }

        try (InputStream body = response.body()) {
            checkSearchRateLimit(response);
            if (response.statusCode() != 200) {
                throw new UpstreamFetchException("GitHub search 오류 상태: " + response.statusCode());
            }
            return BoundedHttpReader.readBounded(body, maxResponseBytes, "GitHub search");
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub search 응답 스트림 종료 오류", e);
        }
    }

    private void checkSearchRateLimit(HttpResponse<?> response) {
        rateGate.observe("search", response);
    }

    private SearchPage parseSearchPage(String json) {
        JsonNode root;
        try {
            root = JSON.readTree(json);
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub search 응답 JSON 파싱 실패", e);
        }

        if (root == null
                || !root.path("total_count").isIntegralNumber()
                || !root.path("incomplete_results").isBoolean()
                || !root.path("items").isArray())
            throw new UpstreamFetchException("Invalid search shape");
        int totalCount = root.path("total_count").asInt(-1);
        if (totalCount < 0 || root.path("items").size() > 30)
            throw new UpstreamFetchException("Invalid search counts");
        boolean incomplete = root.path("incomplete_results").asBoolean(false);

        List<SearchResultItem> items = new ArrayList<>();
        for (JsonNode item : root.path("items")) {
            if (!com.ssafy.pickage.domain.community.CommunitySnapshotValidator.decimalId(
                            item.path("id").asText())
                    || !item.path("number").canConvertToInt()
                    || item.path("number").asInt() <= 0
                    || !item.path("comments").canConvertToInt()
                    || item.path("comments").asInt() < 0
                    || !GitHubReactionCounts.isValidTotalCount(item)
                    || !java.util.Set.of("open", "closed").contains(item.path("state").asText())
                    || item.path("title").asText().isBlank())
                throw new UpstreamFetchException("Invalid search item");
            items.add(
                    new SearchResultItem(
                            item.path("number").asInt(),
                            item.path("title").asText(""),
                            item.path("state").asText(""),
                            parseInstant(
                                    item.path("updated_at").asText(), "search item updated_at"),
                            item.path("user").path("login").asText(null),
                            "Bot".equals(item.path("user").path("type").asText("")),
                            item.path("locked").asBoolean(false),
                            item.has("pull_request"),
                            item.path("comments").asInt(0),
                            item.path("reactions").path("total_count").asInt(0),
                            item.path("id").asText(),
                            parseInstant(item.path("created_at").asText(), "created_at"),
                            item.path("user").path("id").asText(null),
                            item.path("body").asText("")));
        }
        return new SearchPage(totalCount, incomplete, items);
    }

    /**
     * 리뷰에서 발견: {@code Instant.parse}를 그대로 쓰면 필드가 없거나(빈 문자열) 형식이 깨진 응답에서 {@code
     * DateTimeParseException}(unchecked)이 그대로 튀어나가 {@link IssueCollectionService}의 {@code
     * GitHubRateLimitException}/ {@code UpstreamFetchException} 처리를 우회해 전체 수집을 깨뜨린다. 이 필드는 GitHub
     * 응답의 형식을 신뢰할 수 없는 입력으로 다뤄 파싱 실패를 {@link UpstreamFetchException} (일시 실패, terminal 아님)으로 통일한다.
     */
    private static Instant parseInstant(String value, String fieldLabel) {
        try {
            return Instant.parse(value);
        } catch (java.time.format.DateTimeParseException e) {
            throw new UpstreamFetchException("GitHub search 응답의 " + fieldLabel + " 형식 오류", e);
        }
    }

    private static Duration clampTimeout(Duration remainingBudget) {
        Duration perCallCap = Duration.ofSeconds(10);
        return remainingBudget.compareTo(perCallCap) < 0 ? remainingBudget : perCallCap;
    }
}
