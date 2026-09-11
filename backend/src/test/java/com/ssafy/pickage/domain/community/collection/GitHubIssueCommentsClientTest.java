package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.verification.FakeHttpServer;
import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

class GitHubIssueCommentsClientTest {

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

	private GitHubIssueCommentsClient client() {
		return new GitHubIssueCommentsClient(httpClient, "fake-token", MAX_BYTES, server.baseUrl());
	}

	private static String commentsJson(int... ids) {
		StringBuilder sb = new StringBuilder("[");
		for (int i = 0; i < ids.length; i++) {
			if (i > 0) sb.append(',');
			sb.append("""
				{"id": %d, "user": {"login": "u", "type": "User"},
				 "author_association": "NONE", "created_at": "2026-01-01T00:00:00Z", "body": "hi"}
				""".formatted(ids[i]));
		}
		return sb.append(']').toString();
	}

	@Test
	void Link_헤더가_없으면_요청한_page를_마지막으로_본다() {
		server.respond("/repos/o/r/issues/1/comments", 200, commentsJson(1, 2, 3), Map.of());

		CommentsPage page = client().fetchPage("o", "r", 1, 1, BUDGET);

		assertThat(page.comments()).hasSize(3);
		assertThat(page.lastPageNumber()).isEqualTo(1);
	}

	@Test
	void Link_헤더의_rel_last에서_마지막_page_번호를_읽는다() {
		server.respond("/repos/o/r/issues/1/comments", 200, commentsJson(1, 2), Map.of(
			"Link", "<https://api.github.com/repos/o/r/issues/1/comments?page=2>; rel=\"next\", "
				+ "<https://api.github.com/repos/o/r/issues/1/comments?page=5>; rel=\"last\""));

		assertThat(client().fetchPage("o", "r", 1, 1, BUDGET).lastPageNumber()).isEqualTo(5);
	}

	@Test
	void id를_십진_문자열로_보존한다() {
		server.respond("/repos/o/r/issues/1/comments", 200,
			"[{\"id\": 9223372036854775807, \"user\": {\"login\": \"u\", \"type\": \"User\"}, "
				+ "\"author_association\": \"NONE\", \"created_at\": \"2026-01-01T00:00:00Z\", \"body\": \"hi\"}]",
			Map.of());

		assertThat(client().fetchPage("o", "r", 1, 1, BUDGET).comments().getFirst().sourceCommentId())
			.isEqualTo("9223372036854775807");
	}

	@Test
	void remaining_0인_403은_rate_limit_예외다() {
		server.respond("/repos/o/r/issues/1/comments", 403, "rate limited",
			Map.of("X-RateLimit-Remaining", "0"));

		assertThatThrownBy(() -> client().fetchPage("o", "r", 1, 1, BUDGET))
			.isInstanceOf(GitHubRateLimitException.class);
	}

	@Test
	void 그_외_오류_상태는_UpstreamFetchException이다() {
		server.respond("/repos/o/r/issues/1/comments", 500, "boom", Map.of());

		assertThatThrownBy(() -> client().fetchPage("o", "r", 1, 1, BUDGET))
			.isInstanceOf(UpstreamFetchException.class);
	}

	/**
	 * 리뷰에서 발견 — {@code id}가 없거나 숫자가 아니면 이전에는 검증되지 않은 채
	 * {@code CommentWindowResolver.selectLatest}까지 흘러가 {@code NumberFormatException}
	 * (unchecked)으로 전체 수집을 깨뜨렸다. 이제 이 경계에서 {@link UpstreamFetchException}
	 * 으로 통일해, {@code IssueCollectionService.collectIssue}의 기존 격리(TRUNCATED/FAILED)
	 * 가 정상 작동하게 한다.
	 */
	@Test
	void id가_없으면_UpstreamFetchException이다() {
		server.respond("/repos/o/r/issues/1/comments", 200,
			"[{\"user\": {\"login\": \"u\", \"type\": \"User\"}, "
				+ "\"author_association\": \"NONE\", \"created_at\": \"2026-01-01T00:00:00Z\", \"body\": \"hi\"}]",
			Map.of());

		assertThatThrownBy(() -> client().fetchPage("o", "r", 1, 1, BUDGET))
			.isInstanceOf(UpstreamFetchException.class);
	}
}
