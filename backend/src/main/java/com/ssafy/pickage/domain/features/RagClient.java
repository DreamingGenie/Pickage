package com.ssafy.pickage.domain.features;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * 기능 비교 RAG 서버 호출 (S15P21A506-178).
 *
 * <p>같은 compose 네트워크 안의 {@code rag-api:8000} 으로 붙는다. 그 서비스는 호스트에 포트를
 * 열지 않는다 — 밖에 노출할 이유가 없고, 노출하면 LLM 키를 쓰는 경로가 하나 더 생긴다.
 *
 * <p><b>응답을 우리 record 로 옮기지 않는다.</b> {@link JsonNode} 그대로 들고 있다가 그대로
 * 내보낸다. 이유가 둘이다 —
 *
 * <ul>
 *   <li>이 응답의 계약 주인은 AI 쪽({@code ai/rag/main.py} 의 {@code _serialize})이다.
 *       여기에 같은 스키마를 한 벌 더 두면 한쪽만 고쳐지는 날이 온다.</li>
 *   <li>백엔드는 {@code SNAKE_CASE} 전략을 쓴다. record 로 받으면 {@code featureLabel} 이
 *       {@code feature_label} 로 바뀌어 나간다 — AI 가 정하고 프런트가 기다리는 이름과
 *       달라진다. {@code JsonNode} 는 이름을 그대로 둔다.</li>
 * </ul>
 */
@Component
public class RagClient {

	private final ObjectMapper json = new ObjectMapper();
	private final HttpClient http;
	private final URI compareUri;
	private final Duration timeout;

	public RagClient(
		@Value("${pickage.rag.base-url:http://rag-api:8000}") String baseUrl,
		@Value("${pickage.rag.timeout-seconds:180}") long timeoutSeconds
	) {
		this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
		this.compareUri = URI.create(baseUrl.replaceAll("/+$", "") + "/compare");
		// LLM 생성이 붙어 있어 초 단위가 아니라 분 단위다. 요청 경로가 아니라 백그라운드
		// run 안에서 부르므로 nginx 의 60초와 무관하다.
		this.timeout = Duration.ofSeconds(timeoutSeconds);
	}

	/** RAG 가 "그 버전의 자료가 없다" 로 답한 것. 서버 오류가 아니다. */
	public static class DocumentMissingException extends RuntimeException {
		private final transient JsonNode detail;

		DocumentMissingException(JsonNode detail) {
			super("DOC_NOT_FOUND");
			this.detail = detail;
		}

		public JsonNode detail() {
			return detail;
		}
	}

	/** RAG 가 자체 검증에서 걸러낸 것. 생성물을 내보내면 안 되는 경우다. */
	public static class VerificationFailedException extends RuntimeException {
		private final transient JsonNode violations;

		VerificationFailedException(JsonNode violations) {
			super("VERIFICATION_FAILED");
			this.violations = violations;
		}

		public JsonNode violations() {
			return violations;
		}
	}

	/**
	 * 비교를 요청한다. 순서는 넣은 그대로 간다.
	 *
	 * <p>404·502 를 예외로 갈라 내는 이유는, 그 둘이 "고치면 되는 것" 과 "그대로 두어야 하는
	 * 것" 으로 다르기 때문이다. 404 는 그 버전의 문헌이 아직 없다는 뜻이라 다른 버전을 고르면
	 * 되고, 502 는 생성물이 근거와 어긋났다는 뜻이라 다시 눌러도 같은 답이 나올 수 있다.
	 */
	public JsonNode compare(List<PackageRefs.Ref> refs) throws IOException, InterruptedException {
		ObjectNode body = json.createObjectNode();
		ArrayNode packages = body.putArray("packages");
		for (PackageRefs.Ref ref : refs) {
			packages.addObject().put("package", ref.name()).put("version", ref.version());
		}

		HttpResponse<byte[]> response = http.send(
			HttpRequest.newBuilder(compareUri)
				.header("Content-Type", "application/json")
				.timeout(timeout)
				.POST(HttpRequest.BodyPublishers.ofString(body.toString(), StandardCharsets.UTF_8))
				.build(),
			HttpResponse.BodyHandlers.ofByteArray());

		int code = response.statusCode();
		if (code == 200) {
			return json.readTree(response.body());
		}

		JsonNode detail = parseDetail(response.body());
		if (code == 404) {
			throw new DocumentMissingException(detail);
		}
		if (code == 502) {
			throw new VerificationFailedException(detail.path("violations"));
		}
		throw new IOException("rag-api HTTP " + code + " " + detail);
	}

	/** 오류 본문이 JSON 이 아닐 수도 있다 — 그때 파싱 예외로 원인을 덮지 않는다. */
	private JsonNode parseDetail(byte[] raw) {
		try {
			return json.readTree(raw).path("detail");
		} catch (IOException e) {
			return json.getNodeFactory().textNode(new String(raw, StandardCharsets.UTF_8));
		}
	}
}
