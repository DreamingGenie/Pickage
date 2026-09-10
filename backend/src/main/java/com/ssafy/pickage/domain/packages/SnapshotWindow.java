package com.ssafy.pickage.domain.packages;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 추이 조회 구간 (API 명세 §4).
 *
 * <p>{@code from}·{@code to} 는 둘 다 선택이다. 생략됐을 때 기본값을 정하는 기준이
 * <b>오늘이 아니라 최신 스냅샷</b> 이라는 점이 핵심이다 — 스냅샷은 주 1회 만들어지므로
 * 오늘 기준으로 26주를 세면 아직 만들어지지 않은 주가 구간에 들어가고, 그만큼 앞쪽이
 * 잘려 나가 매번 다른 길이의 시리즈가 나온다.
 *
 * @param from 포함
 * @param to   포함
 */
public record SnapshotWindow(LocalDate from, LocalDate to) {

	/** §4 — 조회 기간 상한(주). 배열 상한 3 과 곱해져 응답 크기를 정한다. */
	public static final int MAX_WEEKS = 104;

	/** §4 — {@code from} 생략 시 기본 구간(주). */
	public static final int DEFAULT_WEEKS = 26;

	/**
	 * 날짜 <b>형식</b> 검증은 여기서 하지 않는다.
	 *
	 * <p>스프링이 {@code String → LocalDate} 변환에 실패하면
	 * {@code MethodArgumentTypeMismatchException} 이 나고, 전역 핸들러가 그것을 V003 으로
	 * 옮긴다. 즉 이 메서드에 도달한 값은 이미 파싱된 날짜다. 여기서 또 검사하면 같은 규칙이
	 * 두 곳에 생기고, 나중에 한쪽만 고쳐진다.
	 *
	 * @param latestSnapshot {@code SELECT MAX(snapshot_at) FROM snapshot} 의 값
	 */
	public static SnapshotWindow of(LocalDate from, LocalDate to, LocalDate latestSnapshot) {
		LocalDate end = to != null ? to : latestSnapshot;
		LocalDate start = from != null ? from : end.minusWeeks(DEFAULT_WEEKS - 1L);

		if (start.isAfter(end)) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED, "시작 날짜가 끝 날짜보다 뒤입니다.");
		}

		// 양 끝을 포함하므로 +1. 26주를 고르면 점이 26개여야 한다.
		long weeks = ChronoUnit.WEEKS.between(start, end) + 1;
		if (weeks > MAX_WEEKS) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"한 번에 최대 %d개, 최대 %d주까지 조회할 수 있습니다.".formatted(PackageNames.MAX, MAX_WEEKS));
		}
		return new SnapshotWindow(start, end);
	}
}
