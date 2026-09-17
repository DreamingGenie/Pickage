package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.verification.FakeHttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

class GmsCommunitySummarizerTest {

    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final String PATH = "/v1/responses";
    private static final Duration BUDGET = Duration.ofSeconds(10);

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

    private GmsCommunitySummarizer client() {
        return new GmsCommunitySummarizer(
                httpClient,
                server.baseUrl(),
                PATH,
                "fake-key",
                "Authorization",
                "Bearer",
                "gpt-5.4-mini",
                MAX_BYTES);
    }

    private CollectedIssue issue(int number) {
        return new CollectedIssue(
                number,
                "설정 동작 확인",
                "open",
                Instant.parse("2026-01-02T00:00:00Z"),
                "asker",
                1,
                0,
                CommentCollectionStatus.COMPLETE,
                List.of(
                        new CollectedComment(
                                "9007199254740993",
                                "helper",
                                "CONTRIBUTOR",
                                false,
                                Instant.parse("2026-01-02T01:00:00Z"),
                                "설정을 확인하는 방법을 제시했다.",
                                "user-2",
                                0)),
                List.of(),
                "701",
                Instant.parse("2026-01-01T00:00:00Z"),
                "user-1",
                "설정이 반영되지 않습니다.");
    }

    private static String gmsEnvelope(String outputTextJson) {
        return """
                {
                  "status": "completed",
                  "output": [
                    {
                      "type": "message",
                      "content": [{"type": "output_text", "text": %s}]
                    }
                  ]
                }
                """
                .formatted(new ObjectMapper().valueToTree(outputTextJson).toString());
    }

    private static final String VALID_PAYLOAD =
            """
            {
              "issue_number": 7,
              "title_ko": "설정 동작 확인",
              "summary_ko": "작성자가 설정 동작을 질문했고 댓글에서 확인 방법이 제시됐다.",
              "summary_support": [{"type": "ISSUE_BODY", "id": "701"}],
              "flow": [
                {"text": "설정 동작에 관한 질문이 제기됐다."}
              ],
              "flow_support": [{"flow_index": 0, "type": "ISSUE_BODY", "id": "701"}],
              "messages": [
                {"source_comment_id": "9007199254740993", "kind": "DISCUSSION", "text": "설정을 확인하는 방법을 제시했다."}
              ]
            }
            """;

    private static String payloadWithFlowSupport(String flowSupportJson) {
        return """
                {
                  "issue_number": 7,
                  "title_ko": "설정 동작 확인",
                  "summary_ko": "작성자가 설정 동작을 질문했고 댓글에서 확인 방법이 제시됐다.",
                  "summary_support": [{"type": "ISSUE_BODY", "id": "701"}],
                  "flow": [
                    {"text": "설정 동작에 관한 질문이 제기됐다."}
                  ],
                  "flow_support": %s,
                  "messages": []
                }
                """
                .formatted(flowSupportJson);
    }

    @Test
    void 정상_응답을_TopicSummary로_파싱한다() {
        server.respond(PATH, 200, gmsEnvelope(VALID_PAYLOAD), java.util.Map.of());

        TopicSummary summary = client().summarize(issue(7), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.READY);
        assertThat(summary.titleKo()).isEqualTo("설정 동작 확인");
        assertThat(summary.summaryKo()).contains("확인 방법");
        assertThat(summary.discussionFlow()).hasSize(1);
        assertThat(summary.messages()).hasSize(1);
        assertThat(summary.messages().get(0).sourceCommentId()).isEqualTo("9007199254740993");
        assertThat(summary.messages().get(0).kind()).isEqualTo("DISCUSSION");
        assertThat(summary.summarySupport())
                .containsExactly(new TopicSummary.SourceRef("ISSUE_BODY", "701"));
        assertThat(summary.flowSupport())
                .containsExactly(List.of(new TopicSummary.SourceRef("ISSUE_BODY", "701")));
    }

    @Test
    void flow_index가_flow_범위를_벗어나면_실패로_처리한다() {
        server.respond(
                PATH,
                200,
                gmsEnvelope(
                        payloadWithFlowSupport(
                                "[{\"flow_index\": 5, \"type\": \"ISSUE_BODY\", \"id\": \"701\"}]")),
                java.util.Map.of());

        TopicSummary summary = client().summarize(issue(7), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void issue_number가_다르면_실패로_처리한다() {
        server.respond(PATH, 200, gmsEnvelope(VALID_PAYLOAD), java.util.Map.of());

        // 요청한 issue_number(999)와 응답의 issue_number(7 — VALID_PAYLOAD 고정)가 어긋남
        TopicSummary summary = client().summarize(issue(999), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void 비200_응답은_실패로_처리한다() {
        server.respond(PATH, 400, "{\"statusCode\":400,\"message\":\"[GMS 에러] boom\"}", java.util.Map.of());

        TopicSummary summary = client().summarize(issue(7), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void status가_completed가_아니면_실패로_처리한다() {
        server.respond(
                PATH,
                200,
                "{\"status\":\"incomplete\",\"output\":[]}",
                java.util.Map.of());

        TopicSummary summary = client().summarize(issue(7), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void output_text가_유효한_JSON이_아니면_실패로_처리한다() {
        server.respond(PATH, 200, gmsEnvelope("이건 JSON이 아니다"), java.util.Map.of());

        TopicSummary summary = client().summarize(issue(7), BUDGET);

        assertThat(summary.status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void 인증_헤더와_모델명을_정확히_보낸다() {
        AtomicReference<String> captured = new AtomicReference<>();
        server.respondCapturingBody(PATH, gmsEnvelope(VALID_PAYLOAD), captured::set);

        client().summarize(issue(7), BUDGET);

        JsonNode request = readTree(captured.get());
        assertThat(request.path("model").asText()).isEqualTo("gpt-5.4-mini");
        assertThat(request.path("text").path("format").path("type").asText())
                .isEqualTo("json_schema");
        assertThat(request.path("text").path("format").path("strict").asBoolean()).isTrue();
        assertThat(request.path("input")).hasSize(2);
        assertThat(request.path("input").get(0).path("role").asText()).isEqualTo("system");
        assertThat(request.path("input").get(1).path("role").asText()).isEqualTo("user");
        assertThat(request.path("input").get(1).path("content").asText()).contains("701");
    }

    @Test
    void 요청_스키마는_flow_support를_평면_배열로_보낸다() {
        AtomicReference<String> captured = new AtomicReference<>();
        server.respondCapturingBody(PATH, gmsEnvelope(VALID_PAYLOAD), captured::set);

        client().summarize(issue(7), BUDGET);

        JsonNode request = readTree(captured.get());
        assertThat(request.path("max_output_tokens").asInt()).isEqualTo(3072);

        JsonNode schema = request.path("text").path("format").path("schema");
        JsonNode flowItemSchema = schema.path("properties").path("flow").path("items");
        assertThat(flowItemSchema.path("properties").has("support")).isFalse();
        assertThat(flowItemSchema.path("required")).extracting(JsonNode::asText).containsExactly("text");

        JsonNode flowSupportSchema = schema.path("properties").path("flow_support");
        assertThat(flowSupportSchema.path("type").asText()).isEqualTo("array");
        JsonNode flowSupportItemProps = flowSupportSchema.path("items").path("properties");
        assertThat(flowSupportItemProps.has("flow_index")).isTrue();
        assertThat(flowSupportItemProps.has("type")).isTrue();
        assertThat(flowSupportItemProps.has("id")).isTrue();
        assertThat(schema.path("required")).extracting(JsonNode::asText).contains("flow_support");
    }

    private static JsonNode readTree(String json) {
        try {
            return new ObjectMapper().readTree(json);
        } catch (Exception e) {
            throw new AssertionError(e);
        }
    }
}
