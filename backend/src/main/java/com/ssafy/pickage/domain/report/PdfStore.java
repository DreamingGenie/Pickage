package com.ssafy.pickage.domain.report;

import java.time.Duration;
import java.time.Instant;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.ssafy.pickage.domain.report.dto.PdfJobResponse;

/**
 * 만들어진 PDF 를 잠깐 들고 있는다.
 *
 * <h2>왜 들고 있어야 하는가</h2>
 *
 * 화면 흐름이 <b>생성 → 제작 중 → 미리보기 → 다운로드</b> 라서 한 파일을 최소 두 번 읽는다.
 * 만들자마자 바이트로 돌려주면 미리보기를 본 뒤 저장할 때 문서를 다시 만들어야 하고,
 * 그러면 요구사항 §13.2("다운로드만 실패한 경우 다시 만들지 않고 같은 파일을 받는다")도
 * 지킬 수 없다.
 *
 * <h2>디스크가 아니라 메모리인 이유</h2>
 *
 * 이 문서는 <b>일회용</b>이다. 보는 순간 쓰임이 끝나고, 필요하면 조건을 그대로 다시 눌러
 * 만들면 된다. 디스크에 두면 지우는 규칙을 따로 만들어야 하고 — 안 만들면 영원히 쌓인다 —
 * 식별자를 경로로 쓰는 데서 오는 경로 조작 방어까지 떠안게 된다. 메모리에 두면 그 문제가
 * 통째로 사라지고, 상한과 기한만 지키면 된다.
 *
 * <p>대가는 <b>재시작하면 사라진다</b> 는 것. 일회용 문서라 다시 만들면 그만이고, 화면은
 * 이미 "없는 보고서" 를 다룰 수 있어야 한다(링크를 오래 열어 둔 경우).
 *
 * <p>생성이 #1 워커로 옮겨가면 이 클래스만 MinIO 저장소로 갈아끼운다. 바깥은 그대로다.
 */
@Component
public class PdfStore {

	private final int capacity;
	private final Duration ttl;

	/**
	 * 접근 순서를 유지하는 LRU.
	 *
	 * <p>{@code accessOrder=true} 라 <b>읽기도 최근 사용으로 친다.</b> 미리보기를 본 문서가
	 * 다운로드 전에 밀려나면 사용자가 방금 본 것을 못 받는다.
	 */
	private final Map<String, Entry> entries;

	public PdfStore(
		@Value("${pickage.pdf.capacity:20}") int capacity,
		@Value("${pickage.pdf.ttl-minutes:30}") long ttlMinutes
	) {
		this.capacity = Math.max(1, capacity);
		this.ttl = Duration.ofMinutes(Math.max(1, ttlMinutes));
		this.entries = new LinkedHashMap<>(16, 0.75f, true);
	}

	/**
	 * HTML 과 PDF 를 <b>함께</b> 보관한다.
	 *
	 * <p>미리보기는 HTML 을, 다운로드는 PDF 를 쓰는데 둘이 같은 생성에서 나온 것이어야
	 * "본 것과 받은 것이 같다" 가 성립한다. 따로 들고 있다가 한쪽만 밀려나면 그 보장이 깨진다.
	 *
	 * <p>PDF 를 다운로드 시점에 변환하지 않고 미리 만들어 두는 이유는 <b>크기</b> 때문이다 —
	 * 화면이 완료 상태에서 파일 크기를 보여줘야 하는데(IA §12.3) 변환 전에는 알 수 없다.
	 */
	public synchronized void save(String id, String html, byte[] pdf, PdfJobResponse meta) {
		evictExpired();
		entries.put(id, new Entry(html, pdf, meta, Instant.now()));

		// 기한이 남아도 개수가 넘치면 가장 오래 안 쓴 것부터 버린다. 상한이 없으면
		// 많이 눌러 본 사용자 하나가 힙을 채운다.
		while (entries.size() > capacity) {
			Iterator<String> oldest = entries.keySet().iterator();
			oldest.next();
			oldest.remove();
		}
	}

	public synchronized Optional<PdfJobResponse> findMeta(String id) {
		return find(id).map(Entry::meta);
	}

	public synchronized Optional<byte[]> findFile(String id) {
		return find(id).map(Entry::pdf);
	}

	/** 미리보기가 쓰는 HTML. PDF 와 같은 생성에서 나온 것이다. */
	public synchronized Optional<String> findHtml(String id) {
		return find(id).map(Entry::html);
	}

	private Optional<Entry> find(String id) {
		if (id == null) return Optional.empty();
		evictExpired();
		// LinkedHashMap 의 접근 순서 갱신을 위해 get 을 쓴다.
		return Optional.ofNullable(entries.get(id));
	}

	/**
	 * 기한이 지난 것을 치운다.
	 *
	 * <p>별도 스케줄러를 두지 않는다 — 접근할 때만 치워도 개수 상한이 있어 무한히 쌓이지
	 * 않고, 아무도 안 쓰는 동안 도는 작업이 하나 줄어든다.
	 */
	private void evictExpired() {
		Instant deadline = Instant.now().minus(ttl);
		entries.values().removeIf(e -> e.storedAt().isBefore(deadline));
	}

	/** 지금 들고 있는 개수. 시험이 상한과 기한을 확인하는 데만 쓴다. */
	synchronized int size() {
		evictExpired();
		return entries.size();
	}

	private record Entry(String html, byte[] pdf, PdfJobResponse meta, Instant storedAt) {
	}

	/** 작업 메타데이터. 생성 시각은 서버가 정한다. */
	public static PdfJobResponse meta(String id, String fileName, long bytes,
		java.util.List<String> omitted) {
		return new PdfJobResponse(id, PdfJobResponse.COMPLETE, fileName, bytes,
			Instant.now(), omitted);
	}
}
