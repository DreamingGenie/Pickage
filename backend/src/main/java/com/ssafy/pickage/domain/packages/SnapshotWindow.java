package com.ssafy.pickage.domain.packages;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

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
	 * <h2>구간이 아예 없을 수 있다</h2>
	 *
	 * 적재 전이라 {@code snapshot} 이 비어 있으면 {@code latestSnapshot} 이 {@code null} 이고,
	 * {@code to} 도 안 왔으면 <b>셀 기준 자체가 없다.</b> 예전에는 여기서 그대로
	 * {@code end.minusWeeks(...)} 를 불러 NPE 가 났고, 전역 핸들러가 그것을 S001(500) 로 옮겼다 —
	 * 정상 상태인 "자료 축적 중" 이 화면에서 장애로 보였다.
	 *
	 * <p>명세 §6 은 같은 상황(형식은 맞지만 데이터가 없는 날짜)을 <b>200 에 빈 결과</b>로
	 * 정해 두었다. 추이 두 개만 다른 규칙을 쓸 이유가 없어 여기서도 빈 값을 돌려주고,
	 * 호출자가 DB 를 묻지 않고 빈 시리즈로 내보낸다.
	 *
	 * <p><b>{@code from}·{@code to} 를 둘 다 명시하면 스냅샷이 없어도 구간은 성립한다.</b>
	 * 그때는 조회 결과만 비는 것이 맞다 — 사용자가 물어본 구간을 서버가 지어내지 않는다.
	 *
	 * @param latestSnapshot {@code SELECT MAX(snapshot_at) FROM snapshot} 의 값.
	 *                       스냅샷이 하나도 없으면 {@code null} 이다.
	 * @return 구간. 기준으로 삼을 날짜가 없으면 비어 있다.
	 */
	public static Optional<SnapshotWindow> of(LocalDate from, LocalDate to, LocalDate latestSnapshot) {
		LocalDate end = to != null ? to : latestSnapshot;
		if (end == null) {
			return Optional.empty();
		}

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
		return Optional.of(new SnapshotWindow(start, end));
	}
}
