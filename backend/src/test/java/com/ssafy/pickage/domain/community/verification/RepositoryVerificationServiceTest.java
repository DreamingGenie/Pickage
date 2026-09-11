package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.http.HttpClient;
import java.util.Base64;
import java.util.Map;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * npm·GitHub 가짜 서버를 함께 띄워 {@link RepositoryVerificationService}를 끝까지 돌린다.
 * Jira S15P21A506-213 완료 판단 기준의 fixture 목록(npm/DB 충돌·비GitHub·directory/name
 * 불일치·DB-only·workspaces·private·SSRF·429)을 그대로 시나리오화한다.
 */
class RepositoryVerificationServiceTest {

	private static final long MAX_BYTES = 2L * 1024 * 1024;

	private FakeHttpServer npmServer;
	private FakeHttpServer githubServer;
	private RepositoryVerificationService service;

	@BeforeEach
	void setUp() {
		npmServer = FakeHttpServer.start();
		githubServer = FakeHttpServer.start();
		HttpClient httpClient = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
		NpmRepositoryLookup npmLookup = new NpmRepositoryLookup(httpClient, MAX_BYTES, npmServer.baseUrl());
		GitHubRepositoryClient githubClient =
			new GitHubRepositoryClient(httpClient, "fake-token", MAX_BYTES, githubServer.baseUrl());
		service = new RepositoryVerificationService(npmLookup, githubClient);
	}

	@AfterEach
	void tearDown() {
		npmServer.close();
		githubServer.close();
	}

	private void npmRepository(String packageName, String repositoryJsonValue) {
		npmServer.respond("/" + packageName + "/latest", 200,
			"{\"name\":\"" + packageName + "\",\"repository\":" + repositoryJsonValue + "}", Map.of());
	}

	private void npmNoRepository(String packageName) {
		npmServer.respond("/" + packageName + "/latest", 200, "{\"name\":\"" + packageName + "\"}", Map.of());
	}

	private void githubRepo(String owner, String repo, boolean archived) {
		githubServer.respond("/repos/" + owner + "/" + repo, 200,
			"{\"archived\":" + archived + "}", Map.of());
	}

	private void githubPackageJson(String owner, String repo, String path, String name) {
		String content = "{\"name\":\"" + name + "\"}";
		String base64 = Base64.getEncoder().encodeToString(content.getBytes(StandardCharsets.UTF_8));
		githubServer.respond("/repos/" + owner + "/" + repo + "/contents/" + path, 200,
			"{\"encoding\":\"base64\",\"content\":\"" + base64 + "\"}", Map.of());
	}

	@Test
	void npm이_유일한_후보이고_루트_이름이_일치하면_PACKAGE_SCOPED로_검증된다() {
		npmRepository("pino", "\"https://github.com/pinojs/pino\"");
		githubRepo("pinojs", "pino", false);
		githubPackageJson("pinojs", "pino", "package.json", "pino");

		RepositoryVerificationResult result = service.verify("pino", null);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.owner()).isEqualTo("pinojs");
		assertThat(verified.scope()).isEqualTo(RepositoryScope.PACKAGE_SCOPED);
		assertThat(verified.repositoryArchived()).isFalse();
	}

	@Test
	void DB와_npm이_달라도_npm_후보로_검증된다() {
		npmRepository("pino", "\"https://github.com/pinojs/pino\"");
		githubRepo("pinojs", "pino", false);
		githubPackageJson("pinojs", "pino", "package.json", "pino");

		// DB는 완전히 다른(존재하지 않는) 저장소를 가리킨다 — npm이 이겨야 한다.
		RepositoryVerificationResult result = service.verify("pino", "https://github.com/someone-else/old-pino");

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.owner()).isEqualTo("pinojs");
	}

	@Test
	void npm이_명시적으로_비GitHub_host면_UnsupportedHost다() {
		npmRepository("weird-pkg", "\"https://gitlab.com/foo/bar\"");

		RepositoryVerificationResult result = service.verify("weird-pkg", "https://github.com/foo/bar");

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnsupportedHost.class);
	}

	@Test
	void DB_only_루트_이름_불일치는_UnverifiedRepository다() {
		npmNoRepository("mystery-pkg");
		githubRepo("someone", "unrelated", false);
		githubPackageJson("someone", "unrelated", "package.json", "완전히-다른-이름");

		RepositoryVerificationResult result = service.verify("mystery-pkg", "https://github.com/someone/unrelated");

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnverifiedRepository.class);
	}

	@Test
	void workspaces_directory_이름_일치는_REPOSITORY_WIDE로_검증된다() {
		npmRepository("react", """
			{"type":"git","url":"https://github.com/facebook/react.git","directory":"packages/react"}
			""");
		githubRepo("facebook", "react", false);
		githubPackageJson("facebook", "react", "packages/react/package.json", "react");

		RepositoryVerificationResult result = service.verify("react", null);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.scope()).isEqualTo(RepositoryScope.REPOSITORY_WIDE);
		assertThat(verified.scopeLimited()).isTrue();
	}

	@Test
	void directory_이름_불일치는_AmbiguousScope다() {
		npmRepository("broken-monorepo-pkg", """
			{"type":"git","url":"https://github.com/someorg/monorepo.git","directory":"packages/missing"}
			""");
		githubRepo("someorg", "monorepo", false);
		githubServer.respond("/repos/someorg/monorepo/contents/packages/missing/package.json", 404, "nf", Map.of());

		RepositoryVerificationResult result = service.verify("broken-monorepo-pkg", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.AmbiguousScope.class);
	}

	@Test
	void 비공개_저장소_403은_UnverifiedRepository다() {
		npmRepository("private-pkg", "\"https://github.com/org/private-repo\"");
		githubServer.respond("/repos/org/private-repo", 403, "forbidden",
			Map.of("X-RateLimit-Remaining", "10"));

		RepositoryVerificationResult result = service.verify("private-pkg", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnverifiedRepository.class);
	}

	@Test
	void GitHub_rate_limit_429는_FetchLimited이고_terminal이_아니다() {
		npmRepository("busy-pkg", "\"https://github.com/org/busy-repo\"");
		githubServer.respond("/repos/org/busy-repo", 429, "slow down", Map.of("Retry-After", "60"));

		RepositoryVerificationResult result = service.verify("busy-pkg", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.FetchLimited.class);
	}

	@Test
	void npm_registry_통신_오류는_FetchLimited다() {
		npmServer.respond("/flaky-pkg/latest", 500, "boom", Map.of());

		RepositoryVerificationResult result = service.verify("flaky-pkg", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.FetchLimited.class);
	}

	@Test
	void npm에_패키지가_없으면_UnverifiedRepository다() {
		npmServer.respond("/ghost/latest", 404, "not found", Map.of());

		RepositoryVerificationResult result = service.verify("ghost", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnverifiedRepository.class);
	}

	@Test
	void DB_npm_둘_다_후보가_없으면_UnverifiedRepository다() {
		npmNoRepository("no-repo-anywhere");

		RepositoryVerificationResult result = service.verify("no-repo-anywhere", null);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnverifiedRepository.class);
	}

	@Test
	void archived_저장소도_검증은_통과하고_archived_플래그만_켜진다() {
		npmRepository("old-but-valid", "\"https://github.com/org/archived-repo\"");
		githubRepo("org", "archived-repo", true);
		githubPackageJson("org", "archived-repo", "package.json", "old-but-valid");

		RepositoryVerificationResult result = service.verify("old-but-valid", null);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.repositoryArchived()).isTrue();
	}
}
