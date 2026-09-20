package com.ssafy.pickage.domain.community.payload;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;

import com.ssafy.pickage.domain.community.CommunitySnapshotPayloadException;
import com.ssafy.pickage.domain.community.CommunitySnapshotValidator;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

/**
 * 이 파일은 {@code src/test}(DB·Spring 컨텍스트 없이 빠르게 도는 단위 시험)에 있으므로 {@code @SpringBootTest}로 실제 {@link
 * ObjectMapper} 빈을 띄우지 않는다 — 그러면 이 코드베이스의 test/integrationTest 소스셋 분리 원칙({@code build.gradle} "위치가
 * 곧 분류다")을 이 테스트 하나가 깨고, DB 가 없는 CI 잡에서 이 단위 시험까지 실패하게 된다.
 *
 * <p>대신 {@link ObjectMapper#findAndRegisterModules()}로 Spring Boot 의 {@code
 * JacksonAutoConfiguration}과 같은 방식(서비스 로더로 {@code jackson-datatype-jsr310} 등 클래스패스의 모듈을 자동 등록)으로
 * 만들고, {@code application.yaml} 의 {@code spring.jackson.property-naming-strategy: SNAKE_CASE} 값만
 * 그대로 옮겨 온다. application.yaml 의 전략이 바뀌어도 이 값은 자동으로 따라가지 않는다 — 그건 이 단위 시험이 감수하는 한계다.
 */
class CommunityResultPayloadJsonTest {

    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        // CommunityConfig.communityObjectMapper() 와 반드시 같은 설정이어야 한다 — 여기서
        // 갈라지면 이 시험이 실제 운영 직렬화와 다른 것을 검증하게 된다.
        objectMapper =
                new ObjectMapper()
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
        CommunityResultPayload restored =
                objectMapper.readValue(json, CommunityResultPayload.class);

        assertThat(restored).isEqualTo(payload);
    }

    @Test
    void 대표_메시지의_재시작_복원용_필드가_모두_보존된다() throws Exception {
        // Jira S15P21A506-314 세부 항목: source_issue_id/source_comment_id/association/
        // is_issue_author 를 typed JSON 에 보존해 재시작 후 복원한다.
        CommunityResultPayload payload = samplePayload();

        String json = objectMapper.writeValueAsString(payload);
        CommunityResultPayload restored =
                objectMapper.readValue(json, CommunityResultPayload.class);

        MessagePayload originalMessage = payload.topics().getFirst().messages().getFirst();
        MessagePayload restoredMessage = restored.topics().getFirst().messages().getFirst();

        assertThat(restored.topics().getFirst().sourceIssueId())
                .isEqualTo(payload.topics().getFirst().sourceIssueId());
        assertThat(restoredMessage.sourceCommentId()).isEqualTo(originalMessage.sourceCommentId());
        assertThat(restoredMessage.authorAssociation())
                .isEqualTo(originalMessage.authorAssociation());
        assertThat(restoredMessage.isIssueAuthor()).isEqualTo(originalMessage.isIssueAuthor());
    }

    @Test
    void 강조_구간은_summary_marks_로_저장되고_그대로_복원된다() throws Exception {
        var topic = samplePayload().topics().getFirst();
        var marked =
                new TopicPayload(
                        topic.sourceIssueId(),
                        topic.issueNumber(),
                        topic.state(),
                        topic.updatedAt(),
                        topic.createdAt(),
                        topic.titleOriginal(),
                        topic.titleKo(),
                        topic.commentsCount(),
                        topic.reactionsCount(),
                        topic.collectionStatus(),
                        topic.summaryStatus(),
                        topic.summaryKo(),
                        topic.messages(),
                        List.of(new SummaryMarkPayload(0, 10, SummaryMarkPayload.KEY_TERM)));

        String json = objectMapper.writeValueAsString(marked);
        TopicPayload restored = objectMapper.readValue(json, TopicPayload.class);

        assertThat(json).contains("\"summary_marks\"").contains("\"KEY_TERM\"");
        assertThat(restored).isEqualTo(marked);
    }

    @Test
    void summary_marks_가_없는_이전_스냅샷도_읽고_빈_목록이_된다() throws Exception {
        // payload_version 2 를 올리지 않고 선택 필드로 더했으므로, 운영에 이미 저장된 스냅샷(키 없음)이 오류 없이 읽혀야 한다.
        var node = objectMapper.readTree(objectMapper.writeValueAsString(samplePayload()));
        ((com.fasterxml.jackson.databind.node.ObjectNode) node.path("topics").get(0)).remove("summary_marks");

        CommunitySnapshotValidator.validateJson(node);
        CommunityResultPayload restored = objectMapper.treeToValue(node, CommunityResultPayload.class);

        assertThat(restored.topics().getFirst().summaryMarks()).isEmpty();
        CommunitySnapshotValidator.validate(restored);
    }

    @Test
    void 새_스냅샷은_flow를_저장하지_않고_그대로_읽힌다() throws Exception {
        String json = objectMapper.writeValueAsString(samplePayload());

        assertThat(json).doesNotContain("\"flow\"");
        var node = objectMapper.readTree(json);
        CommunitySnapshotValidator.validateJson(node);
        CommunityResultPayload restored = objectMapper.treeToValue(node, CommunityResultPayload.class);
        CommunitySnapshotValidator.validate(restored);
        assertThat(restored).isEqualTo(samplePayload());
    }

    @Test
    void flow가_남아_있는_이전_스냅샷도_읽고_flow만_버린다() throws Exception {
        // payload_version 2 를 올리지 않고 flow 를 걷어 냈으므로, 운영에 이미 저장된 스냅샷(flow 있음)이 그대로 읽혀야 한다.
        // 이 매퍼는 모르는 필드를 거부하는 기본 설정이라 TopicPayload 의 @JsonIgnoreProperties("flow") 가 없으면 여기서 깨진다.
        var node = objectMapper.readTree(objectMapper.writeValueAsString(samplePayload()));
        var topic = (com.fasterxml.jackson.databind.node.ObjectNode) node.path("topics").get(0);
        topic.putArray("flow").addObject().put("text", "Node.js와 worker thread 제약을 확인했습니다.");

        CommunitySnapshotValidator.validateJson(node);
        CommunityResultPayload restored = objectMapper.treeToValue(node, CommunityResultPayload.class);

        CommunitySnapshotValidator.validate(restored);
        assertThat(restored).isEqualTo(samplePayload());
        assertThat(objectMapper.writeValueAsString(restored)).doesNotContain("\"flow\"");
    }

    @Test
    void flow가_비어_있거나_FAILED_요약에_남은_이전_스냅샷도_읽는다() throws Exception {
        // 예전 검증기는 READY/PARTIAL 이면 flow 1개 이상, FAILED 이면 flow 빈 배열을 요구했다. 둘 다 이제는 상관없다.
        var node = objectMapper.readTree(objectMapper.writeValueAsString(samplePayload()));
        ((com.fasterxml.jackson.databind.node.ObjectNode) node.path("topics").get(0)).putArray("flow");

        CommunitySnapshotValidator.validateJson(node);
        CommunitySnapshotValidator.validate(objectMapper.treeToValue(node, CommunityResultPayload.class));
    }

    @Test
    void 모양이_깨진_flow는_여전히_거부한다() throws Exception {
        var node = objectMapper.readTree(objectMapper.writeValueAsString(samplePayload()));
        var topic = (com.fasterxml.jackson.databind.node.ObjectNode) node.path("topics").get(0);
        topic.putArray("flow").addObject().put("text", "흐름").put("support", "x");

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> CommunitySnapshotValidator.validateJson(node))
                .isInstanceOf(CommunitySnapshotPayloadException.class);

        topic.put("flow", "not-an-array");
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> CommunitySnapshotValidator.validateJson(node))
                .isInstanceOf(CommunitySnapshotPayloadException.class);
    }

    @Test
    void 알_수_없는_필드는_여전히_거부한다() throws Exception {
        // flow 만 예외다 — 다른 모르는 키까지 조용히 삼키면 payload 계약이 느슨해진다.
        var node = objectMapper.readTree(objectMapper.writeValueAsString(samplePayload()));
        ((com.fasterxml.jackson.databind.node.ObjectNode) node.path("topics").get(0)).put("surprise", "x");

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> CommunitySnapshotValidator.validateJson(node))
                .isInstanceOf(CommunitySnapshotPayloadException.class);
        org.assertj.core.api.Assertions.assertThatThrownBy(
                        () -> objectMapper.treeToValue(node, CommunityResultPayload.class))
                .isInstanceOf(com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException.class);
    }

    @Test
    void 요약문_범위를_벗어난_강조_구간은_저장_검증에서_거부한다() {
        var topic = samplePayload().topics().getFirst();
        int length = topic.summaryKo().length();
        for (var bad :
                List.of(
                        new SummaryMarkPayload(-1, 3, SummaryMarkPayload.KEY_TERM),
                        new SummaryMarkPayload(3, 3, SummaryMarkPayload.KEY_TERM),
                        new SummaryMarkPayload(0, length + 1, SummaryMarkPayload.KEY_TERM),
                        new SummaryMarkPayload(0, 3, "BOLD"))) {
            var payload = withMarks(topic, List.of(bad));
            org.assertj.core.api.Assertions.assertThatThrownBy(
                            () -> CommunitySnapshotValidator.validate(payload))
                    .as(bad.toString())
                    .isInstanceOf(CommunitySnapshotPayloadException.class);
        }
        CommunitySnapshotValidator.validate(
                withMarks(topic, List.of(new SummaryMarkPayload(0, length, SummaryMarkPayload.KEY_TERM))));
    }

    @Test
    void 대표_발화는_4개까지_허용하고_5개부터_거부한다() {
        var topic = samplePayload().topics().getFirst();
        var messages = new java.util.ArrayList<MessagePayload>();
        for (int i = 0; i < 5; i++)
            messages.add(
                    new MessagePayload(
                            String.valueOf(100 + i),
                            "user" + i,
                            "NONE",
                            false,
                            "DISCUSSION",
                            Instant.parse("2025-10-05T07:25:0" + i + "Z"),
                            "발화 " + i));

        CommunitySnapshotValidator.validate(withMessages(topic, messages.subList(0, 4)));
        org.assertj.core.api.Assertions.assertThatThrownBy(
                        () -> CommunitySnapshotValidator.validate(withMessages(topic, messages)))
                .isInstanceOf(CommunitySnapshotPayloadException.class);
    }

    private static CommunityResultPayload withMarks(TopicPayload t, List<SummaryMarkPayload> marks) {
        return single(
                new TopicPayload(
                        t.sourceIssueId(), t.issueNumber(), t.state(), t.updatedAt(), t.createdAt(),
                        t.titleOriginal(), t.titleKo(), t.commentsCount(), t.reactionsCount(),
                        t.collectionStatus(), t.summaryStatus(), t.summaryKo(), t.messages(),
                        marks));
    }

    private static CommunityResultPayload withMessages(TopicPayload t, List<MessagePayload> messages) {
        return single(
                new TopicPayload(
                        t.sourceIssueId(), t.issueNumber(), t.state(), t.updatedAt(), t.createdAt(),
                        t.titleOriginal(), t.titleKo(), t.commentsCount(), t.reactionsCount(),
                        t.collectionStatus(), t.summaryStatus(), t.summaryKo(), messages,
                        t.summaryMarks()));
    }

    private static CommunityResultPayload single(TopicPayload topic) {
        var base = samplePayload();
        return new CommunityResultPayload(
                base.repository(), base.policyVersion(), base.lookbackDays(), null, List.of(topic), List.of());
    }

    private static CommunityResultPayload samplePayload() {
        MessagePayload message =
                new MessagePayload(
                        "3368825804",
                        "mcollina",
                        "MEMBER",
                        false,
                        "DISCUSSION",
                        Instant.parse("2025-10-05T07:25:06Z"),
                        "worker thread에서 모듈을 불러오는 제약을 설명합니다.");

        TopicPayload topic =
                new TopicPayload(
                        String.valueOf(1000L + 2272),
                        2272,
                        "OPEN",
                        Instant.parse("2026-05-15T10:55:48Z"),
                        Instant.parse("2026-05-15T10:55:48Z"),
                        "[Feature Request] Can pass a module NOT STRING to pino transport target?",
                        "transport target에 모듈을 직접 전달할 수 있을까?",
                        30,
                        3,
                        "COMPLETE",
                        "READY",
                        "transport target의 모듈 전달과 번들러 호환성에 관한 논의입니다.",
                        List.of(message));

        RepositoryPayload repository =
                new RepositoryPayload(
                        ("pinojs/pino").split("/", 2)[0],
                        ("pinojs/pino").split("/", 2)[1],
                        "pinojs/pino",
                        "PACKAGE_SCOPED",
                        false);

        return new CommunityResultPayload(
                repository, "github-active-v1", 180, null, List.of(topic), List.of());
    }
}
