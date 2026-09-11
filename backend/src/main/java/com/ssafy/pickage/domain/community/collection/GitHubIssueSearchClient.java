package com.ssafy.pickage.domain.community.collection;

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

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.verification.BoundedHttpReader;
import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

/**
 * {@code GET /search/issues}만 호출하는 좁은 클라이언트(github-active-v1 정책의 원천 조회).
 *
 * <p>Search API는 core API(213의 {@link com.ssafy.pickage.domain.community.verification.GitHubRepositoryClient})와
 * <b>별도 rate limit quota</b>다(비인증 10/분, 인증 30/분 — 구현계획 §설정과 보안). 그래서
 * {@code send()}/rate-limit 판정 코드를 213에서 가져다 쓰지 않고 이 클래스 안에 다시
 * 작게 둔다 — 이미 병합·리뷰된 213 파일은 건드리지 않는다는 2026-09-11 사용자 결정
 * ({@code docs/for_community/specs/S15P21A506-212.md} §7).
 */
public class GitHubIssueSearchClient {

	private static final String REAL_API_BASE = "https://api.github.com";
	private static final String API_VERSION = "2026-03-10";
	private static final DateTimeFormatter DATE_FORMAT = DateTimeFormatter.ISO_LOCAL_DATE;
	private static final ObjectMapper JSON = new ObjectMapper();

	private final HttpClient httpClient;
	private final String token;
	private final long maxResponseBytes;
	private final String apiBase;

	public GitHubIssueSearchClient(HttpClient httpClient, String token, long maxResponseBytes) {
		this(httpClient, token, maxResponseBytes, REAL_API_BASE);
	}

	/** 시험 전용 — 가짜 서버를 향하게 한다. */
	GitHubIssueSearchClient(HttpClient httpClient, String token, long maxResponseBytes, String apiBase) {
		this.httpClient = httpClient;
		this.token = token;
		this.maxResponseBytes = maxResponseBytes;
		this.apiBase = apiBase;
	}

	/**
	 * @param lookbackDays  180 또는 365(raw 0일 때 한 번 확장 — 호출자가 결정해 넘긴다)
	 * @param remainingBudget 이 호출에 쓸 수 있는 남은 시간. Phase 4가 생기기 전까지는
	 *                         호출자가 직접 정해서 넘긴다(2026-09-11 사용자 결정, §7)
	 * @throws GitHubRateLimitException search rate limit 소진
	 * @throws UpstreamFetchException   그 외 통신 오류·byte 상한 초과
	 */
	public SearchPage searchActiveIssues(String owner, String repo, int lookbackDays, Duration remainingBudget) {
		String since = LocalDate.now(ZoneOffset.UTC).minusDays(lookbackDays).format(DATE_FORMAT);
		String query = "repo:" + owner + "/" + repo + " is:issue updated:>=" + since;
		URI uri = URI.create(apiBase + "/search/issues?q="
			+ URLEncoder.encode(query, StandardCharsets.UTF_8)
			+ "&sort=comments&order=desc&per_page=30");

		HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
			.GET()
			.timeout(clampTimeout(remainingBudget))
			.header("Accept", "application/vnd.github+json")
			.header("X-GitHub-Api-Version", API_VERSION);
		if (token != null && !token.isBlank()) {
			builder.header("Authorization", "Bearer " + token);
		}

		HttpResponse<InputStream> response;
		try {
			response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
		} catch (IOException | InterruptedException e) {
			if (e instanceof InterruptedException) {
				Thread.currentThread().interrupt();
			}
			throw new UpstreamFetchException("GitHub search 통신 오류", e);
		}

		try (InputStream body = response.body()) {
			checkSearchRateLimit(response);
			if (response.statusCode() != 200) {
				throw new UpstreamFetchException("GitHub search 오류 상태: " + response.statusCode());
			}
			String json = BoundedHttpReader.readBounded(body, maxResponseBytes, "GitHub search");
			return parseSearchPage(json);
		} catch (IOException e) {
			throw new UpstreamFetchException("GitHub search 응답 스트림 종료 오류", e);
		}
	}

	private void checkSearchRateLimit(HttpResponse<?> response) {
		int status = response.statusCode();
		if (status != 403 && status != 429) {
			return;
		}
		String remaining = response.headers().firstValue("X-RateLimit-Remaining").orElse(null);
		boolean exhausted = "0".equals(remaining);
		boolean hasRetryAfter = response.headers().firstValue("Retry-After").isPresent();

		if (status == 429 || exhausted || hasRetryAfter) {
			Instant retryAt = response.headers().firstValueAsLong("Retry-After")
				.stream().mapToObj(seconds -> Instant.now().plusSeconds(seconds))
				.findFirst()
				.or(() -> response.headers().firstValueAsLong("X-RateLimit-Reset")
					.stream().mapToObj(Instant::ofEpochSecond)
					.findFirst())
				.orElse(null);
			throw new GitHubRateLimitException("GitHub search rate limit", retryAt);
		}
	}

	private SearchPage parseSearchPage(String json) {
		JsonNode root;
		try {
			root = JSON.readTree(json);
		} catch (IOException e) {
			throw new UpstreamFetchException("GitHub search 응답 JSON 파싱 실패", e);
		}

		int totalCount = root.path("total_count").asInt(0);
		boolean incomplete = root.path("incomplete_results").asBoolean(false);

		List<SearchResultItem> items = new ArrayList<>();
		for (JsonNode item : root.path("items")) {
			items.add(new SearchResultItem(
				item.path("number").asInt(),
				item.path("title").asText(""),
				item.path("state").asText(""),
				parseInstant(item.path("updated_at").asText(), "search item updated_at"),
				item.path("user").path("login").asText(""),
				"Bot".equals(item.path("user").path("type").asText("")),
				item.path("locked").asBoolean(false),
				item.has("pull_request"),
				item.path("comments").asInt(0),
				item.path("reactions").path("total_count").asInt(0)));
		}
		return new SearchPage(totalCount, incomplete, items);
	}

	/**
	 * 리뷰에서 발견: {@code Instant.parse}를 그대로 쓰면 필드가 없거나(빈 문자열) 형식이
	 * 깨진 응답에서 {@code DateTimeParseException}(unchecked)이 그대로 튀어나가
	 * {@link IssueCollectionService}의 {@code GitHubRateLimitException}/
	 * {@code UpstreamFetchException} 처리를 우회해 전체 수집을 깨뜨린다. 이 필드는 GitHub
	 * 응답의 형식을 신뢰할 수 없는 입력으로 다뤄 파싱 실패를 {@link UpstreamFetchException}
	 * (일시 실패, terminal 아님)으로 통일한다.
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
