package com.ssafy.pickage.domain.packages.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * {@code GET /api/packages/version} 응답 (명세 §6).
 *
 * @param basis            지분의 기준. 항상 {@code "dependents"} 다 —
 *                         다운로드는 패키지 단위 단일값이라 버전별로 쪼갤 수 없다.
 * @param sumOverVersions  §5 와 같은 이유로 조각 합계는 부풀려진 값이다.
 *                         비율은 정상이지만 <b>원 가운데에 총계를 찍으면 안 된다</b>는 신호.
 */
public record VersionShareResponse(
	LocalDate snapshotAt,
	String basis,
	boolean sumOverVersions,
	List<Item> items,
	List<String> notFound
) {

	public static VersionShareResponse of(LocalDate snapshotAt, List<Item> items, List<String> notFound) {
		return new VersionShareResponse(snapshotAt, "dependents", true, items, notFound);
	}

	/**
	 * 원 하나.
	 *
	 * <p>{@code slices} 가 빈 배열인 것은 <b>에러가 아니다</b>. 형식은 맞지만 데이터가 없는
	 * {@code snapshot_at} 을 받으면 200 에 빈 배열이 나간다. 형식 오류(V003)와 구분해야 한다 —
	 * 앞은 "그 날짜엔 자료가 없습니다", 뒤는 "날짜를 다시 쓰세요" 로 화면 안내가 다르다.
	 */
	public record Item(String name, List<Slice> slices) {
	}

	/**
	 * major 조각.
	 *
	 * @param major major 문자열. {@code 0.x} 대는 {@code "0"} 으로 뭉친다 — 정상 동작이다.
	 * @param pct   <b>해당 패키지 안에서의</b> 비율. 패키지별로 각각 100% 가 된다.
	 *              소수 한 자리라 {@code double} 대신 {@link BigDecimal} 을 쓴다 —
	 *              {@code double} 은 {@code 91.4} 를 {@code 91.40000000000001} 로 직렬화한다.
	 */
	public record Slice(String major, long dependents, BigDecimal pct) {
	}
}
