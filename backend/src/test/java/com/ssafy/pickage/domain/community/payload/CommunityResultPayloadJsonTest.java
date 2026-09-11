package com.ssafy.pickage.domain.community.payload;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;

/**
 * 이 파일은 {@code src/test}(DB·Spring 컨텍스트 없이 빠르게 도는 단위 시험)에 있으므로
 * {@code @SpringBootTest}로 실제 {@link ObjectMapper} 빈을 띄우지 않는다 — 그러면 이
 * 코드베이스의 test/integrationTest 소스셋 분리 원칙({@code build.gradle} "위치가 곧
 * 분류다")을 이 테스트 하나가 깨고, DB 가 없는 CI 잡에서 이 단위 시험까지 실패하게 된다.
 *
 * <p>대신 {@link ObjectMapper#findAndRegisterModules()}로 Spring Boot 의
 * {@code JacksonAutoConfiguration}과 같은 방식(서비스 로더로 {@code jackson-datatype-jsr310}
 * 등 클래스패스의 모듈을 자동 등록)으로 만들고, {@code application.yaml} 의
 * {@code spring.jackson.property-naming-strategy: SNAKE_CASE} 값만 그대로 옮겨 온다.
 * application.yaml 의 전략이 바뀌어도 이 값은 자동으로 따라가지 않는다 — 그건 이 단위 시험이
 * 감수하는 한계다.
 */
class CommunityResultPayloadJsonTest {

	private ObjectMapper objectMapper;

	@BeforeEach
	void setUp() {
		// CommunityConfig.communityObjectMapper() 와 반드시 같은 설정이어야 한다 — 여기서
		// 갈라지면 이 시험이 실제 운영 직렬화와 다른 것을 검증하게 된다.
		objectMapper = new ObjectMapper()
			.findAndRegisterModules()
			.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
			.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
	}

	@Test
	void 저장_payload는_전역_snake_case_규칙을_그대로_쓴다() throws Exception {
		CommunityResultPayload payload = samplePayload();

		String json = objectMapper.writeValueAsString(payload);

		assertThat(json)
			.contains("\"policy_version\"")
			.contains("\"lookback_days\"")
			.contains("\"summary_retry_at\"")
			.doesNotContain("\"policyVersion\"")
			.doesNotContain("\"lookbackDays\"");
	}

	@Test
	void 시각_필드는_epoch_숫자가_아니라_ISO_8601_문자열이다() throws Exception {
		// 리뷰에서 발견: plain new ObjectMapper() 는 WRITE_DATES_AS_TIMESTAMPS 가 기본
		// 켜짐이라 Instant 가 epoch 숫자로 나간다 — 구현계획 §API "필드 규약"(UTC ISO 8601 Z)
		// 위반. CommunityConfig.communityObjectMapper() 가 이걸 끄는지 이 시험이 지킨다.
		CommunityResultPayload payload = samplePayload();

		String json = objectMapper.writeValueAsString(payload);

		// epoch 숫자로 나갔다면 이 ISO 문자열 자체가 JSON 어디에도 나타나지 않는다 —
		// 숫자 값을 직접 계산해 doesNotContain 하는 것보다 이 쪽이 더 확실하다.
		assertThat(json).contains("\"2025-10-05T07:25:06Z\"");
	}

	@Test
	void 직렬화_후_역직렬화하면_원래_값과_같다() throws Exception {
		CommunityResultPayload payload = samplePayload();

		String json = objectMapper.writeValueAsString(payload);
		CommunityResultPayload restored = objectMapper.readValue(json, CommunityResultPayload.class);

		assertThat(restored).isEqualTo(payload);
	}

	@Test
	void 대표_메시지의_재시작_복원용_필드가_모두_보존된다() throws Exception {
		// Jira S15P21A506-314 세부 항목: source_issue_id/source_comment_id/association/
		// is_issue_author 를 typed JSON 에 보존해 재시작 후 복원한다.
		CommunityResultPayload payload = samplePayload();

		String json = objectMapper.writeValueAsString(payload);
		CommunityResultPayload restored = objectMapper.readValue(json, CommunityResultPayload.class);

		MessagePayload originalMessage = payload.topics().getFirst().messages().getFirst();
		MessagePayload restoredMessage = restored.topics().getFirst().messages().getFirst();

		assertThat(restoredMessage.sourceIssueId()).isEqualTo(originalMessage.sourceIssueId());
		assertThat(restoredMessage.sourceCommentId()).isEqualTo(originalMessage.sourceCommentId());
		assertThat(restoredMessage.association()).isEqualTo(originalMessage.association());
		assertThat(restoredMessage.isIssueAuthor()).isEqualTo(originalMessage.isIssueAuthor());
	}

	private static CommunityResultPayload samplePayload() {
		MessagePayload message = new MessagePayload(
			"2272", "3368825804", "mcollina", "ORGANIZATION_MEMBER", false,
			"NORMAL", Instant.parse("2025-10-05T07:25:06Z"),
			"worker thread에서 모듈을 불러오는 제약을 설명합니다.");

		DiscussionStepPayload step = new DiscussionStepPayload(1, "Node.js와 worker thread 제약을 확인했습니다.");

		TopicPayload topic = new TopicPayload(
			2272, "OPEN", Instant.parse("2026-05-15T10:55:48Z"),
			"[Feature Request] Can pass a module NOT STRING to pino transport target?",
			"transport target에 모듈을 직접 전달할 수 있을까?",
			30, 3, "COMPLETE", "READY",
			"transport target의 모듈 전달과 번들러 호환성에 관한 논의입니다.",
			List.of(step), List.of(message));

		RepositoryPayload repository = new RepositoryPayload("pinojs/pino", "PACKAGE_SCOPED");

		return new CommunityResultPayload(repository, 1, 180, null, List.of(topic), List.of());
	}
}
