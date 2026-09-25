package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.http.HttpClient;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/**
 * 실제 {@code registry.npmjs.org}·{@code api.github.com}을 호출한다. 269
 * ({@code pipeline/snapshot/test_integration.py})가 {@code PICKAGE_SNAPSHOT_TEST_CONTAINER}
 * 환경변수로 없으면 건너뛰는 것과 같은 패턴 — 토큰이 없는 환경(CI·다른 팀원)에서는 자동으로
 * skip된다.
 *
 * <p>실행: {@code GITHUB_COMMUNITY_TOKEN=<발급받은 토큰> ./gradlew integrationTest --tests
 * "*.RepositoryVerificationRealNetworkTest"}
 *
 * <p>Spec {@code docs/history/0923_0917_pickage_final_set_archive/for_community/specs/S15P21A506-213.md} §7 — 사용자가 실제 토큰으로
 * (1) 정상 검증 경로와 (2) 일부러 낮춘 byte 상한이 실제 응답을 끊는지를 함께 확인하기 위한
 * 시험이다.
 */
@EnabledIfEnvironmentVariable(named = "GITHUB_COMMUNITY_TOKEN", matches = ".+")
class RepositoryVerificationRealNetworkTest {

	private static final long NORMAL_MAX_BYTES = 2L * 1024 * 1024;
	private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
		.followRedirects(HttpClient.Redirect.NEVER)
		.build();

	private static String token() {
		return System.getenv("GITHUB_COMMUNITY_TOKEN");
	}

	@Test
	void pino의_실제_저장소_연결을_검증한다() {
		NpmRepositoryLookup npmLookup = new NpmRepositoryLookup(HTTP_CLIENT, NORMAL_MAX_BYTES);
		GitHubRepositoryClient githubClient = new GitHubRepositoryClient(HTTP_CLIENT, token(), NORMAL_MAX_BYTES);
		RepositoryVerificationService service = new RepositoryVerificationService(npmLookup, githubClient);

		RepositoryVerificationResult result = service.verify("pino", null);

		System.out.println("[실네트워크 검증 결과] " + result);
		assertThat(result)
			.as("pino는 실제로 존재하는 GitHub 저장소로 검증돼야 한다 — 결과: %s", result)
			.isInstanceOf(RepositoryVerificationResult.Verified.class);
		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.owner()).isEqualToIgnoringCase("pinojs");
		assertThat(verified.repo()).isEqualToIgnoringCase("pino");
	}

	@Test
	void 일부러_낮춘_byte_상한이_실제_npm_응답에서도_동작한다() {
		// 2026-09-11 사용자 승인 §7 — "일부러 낮춘 byte 상한으로 실제 응답을 끊는 경로"를
		// 이 시험이 확인한다. 100 bytes 는 어떤 정상 npm latest 응답보다도 작다.
		NpmRepositoryLookup tightLimit = new NpmRepositoryLookup(HTTP_CLIENT, 100);

		assertThatThrownBy(() -> tightLimit.fetchRepositoryField("pino"))
			.isInstanceOf(UpstreamFetchException.class)
			.hasMessageContaining("상한");
	}

	@Test
	void 일부러_낮춘_byte_상한이_실제_GitHub_응답에서도_동작한다() {
		GitHubRepositoryClient tightLimit = new GitHubRepositoryClient(HTTP_CLIENT, token(), 50);

		assertThatThrownBy(() -> tightLimit.isArchived("pinojs", "pino"))
			.isInstanceOf(UpstreamFetchException.class)
			.hasMessageContaining("상한");
	}
}
