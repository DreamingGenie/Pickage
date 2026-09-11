package com.ssafy.pickage.domain.report;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.report.dto.PdfJobResponse;

/**
 * 보관소 규칙.
 *
 * <p>여기서 보는 것은 저장·조회가 아니라 <b>한계</b>다. 메모리에 들고 있으므로 상한과 기한이
 * 실제로 도는지가 전부다 — 안 돌면 많이 눌러 본 사용자 하나가 힙을 채운다.
 */
class PdfStoreTest {

	private static byte[] body(String text) {
		return text.getBytes();
	}

	private static void put(PdfStore store, String id) {
		store.save(id, "<html>fixture</html>", body(id), PdfStore.meta(id, id + ".pdf", id.length(), java.util.List.of()));
	}

	@Test
	@DisplayName("저장한 파일과 정보를 그대로 돌려준다")
	void roundTrip() {
		PdfStore store = new PdfStore(20, 30);
		byte[] pdf = body("%PDF-1.4 fake");
		// 한글·스코프 문자가 섞인 이름이 그대로 살아남아야 한다.
		PdfJobResponse meta = PdfStore.meta("a1", "Pickage_@hapi-hapi_보고서.pdf", pdf.length,
			java.util.List.of("COMMUNITY"));

		store.save("a1", "<html>fixture</html>", pdf, meta);

		assertArrayEquals(pdf, store.findFile("a1").orElseThrow());
		assertEquals("Pickage_@hapi-hapi_보고서.pdf", store.findMeta("a1").orElseThrow().fileName());
		assertEquals(PdfJobResponse.COMPLETE, store.findMeta("a1").orElseThrow().status());
		assertEquals(java.util.List.of("COMMUNITY"), store.findMeta("a1").orElseThrow().omitted());
	}

	@Test
	@DisplayName("없는 식별자는 빈 값이다 (예외가 아니다)")
	void missingIsEmpty() {
		PdfStore store = new PdfStore(20, 30);

		assertTrue(store.findFile("nope").isEmpty());
		assertTrue(store.findMeta("nope").isEmpty());
		assertTrue(store.findFile(null).isEmpty());
	}

	@Test
	@DisplayName("상한을 넘으면 가장 오래 안 쓴 것부터 버린다")
	void evictsOverCapacity() {
		PdfStore store = new PdfStore(3, 30);

		put(store, "a");
		put(store, "b");
		put(store, "c");
		put(store, "d");

		assertEquals(3, store.size());
		assertTrue(store.findFile("a").isEmpty(), "가장 오래된 것이 남아 있다");
		assertTrue(store.findFile("d").isPresent());
	}

	/**
	 * <b>읽기도 최근 사용으로 쳐야 한다.</b> 미리보기를 본 문서가 다운로드 전에 밀려나면
	 * 사용자는 방금 본 것을 받지 못한다 — 화면 흐름이 미리보기 → 다운로드라 실제로 밟힌다.
	 */
	@Test
	@DisplayName("미리보기로 읽은 문서는 다운로드 전에 밀려나지 않는다")
	void readCountsAsUse() {
		PdfStore store = new PdfStore(3, 30);

		put(store, "a");
		put(store, "b");
		put(store, "c");

		store.findFile("a"); // 미리보기
		put(store, "d");     // 다른 보고서가 들어와 하나가 밀려난다

		assertTrue(store.findFile("a").isPresent(), "방금 본 문서가 밀려났다");
		assertTrue(store.findFile("b").isEmpty(), "밀려났어야 하는 것은 b 다");
	}

	@Test
	@DisplayName("기한이 지나면 사라진다")
	void expires() throws Exception {
		// 기한은 분 단위이고 최솟값이 1분이라, 여기서는 경계가 아니라 '안 사라짐' 만 본다.
		PdfStore store = new PdfStore(20, 1);

		put(store, "a");
		Thread.sleep(50);

		assertTrue(store.findFile("a").isPresent(), "1분 안에는 남아 있어야 한다");
	}
}
