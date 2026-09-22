package com.ssafy.pickage.domain.packages;

import java.math.BigDecimal;

/**
 * 이동쌍 서빙 기준 — <b>필터와 등급이 사는 유일한 자리</b> (S15P21A506-211 결정 1·2·4).
 *
 * <p>결정 4가 요구하는 것이 이 클래스의 존재 이유다. 전체 흐름 · 패키지 focus · 최대 6개
 * 방향이 <b>같은 값을 참조해야 한다.</b> 화면이나 질의마다 하한을 따로 적으면, 한 곳만 고쳐진
 * 채로 두 화면이 다른 규칙으로 돌면서도 둘 다 그럴듯해 보인다.
 *
 * <h2>적재 기준과 표시 기준은 다르다</h2>
 *
 * <p>표에는 loose 전량({@code lift>=5 AND votes>=3})이 들어 있다. 여기 값들은 <b>적재를
 * 거르지 않는다</b> — 조회가 붙이는 기준이다. 그래서 기준이 바뀌어도 재적재하지 않는다
 * (결정 1). {@code lift>=5} 를 여기 두지 않은 것도 같은 이유다. 그건 표의
 * {@code CK_MIGRATION_PAIR_LOOSE} 가 이미 보장한다.
 */
public final class MigrationPairFilter {

	private MigrationPairFilter() {
	}

	/* ------------------------------------------------------------------ *
	 * 기본 필터 — 화면에 개별 행으로 세울 자격
	 * ------------------------------------------------------------------ */

	/**
	 * 몇 번 바뀌었나. 가중 합이라 정수가 아니다.
	 *
	 * <p><b>이 값만으로 거르면 정밀도가 22% 다.</b> 아래 {@link #MIN_PUBLISHER_MONTHS} 와
	 * 함께 써야 73~81% 가 된다(S15P21A506-136 §1).
	 */
	public static final BigDecimal MIN_VOTES = new BigDecimal("5");

	/**
	 * 서로 다른 (발행자 × 달) 이 몇 개인가. <b>votes 보다 위에 있는 조건이다</b>(결정 2).
	 *
	 * <p>한 조직이 자기 패키지 수십 개를 한 달에 일괄 변경하면 votes 만 커지고 이 수는 1 이다.
	 * 결정 2가 고정한 것은 SQL 실행 순서가 아니라 <b>완화할 때 푸는 순서</b>이고, 이 조건은
	 * votes 보다 <b>나중에</b> 푼다.
	 */
	public static final int MIN_PUBLISHER_MONTHS = 3;

	/** 개별 행으로 세우는 도착지 수. 나머지는 하나로 접는다(S15P21A506-136 §1 — 상위 5가 66%). */
	public static final int TOP_DESTINATIONS = 5;

	/* ------------------------------------------------------------------ *
	 * 근거 강도 배지 — 행을 지우지 않고 색만 달리 한다 (결정 1)
	 * ------------------------------------------------------------------ */

	/** 확실한 것. 화면 노출·발표용. {@code build_migration_pairs.py} 의 {@code STRICT} 와 같다. */
	public static final String STRICT = "strict";
	/** AI 학습 라벨용 기본값. 같은 파일의 {@code RECOMMENDED} 와 같다. */
	public static final String RECOMMENDED = "recommended";
	/** 표에 들어 있는 것 전부. 위 둘에 못 미치는 행이 여기다. */
	public static final String LOOSE = "loose";

	// 아래 임계값은 **빌더의 문자열 조건을 옮겨 적은 것이다**
	// (pipeline/duckdb/build_migration_pairs.py:329·331).
	//
	//   STRICT      = lift>=5 AND votes>=12 AND publisher_months>=10 AND a_rate>=0.03
	//   RECOMMENDED = lift>=5 AND votes>=8  AND publisher_months>=5  AND share>=0.10
	//
	// 빌더는 비율(a_rate·share)로 쓰고 CSV 는 백분율(a_pct·share_pct)로 내므로 100 을 곱했다.
	// **빌더를 고치면 여기도 고쳐야 한다.** 두 곳이 갈라지면 같은 쌍이 CSV 에서는 strict 인데
	// 화면에서는 loose 로 보인다 — 배지만 어긋나고 수는 맞으므로 알아채기 어렵다.
	// 그 대신 얻는 것은 재적재 없이 등급을 바꿀 수 있다는 것이다(결정 1).
	private static final BigDecimal STRICT_VOTES = new BigDecimal("12");
	private static final int STRICT_PUBLISHER_MONTHS = 10;
	private static final BigDecimal STRICT_A_PCT = new BigDecimal("3");
	private static final BigDecimal RECOMMENDED_VOTES = new BigDecimal("8");
	private static final int RECOMMENDED_PUBLISHER_MONTHS = 5;
	private static final BigDecimal RECOMMENDED_SHARE_PCT = new BigDecimal("10");

	/**
	 * 이 쌍이 어느 등급인가.
	 *
	 * <p><b>strict 와 recommended 는 포함 관계가 아니다.</b> strict 는 "X 를 뺀 전이 중 Y 를
	 * 함께 넣은 비율"({@code a_pct})을 보고, recommended 는 "X 의 도착지 중 Y 의 몫"
	 * ({@code share_pct})을 본다. 그래서 strict 인데 recommended 가 아닌 쌍이 있다.
	 * 더 센 것부터 확인하는 이 순서가 곧 표시 우선순위다.
	 */
	public static String grade(BigDecimal votes, int publisherMonths, BigDecimal aPct,
		BigDecimal sharePct) {
		if (atLeast(votes, STRICT_VOTES) && publisherMonths >= STRICT_PUBLISHER_MONTHS
			&& atLeast(aPct, STRICT_A_PCT)) {
			return STRICT;
		}
		if (atLeast(votes, RECOMMENDED_VOTES) && publisherMonths >= RECOMMENDED_PUBLISHER_MONTHS
			&& atLeast(sharePct, RECOMMENDED_SHARE_PCT)) {
			return RECOMMENDED;
		}
		return LOOSE;
	}

	/** 기본 필터를 통과하는가. 조회 SQL 과 <b>같은 값</b>을 쓰기 위해 여기 둔다. */
	public static boolean passesDefault(BigDecimal votes, int publisherMonths) {
		return atLeast(votes, MIN_VOTES) && publisherMonths >= MIN_PUBLISHER_MONTHS;
	}

	// BigDecimal 은 equals 가 소수 자릿수까지 보므로(5 != 5.0) compareTo 로만 비교한다.
	// 적재된 votes 는 NUMERIC(10,1) 이라 실제로 5.0 으로 올라온다 — equals 를 쓰면
	// 경계값 한 줄이 조용히 탈락한다.
	private static boolean atLeast(BigDecimal value, BigDecimal bound) {
		return value != null && value.compareTo(bound) >= 0;
	}
}
