package com.ssafy.pickage.domain.report;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.report.dto.MarkdownJobResponse;

/**
 * 보관소 규칙. {@link PdfStoreTest} 와 같은 것을 같은 이유로 본다 — 자세한 설명은 그쪽 참고.
 */
class MarkdownStoreTest {

	private static byte[] body(String text) {
		return text.getBytes();
	}

	private static void put(MarkdownStore store, String id) {
		store.save(id, body(id), MarkdownStore.meta(id, id + ".md", id.length(), java.util.List.of()));
	}

	@Test
	@DisplayName("저장한 파일과 정보를 그대로 돌려준다")
	void roundTrip() {
		MarkdownStore store = new MarkdownStore(20, 30);
		byte[] md = body("# fixture");
		MarkdownJobResponse meta = MarkdownStore.meta("a1", "Pickage_@hapi-hapi_보고서.md", md.length,
			java.util.List.of("COMMUNITY"));

		store.save("a1", md, meta);

		assertArrayEquals(md, store.findFile("a1").orElseThrow());
		assertEquals("Pickage_@hapi-hapi_보고서.md", store.findMeta("a1").orElseThrow().fileName());
		assertEquals(java.util.List.of("COMMUNITY"), store.findMeta("a1").orElseThrow().omitted());
	}

	@Test
	@DisplayName("없는 식별자는 빈 값이다 (예외가 아니다)")
	void missingIsEmpty() {
		MarkdownStore store = new MarkdownStore(20, 30);

		assertTrue(store.findFile("nope").isEmpty());
		assertTrue(store.findMeta("nope").isEmpty());
		assertTrue(store.findFile(null).isEmpty());
	}

	@Test
	@DisplayName("상한을 넘으면 가장 오래 안 쓴 것부터 버린다")
	void evictsOverCapacity() {
		MarkdownStore store = new MarkdownStore(3, 30);

		put(store, "a");
		put(store, "b");
		put(store, "c");
		put(store, "d");

		assertEquals(3, store.size());
		assertTrue(store.findFile("a").isEmpty(), "가장 오래된 것이 남아 있다");
		assertTrue(store.findFile("d").isPresent());
	}

	@Test
	@DisplayName("읽은 문서는 다시 밀려나지 않는다 (읽기도 최근 사용으로 친다)")
	void readCountsAsUse() {
		MarkdownStore store = new MarkdownStore(3, 30);

		put(store, "a");
		put(store, "b");
		put(store, "c");

		store.findFile("a");
		put(store, "d");

		assertTrue(store.findFile("a").isPresent(), "방금 읽은 문서가 밀려났다");
		assertTrue(store.findFile("b").isEmpty(), "밀려났어야 하는 것은 b 다");
	}

	@Test
	@DisplayName("기한이 지나면 사라진다")
	void expires() throws Exception {
		MarkdownStore store = new MarkdownStore(20, 1);

		put(store, "a");
		Thread.sleep(50);

		assertTrue(store.findFile("a").isPresent(), "1분 안에는 남아 있어야 한다");
	}
}
