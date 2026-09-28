package com.ssafy.pickage.domain.features.dto;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

/**
 * 기능 비교 run 응답의 직렬화 (S15P21A506-429).
 *
 * <p><b>Jackson 3 로 시험한다.</b> 이 앱의 HTTP 응답을 쓰는 것이 Spring Boot 4 의 Jackson 3
 * 이기 때문이다. 이 버그는 Jackson 2 로 시험하면 <b>통과한다</b> — Jackson 2 는 자기
 * {@code JsonNode} 를 알아서 내용 그대로 쓴다. 운영에서만 {@code result} 가
 * {@code {"node_type":"OBJECT",...}} 로 나갔고, 프런트가 {@code result.packages} 에서 터졌다.
 *
 * <p>{@code application.yaml} 의 {@code spring.jackson.property-naming-strategy: SNAKE_CASE}
 * 만 옮겨 온다. 스프링 컨텍스트를 띄우지 않는 이유는 이 소스셋이 DB 없이 도는 단위 시험이라서다
 * ({@code build.gradle} "위치가 곧 분류다").
 */
class FeatureRunResponseJsonTest {

	private final JsonMapper mapper = JsonMapper.builder()
		.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
		.build();

	private static final String RAG = """
		{"dataStatus":"COMPLETE","packages":[{"package":"express","version":"5.2.1"}],\
		"common":"라우팅을 해요.","differences":[{"package":"express","version":"5.2.1","body":"미들웨어로 이어 붙여요."}],\
		"sources":[]}""";

	private static FeatureRunResponse completed(String result) {
		Instant t = Instant.parse("2026-09-21T00:00:00Z");
		return FeatureRunResponse.of("r1", "COMPLETED", "DONE", List.of("express@5.2.1"),
			t, t.plusSeconds(5), result, null, null);
	}

	@Test
	@DisplayName("RAG 결과를 내용 그대로 싣는다 — 트리 노드의 성질을 싣지 않는다")
	void resultIsPassedThrough() {
		String body = mapper.writeValueAsString(completed(RAG));

		assertThat(body)
			.contains("\"result\":{\"dataStatus\":\"COMPLETE\"")
			.contains("\"packages\":[{\"package\":\"express\"")
			.doesNotContain("node_type")
			.doesNotContain("container_node");
	}

	/** 계약 주인이 AI 쪽이라, 전역 SNAKE_CASE 가 결과 안의 이름까지 바꾸면 안 된다. */
	@Test
	@DisplayName("결과 안의 camelCase 이름을 바꾸지 않는다")
	void keepsCamelCaseInsideResult() {
		String body = mapper.writeValueAsString(completed(RAG));

		assertThat(body)
			.contains("\"dataStatus\"")
			.doesNotContain("data_status");
		// 바깥 봉투는 우리 규약(snake_case)을 따른다
		assertThat(body).contains("\"run_id\"").contains("\"elapsed_sec\":5");
	}

	@Test
	@DisplayName("결과가 없으면 null 로 나간다 — 빈 칸으로 JSON 을 깨지 않는다")
	void nullStaysValidJson() {
		Instant t = Instant.parse("2026-09-21T00:00:00Z");
		FeatureRunResponse running = FeatureRunResponse.of("r1", "RUNNING", "PREPARING_DOCS",
			List.of("express@5.2.1"), t, null, null, null, null);

		String body = mapper.writeValueAsString(running);

		assertThat(body).contains("\"result\":null").contains("\"error_detail\":null");
		// 다시 읽혀야 한다 — @JsonRawValue 가 빈 문자열을 넣으면 여기서 깨진다
		assertThat(mapper.readTree(body).get("result").isNull()).isTrue();
	}

	@Test
	@DisplayName("실패 사유도 원문 그대로 싣는다")
	void errorDetailIsPassedThrough() {
		Instant t = Instant.parse("2026-09-21T00:00:00Z");
		FeatureRunResponse failed = FeatureRunResponse.of("r1", "FAILED", "PREPARING_DOCS",
			List.of("express@5.2.1"), t, t, null, "DOC_NOT_FOUND", "[\"express@5.2.1\"]");

		String body = mapper.writeValueAsString(failed);

		assertThat(body).contains("\"error_detail\":[\"express@5.2.1\"]");
	}
}
