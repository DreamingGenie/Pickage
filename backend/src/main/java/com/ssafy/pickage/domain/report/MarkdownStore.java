package com.ssafy.pickage.domain.report;

import java.time.Duration;
import java.time.Instant;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.ssafy.pickage.domain.report.dto.MarkdownJobResponse;

/**
 * 만들어진 HAND-OFF Markdown 을 잠깐 들고 있는다. {@link PdfStore} 와 같은 이유·같은 모양이다
 * (S15P21A506-466) — 다시 받기(§13.2·기능-16-R08)를 지키려면 생성과 다운로드를 나눠야 하고,
 * 나누려면 그 사이를 메모리에 들고 있어야 한다. 디스크가 아니라 메모리인 이유, 재시작하면
 * 사라지는 대가, 생성이 #1 워커로 옮겨가면 MinIO 로 갈아끼울 계획까지 전부 {@link PdfStore} 와
 * 같다 — 자세한 설명은 그쪽 주석을 본다.
 *
 * <p><b>PDF·HTML 대신 {@code .md} bytes 하나만 든다.</b> Markdown 은 그 자체로 사람도 읽을 수
 * 있는 텍스트라 별도 미리보기 산출물이 없다.
 */
@Component
public class MarkdownStore {

	private final int capacity;
	private final Duration ttl;
	private final Map<String, Entry> entries;

	public MarkdownStore(
		@Value("${pickage.markdown.capacity:20}") int capacity,
		@Value("${pickage.markdown.ttl-minutes:30}") long ttlMinutes
	) {
		this.capacity = Math.max(1, capacity);
		this.ttl = Duration.ofMinutes(Math.max(1, ttlMinutes));
		this.entries = new LinkedHashMap<>(16, 0.75f, true);
	}

	public synchronized void save(String id, byte[] markdown, MarkdownJobResponse meta) {
		evictExpired();
		entries.put(id, new Entry(markdown, meta, Instant.now()));

		while (entries.size() > capacity) {
			Iterator<String> oldest = entries.keySet().iterator();
			oldest.next();
			oldest.remove();
		}
	}

	public synchronized Optional<MarkdownJobResponse> findMeta(String id) {
		return find(id).map(Entry::meta);
	}

	public synchronized Optional<byte[]> findFile(String id) {
		return find(id).map(Entry::markdown);
	}

	private Optional<Entry> find(String id) {
		if (id == null) return Optional.empty();
		evictExpired();
		return Optional.ofNullable(entries.get(id));
	}

	private void evictExpired() {
		Instant deadline = Instant.now().minus(ttl);
		entries.values().removeIf(e -> e.storedAt().isBefore(deadline));
	}

	/** 지금 들고 있는 개수. 시험이 상한과 기한을 확인하는 데만 쓴다. */
	synchronized int size() {
		evictExpired();
		return entries.size();
	}

	private record Entry(byte[] markdown, MarkdownJobResponse meta, Instant storedAt) {
	}

	public static MarkdownJobResponse meta(String id, String fileName, long bytes, List<String> omitted) {
		return new MarkdownJobResponse(id, fileName, bytes, Instant.now(), omitted);
	}
}
