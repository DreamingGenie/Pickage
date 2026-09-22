package com.ssafy.pickage.domain.summary;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class GmsEcosystemSummarizerTest {

	@Test
	@DisplayName("입력은 공백 없는 JSON 이고 false·빈 description 은 뺀다")
	void userMessage() throws Exception {
		String msg = GmsEcosystemSummarizer.userMessage(List.of(
			new EcosystemFacts("a", "", false, "high", "up", "flat"),
			new EcosystemFacts("b", "desc", true, "low", "unknown", "down")));
		assertEquals("[{\"name\":\"a\",\"downloads_level\":\"high\",\"downloads_3m\":\"up\",\"dependents_3m\":\"flat\"},"
			+ "{\"name\":\"b\",\"description\":\"desc\",\"deprecated\":true,\"downloads_level\":\"low\","
			+ "\"downloads_3m\":\"unknown\",\"dependents_3m\":\"down\"}]", msg);
	}

	@Test
	@DisplayName("응답에서 두 문장과 사용량(크레딧)을 꺼낸다")
	void parse() throws Exception {
		String body = """
			{"status":"completed","usage":{"input_tokens":600,"output_tokens":180,
			 "output_tokens_details":{"reasoning_tokens":0}},
			 "output":[{"type":"message","content":[{"type":"output_text",
			 "text":"{\\"common\\":\\"공통이에요.\\",\\"ecosystem\\":\\"흐름이에요.\\"}"}]}]}""";
		var r = GmsEcosystemSummarizer.parse(body).orElseThrow();
		assertEquals("공통이에요.", r.common());
		assertEquals("흐름이에요.", r.ecosystem());
		assertEquals(21.15, r.usage().credits(), 0.001);
	}

	@Test
	@DisplayName("잘린 응답(incomplete)은 실패로 본다")
	void incomplete() throws Exception {
		assertTrue(GmsEcosystemSummarizer.parse(
			"{\"status\":\"incomplete\",\"incomplete_details\":{\"reason\":\"max_output_tokens\"},\"usage\":{}}").isEmpty());
	}

	@Test
	@DisplayName("너무 긴 문장은 마지막 문장 끝에서 자른다")
	void clean() {
		String longText = "첫 문장이에요. " + "가".repeat(200);
		assertEquals("첫 문장이에요.", GmsEcosystemSummarizer.clean(longText));
		assertEquals("ab", GmsEcosystemSummarizer.clean("<a>b"));
	}
}
