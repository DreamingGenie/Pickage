package com.ssafy.pickage.domain.packages;


import java.util.List;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 유지·유입·이탈 조회 구간 (기능-08).
 *
 * <p><b>프리셋만 받는다.</b> 임의 날짜를 허용하면 요청마다 수천만 행을 집계해야 한다 —
 * {@code react} 하나가 regular dependent 192,736 개다. 배치가 세 구간을 미리 접어 두고
 * 조회는 키 하나로 끝낸다.
 *
 * <p>이름이 {@code window} 가 아니라 {@code period} 인 것은 <b>{@code window} 가
 * DuckDB·PostgreSQL 예약어</b>이기 때문이다. 열 이름으로 쓰면 따옴표 없이 못 쓰고, 개발 중
 * 실제로 파서 오류가 났다. 파이프라인·DB·API 가 같은 이름을 쓰도록 여기서도 {@code period} 다.
 *
 * <p>값은 DB 의 {@code CK_DEPENDENT_TRANSITION_PERIOD} 와 같아야 한다. 프리셋을 늘릴 때는
 * <b>네 곳을 함께</b> 고친다 — 이 목록 · 그 제약 · 파이프라인의 {@code PERIOD_YEARS} ·
 * 그리고 <b>새 구간의 행이 실제로 적재된 뒤에 배포한다.</b>
 *
 * <p>마지막 항목이 순서 문제라 놓치기 쉽다. 프리셋만 먼저 늘리고 파이프라인이 아직 그
 * 구간을 내지 않은 상태로 배포하면, 조회는 빈 결과가 되는데
 * {@code PackageQueryRepository#hasAnyTransition()} 은 <b>구간을 보지 않고</b> 표에 뭐라도
 * 있는지만 확인하므로 참을 돌려준다. 그 결과 계산 대상인 패키지가
 * {@code NOT_COMPUTED}(준비 중)가 아니라 {@code OUT_OF_SCOPE}(대상 아님)로 나가고,
 * 화면은 "이 패키지는 분석 대상이 아닙니다" 를 영영 띄운다.
 *
 * <p>그 검사를 구간별로 바꾸지 않은 것은 의도다 — PK 가
 * {@code (package_id, period, kind)} 라 {@code period} 단독 조건은 인덱스를 타지 못하고,
 * 행이 구간별로 뭉쳐 있어 순차 스캔이 수십만 행을 훑는다. 조회 결과가 빌 때마다 그 비용을
 * 내는 것보다, 프리셋을 늘리는 드문 일에 순서를 지키는 쪽이 싸다.
 */
public enum TransitionPeriod {

	ONE_YEAR("1y"),
	THREE_YEARS("3y"),
	FIVE_YEARS("5y");

	/** 화면이 아무것도 고르지 않았을 때. 관측 가능 비중이 절반(49.2%)이라 셋 중 가장 균형이 좋다. */
	public static final TransitionPeriod DEFAULT = THREE_YEARS;

	private final String code;

	TransitionPeriod(String code) {
		this.code = code;
	}

	public String code() {
		return code;
	}

	/**
	 * 프리셋 밖의 값은 <b>빈 결과가 아니라 400</b> 이다.
	 *
	 * <p>조용히 기본값으로 떨어뜨리면 화면은 "3년" 을 보면서 "2년" 을 요청했다고 믿는다.
	 * 응답의 {@code period} 가 요청과 다르다는 것을 알아차리기 어렵다.
	 */
	public static TransitionPeriod of(String raw) {
		if (raw == null || raw.isBlank()) {
			return DEFAULT;
		}
		String value = raw.trim();
		for (TransitionPeriod period : values()) {
			if (period.code.equals(value)) {
				return period;
			}
		}
		throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT,
			"period는 %s 중 하나여야 합니다: %s".formatted(codes(), value));
	}

	public static List<String> codes() {
		return List.of(ONE_YEAR.code, THREE_YEARS.code, FIVE_YEARS.code);
	}

	// 구간 시작 날짜를 여기서 계산하지 않는다. 응답의 t1·t2 는 **표가 가진 값만** 쓴다 —
	// 서버가 따로 계산하면 파이프라인이 구간 정의를 바꿨을 때 조용히 어긋나고, 읽을 행이
	// 없을 때는 지어낸 날짜를 내보내게 된다. 모르면 null 이다.
}
