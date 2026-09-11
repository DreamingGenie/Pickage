package com.ssafy.pickage.domain.community.collection;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.verification.BoundedHttpReader;
import com.ssafy.pickage.domain.community.verification.GitHubRateGate;
import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigInteger;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 이슈 하나의 댓글 한 page만 가져온다(core rate limit 공유 — 213의 {@code GitHubRepositoryClient}와 같은 quota지만,
 * private 메서드라 코드는 재사용하지 않는다. §2 결정 참고). 어떤 page를 부를지는 이 클래스가 정하지 않는다 — {@link
 * CommentWindowResolver}·{@link IssueCollectionService}의 몫이다.
 */
public class GitHubIssueCommentsClient {

    private static final String REAL_API_BASE = "https://api.github.com";
    private static final String API_VERSION = "2026-03-10";
    private static final int PAGE_SIZE = 100;
    private static final Pattern LAST_PAGE_LINK =
            Pattern.compile("[?&]page=(\\d+)[^>]*>;\\s*rel=\"last\"");
    private static final ObjectMapper JSON = new ObjectMapper();

    private final HttpClient httpClient;
    private GitHubRateGate rateGate = new GitHubRateGate();

    public void setRateGate(GitHubRateGate gate) {
        this.rateGate = java.util.Objects.requireNonNull(gate);
    }

    private final String token;
    private final long maxResponseBytes;
    private final String apiBase;

    public GitHubIssueCommentsClient(HttpClient httpClient, String token, long maxResponseBytes) {
        this(httpClient, token, maxResponseBytes, REAL_API_BASE);
    }

    /** 시험 전용 — 가짜 서버를 향하게 한다. */
    GitHubIssueCommentsClient(
            HttpClient httpClient, String token, long maxResponseBytes, String apiBase) {
        this.httpClient = httpClient;
        this.token = token;
        this.maxResponseBytes = maxResponseBytes;
        this.apiBase = apiBase;
    }

    /**
     * @param remainingBudget 이 호출에 쓸 수 있는 남은 시간(2026-09-11 사용자 결정 — 필수 매개변수, 기본값 없음)
     * @throws GitHubRateLimitException core rate limit 소진
     * @throws UpstreamFetchException 그 외 통신 오류·byte 상한 초과
     */
    public CommentsPage fetchPage(
            String owner, String repo, int issueNumber, int page, Duration remainingBudget) {
        URI uri =
                URI.create(
                        apiBase
                                + "/repos/"
                                + owner
                                + "/"
                                + repo
                                + "/issues/"
                                + issueNumber
                                + "/comments?per_page="
                                + PAGE_SIZE
                                + "&page="
                                + page);

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

        HttpResponse<InputStream> response;
        try {
            response = BoundedHttpReader.send(httpClient, builder.build(), maxResponseBytes);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new UpstreamFetchException("GitHub comments 통신 오류", e);
        }

        try (InputStream body = response.body()) {
            checkRateLimit(response);
            if (response.statusCode() != 200) {
                throw new UpstreamFetchException("GitHub comments 오류 상태: " + response.statusCode());
            }
            String json = BoundedHttpReader.readBounded(body, maxResponseBytes, "GitHub comments");
            int lastPage = parseLastPageNumber(response, page);
            return new CommentsPage(parseComments(json), lastPage);
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub comments 응답 스트림 종료 오류", e);
        }
    }

    private void checkRateLimit(HttpResponse<?> response) {
        rateGate.observe("core", response);
    }

    /** {@code Link} 헤더에 {@code rel="last"}가 없으면 이 page가 마지막이라는 뜻이다. */
    private int parseLastPageNumber(HttpResponse<?> response, int requestedPage) {
        String link = response.headers().firstValue("Link").orElse(null);
        if (link == null) {
            return requestedPage;
        }
        Matcher matcher = LAST_PAGE_LINK.matcher(link);
        try {
            int last = matcher.find() ? Integer.parseInt(matcher.group(1)) : requestedPage;
            if (last < requestedPage)
                throw new UpstreamFetchException("Invalid comment pagination");
            return last;
        } catch (NumberFormatException e) {
            throw new UpstreamFetchException("Invalid comment pagination");
        }
    }

    private List<CollectedComment> parseComments(String json) {
        JsonNode array;
        try {
            array = JSON.readTree(json);
        } catch (IOException e) {
            throw new UpstreamFetchException("GitHub comments 응답 JSON 파싱 실패", e);
        }

        if (array == null || !array.isArray() || array.size() > 100)
            throw new UpstreamFetchException("Invalid comments shape");
        List<CollectedComment> comments = new ArrayList<>();
        for (JsonNode node : array) {
            comments.add(
                    new CollectedComment(
                            parseCommentId(node),
                            node.path("user").path("login").asText(null),
                            node.path("user").isNull()
                                    ? null
                                    : node.path("author_association").asText("NONE"),
                            "Bot".equals(node.path("user").path("type").asText("")),
                            parseInstant(node.path("created_at").asText(), "comment created_at"),
                            node.path("body").asText(""),
                            node.path("user").path("id").asText(null)));
        }
        return comments;
    }

    /**
     * {@link CommentWindowResolver#selectLatest}가 이 값을 {@link BigInteger}로 비교하므로 여기서 미리 검증한다 — 검증
     * 없이 넘기면 {@code id}가 없거나(빈 문자열) 숫자가 아닐 때 {@code NumberFormatException}(unchecked)이 이슈 단위 격리를
     * 건너뛰고 전체 수집을 깨뜨린다(리뷰에서 발견). {@link #parseInstant}와 같은 이유로 여기서 {@link UpstreamFetchException}으로
     * 통일한다 — 그러면 {@code collectIssue}의 기존 try/catch가 이 이슈만 TRUNCATED/FAILED로 격리한다.
     */
    private static String parseCommentId(JsonNode node) {
        String id = node.path("id").asText("");
        try {
            if (!com.ssafy.pickage.domain.community.CommunitySnapshotValidator.decimalId(id))
                throw new NumberFormatException();
        } catch (NumberFormatException e) {
            throw new UpstreamFetchException("GitHub comments 응답의 id 형식 오류");
        }
        return id;
    }

    /** {@link GitHubIssueSearchClient#parseInstant}와 같은 이유(리뷰에서 발견). */
    private static Instant parseInstant(String value, String fieldLabel) {
        try {
            return Instant.parse(value);
        } catch (java.time.format.DateTimeParseException e) {
            throw new UpstreamFetchException("GitHub comments 응답의 " + fieldLabel + " 형식 오류", e);
        }
    }

    private static Duration clampTimeout(Duration remainingBudget) {
        Duration perCallCap = Duration.ofSeconds(10);
        return remainingBudget.compareTo(perCallCap) < 0 ? remainingBudget : perCallCap;
    }
}
