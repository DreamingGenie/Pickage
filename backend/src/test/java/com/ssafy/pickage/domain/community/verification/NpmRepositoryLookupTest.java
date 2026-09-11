package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.http.HttpClient;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class NpmRepositoryLookupTest {

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

	private NpmRepositoryLookup lookup(long maxBytes) {
		return new NpmRepositoryLookup(httpClient, maxBytes, server.baseUrl());
	}

	@Test
	void repository가_문자열이면_그대로_읽는다() {
		server.respond("/pino/latest", 200,
			"{\"name\":\"pino\",\"repository\":\"github:pinojs/pino\"}", Map.of());

		NpmLookupOutcome outcome = lookup(MAX_BYTES).fetchRepositoryField("pino");

		assertThat(outcome).isInstanceOf(NpmLookupOutcome.Found.class);
		assertThat(((NpmLookupOutcome.Found) outcome).rawRepositoryUrl()).isEqualTo("github:pinojs/pino");
	}

	@Test
	void repository가_객체면_url과_directory를_읽는다() {
		server.respond("/react/latest", 200, """
			{"name":"react","repository":{"type":"git","url":"https://github.com/facebook/react.git","directory":"packages/react"}}
			""", Map.of());

		NpmLookupOutcome outcome = lookup(MAX_BYTES).fetchRepositoryField("react");

		var found = (NpmLookupOutcome.Found) outcome;
		assertThat(found.rawRepositoryUrl()).isEqualTo("https://github.com/facebook/react.git");
		assertThat(found.directory()).isEqualTo("packages/react");
	}

	@Test
	void repository_필드가_없으면_NoRepositoryField다() {
		server.respond("/no-repo/latest", 200, "{\"name\":\"no-repo\"}", Map.of());

		NpmLookupOutcome outcome = lookup(MAX_BYTES).fetchRepositoryField("no-repo");

		assertThat(outcome).isInstanceOf(NpmLookupOutcome.NoRepositoryField.class);
	}

	@Test
	void HTTP_404는_NotFound다() {
		server.respond("/ghost-package/latest", 404, "not found", Map.of());

		NpmLookupOutcome outcome = lookup(MAX_BYTES).fetchRepositoryField("ghost-package");

		assertThat(outcome).isInstanceOf(NpmLookupOutcome.NotFound.class);
	}

	@Test
	void 그_외_오류_상태는_UpstreamFetchException이다() {
		server.respond("/broken/latest", 500, "boom", Map.of());

		assertThatThrownBy(() -> lookup(MAX_BYTES).fetchRepositoryField("broken"))
			.isInstanceOf(UpstreamFetchException.class);
	}

	@Test
	void 응답이_상한을_넘으면_UpstreamFetchException이다() {
		String hugeBody = "{\"name\":\"huge\",\"repository\":\"" + "x".repeat(200) + "\"}";
		server.respond("/huge/latest", 200, hugeBody, Map.of());

		// 일부러 아주 작은 상한을 줘서(사용자 승인 §7의 "일부러 낮춘 byte 상한" 아이디어와
		// 같은 방식) 이 메커니즘 자체를 확실히 트립시킨다.
		assertThatThrownBy(() -> lookup(50).fetchRepositoryField("huge"))
			.isInstanceOf(UpstreamFetchException.class)
			.hasMessageContaining("상한");
	}

	@Test
	void 스코프_패키지_이름의_슬래시를_인코딩한다() {
		// URLEncoder.encode("@scope/name", UTF_8) == "%40scope%2Fname" 로 요청은 나가지만,
		// com.sun.net.httpserver 의 컨텍스트 매칭은 디코드된 경로 기준이라 등록은 원문으로 한다.
		server.respond("/@scope/name/latest", 200,
			"{\"name\":\"@scope/name\",\"repository\":\"https://github.com/scope/name\"}", Map.of());

		NpmLookupOutcome outcome = lookup(MAX_BYTES).fetchRepositoryField("@scope/name");

		assertThat(outcome).isInstanceOf(NpmLookupOutcome.Found.class);
	}
}
