package com.ssafy.pickage.domain.community.verification;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * {@code HttpResponse.BodyHandlers.ofInputStream()}으로 받은 본문을 <b>읽는 도중</b> 누적
 * 바이트 수를 세다가 상한을 넘으면 그 자리에서 멈춘다.
 *
 * <p>{@code BodyHandlers.ofString()}을 쓰지 않는 이유가 이것이다 — 그건 상한을 확인하기도
 * 전에 전체 응답을 이미 메모리에 다 올려 버린다. 상한의 목적(악의적이거나 손상된 응답이
 * 무한정 메모리를 먹는 것을 막는 것)을 지키려면 스트림을 직접 조각내 읽어야 한다.
 *
 * <p>{@code public}이다 — Phase 3({@code domain/community/collection}, S15P21A506-212)의
 * GitHub Search·댓글 클라이언트도 같은 byte 상한 문제를 겪는다. rate limit 판정 로직(213의
 * {@code send()}/{@code checkRateLimit()})은 사용자 결정으로 그쪽에서 다시 작게 구현하지만,
 * 이 클래스는 정책 판단이 없는 순수 스트림 유틸이라 로직을 중복하지 않고 가시성만 넓혀
 * 재사용한다({@code docs/for_community/specs/S15P21A506-212.md} §2).
 */
public final class BoundedHttpReader {

	private static final int CHUNK_SIZE = 8192;

	private BoundedHttpReader() {
	}

	/**
	 * @param maxBytes 2026-09-11 사용자 승인 — 기본값은 npm·GitHub 응답 각 2 MiB
	 *                 (2,097,152 bytes)이지만 호출자가 시험용으로 다른 값을 넣을 수 있다
	 *                 ({@code docs/for_community/specs/S15P21A506-213.md} §7).
	 * @throws UpstreamFetchException 상한을 넘거나 읽기 자체가 실패하면. 원인 예외의 raw
	 *                                내용은 메시지에 담지 않는다.
	 */
	public static String readBounded(InputStream body, long maxBytes, String sourceForLogging) {
		try (InputStream in = body) {
			ByteArrayOutputStream buffer = new ByteArrayOutputStream();
			byte[] chunk = new byte[CHUNK_SIZE];
			long total = 0;
			int read;
			while ((read = in.read(chunk)) != -1) {
				total += read;
				if (total > maxBytes) {
					throw new UpstreamFetchException(
						sourceForLogging + " 응답이 상한(" + maxBytes + " bytes)을 넘었다");
				}
				buffer.write(chunk, 0, read);
			}
			return buffer.toString(StandardCharsets.UTF_8);
		} catch (IOException e) {
			throw new UpstreamFetchException(sourceForLogging + " 응답을 읽는 중 통신 오류", e);
		}
	}
}
