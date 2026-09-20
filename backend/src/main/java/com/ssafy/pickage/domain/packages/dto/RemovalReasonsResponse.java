package com.ssafy.pickage.domain.packages.dto;

import java.time.LocalDate;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 구간별 이탈 사유 응답 (기능-08 · S15P21A506-396).
 *
 * <p>"X 를 뺀 사람들이 그 자리에 다른 것을 넣었나, 그냥 뺐나". 배치가 미리 접어 둔
 * {@code dependent_removal_reason} 을 키 조회 한 번으로 읽는다.
 *
 * <h2>{@link TransitionsResponse} 와 <b>단위가 다르다.</b> 합치거나 나누면 안 된다</h2>
 *
 * <table border="1">
 * <caption>두 지표의 차이</caption>
 * <tr><th></th><th>유지·유입·이탈</th><th>이탈 사유</th></tr>
 * <tr><td>계산</td><td>시점 두 개의 선언 집합 비교</td><td>연속한 두 릴리스를 훑음</td></tr>
 * <tr><td>단위</td><td><b>패키지 수</b></td><td><b>전이 건수</b></td></tr>
 * </table>
 *
 * <p>{@code outflow} 는 "T1 엔 쓰고 T2 엔 안 쓰는 패키지가 몇 개인가" 이고 {@code removals} 는
 * "그 사이 빼는 행위가 몇 번 있었나" 다. 한 의존자가 뺐다 넣었다 다시 뺐으면 앞은 1, 뒤는 2다.
 *
 * <p><b>그래서 응답을 따로 낸다.</b> 같은 객체에 담으면 받는 쪽이 반드시 더하거나 나눈다.
 * 그리고 {@code unit} 을 <b>값으로</b> 싣는다 — 주석이나 문서가 아니라 필드여야 화면이
 * 캡션에 쓸 수 있다.
 *
 * <p>대신 <b>구간과 기준일은 같다.</b> 적재기가 {@code dependent_transition} 에서 t1·t2 를
 * 가져오므로 두 응답의 {@code t1}·{@code t2} 는 같은 값이다. 한 화면에 나란히 놓아도 기준일이
 * 어긋나지 않는다.
 *
 * @param period    요청한 구간. 생략 시 적용된 기본값을 그대로 돌려준다.
 * @param t1        구간 시작 <b>날짜</b>. {@code transitions} 응답의 같은 이름과 같은 값이다.
 * @param t2        구간 끝 <b>날짜</b> = 원천 스냅샷 날짜. "오늘" 이 아니다.
 * @param series    <b>한 패키지가 한 줄이다.</b> {@code transitions} 와 달리 {@code kind}
 *                  차원이 없다 — 원천이 선언 종류를 나누지 않는다.
 * @param notFound  {@code package} 테이블에 아예 없는 이름.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record RemovalReasonsResponse(
	String metric,
	String period,
	LocalDate t1,
	LocalDate t2,
	List<Series> series,
	List<String> notFound
) {

	public static final String METRIC = "removal_reasons";

	/**
	 * 이 수의 단위. <b>패키지 수가 아니라 전이 건수다.</b>
	 *
	 * <p>{@code transitions} 의 수와 나란히 두고 더하거나 비율을 내면 안 된다는 것을
	 * 응답만 보고 알 수 있어야 해서 값으로 싣는다.
	 */
	public static final String UNIT = "transitions";

	// 네 상태의 뜻은 transitions 와 **같아야 한다.** 화면이 두 패널에 같은 분기를 쓴다.
	// 문자열을 다시 적지 않고 그대로 가리키는 것은, 한쪽만 고쳐져 두 패널이 다른 규칙으로
	// 도는 것을 막기 위해서다.
	/** 정상. 수가 들어 있다. */
	public static final String COMPLETE = TransitionsResponse.COMPLETE;
	/**
	 * 대상은 맞는데 이 구간에 <b>한 번도 빠진 적이 없다.</b> 0 이 맞는 값이다.
	 *
	 * <p>드물지 않다 — 대상 97,745개 중 <b>57,201개(58.5%)</b>가 여기다. 이걸
	 * {@code OUT_OF_SCOPE} 로 내보내면 화면이 절반 넘는 패키지에 "분석 대상이 아닙니다" 를
	 * 띄운다. 그래서 조회가 {@code dependent_transition} 을 함께 본다.
	 */
	public static final String NO_DATA = TransitionsResponse.NO_DATA;
	/** 유지·유입·이탈 대상이 아니다. 0 이 아니라 {@code null} 이다 — <b>세어 보지 않았다.</b> */
	public static final String OUT_OF_SCOPE = TransitionsResponse.OUT_OF_SCOPE;
	/** 회차가 아직 적재되지 않았다. 표 자체가 비어 있다. */
	public static final String NOT_COMPUTED = TransitionsResponse.NOT_COMPUTED;

	/** 이 수를 센 모집단. {@code transitions} 와 같다. */
	public static final String NPM_ALL = TransitionsResponse.NPM_ALL;

	public static RemovalReasonsResponse of(String period, LocalDate t1, LocalDate t2,
		List<Series> series, List<String> notFound) {
		return new RemovalReasonsResponse(METRIC, period, t1, t2, series, notFound);
	}

	/**
	 * 한 패키지의 한 구간.
	 *
	 * <p><b>{@code dependents} 로 {@code removals} 를 나누지 말 것.</b> 단위가 달라서 나온
	 * 값("의존자당 평균 제거 횟수")은 해석할 수 있는 수가 아니다. 두 열을 함께 주는 것은
	 * "몇 번 일어났나" 와 "몇 명이 했나" 가 다르다는 것을 보이기 위해서다 — 한 의존자가
	 * 반복해서 넣었다 뺐다 하면 {@code removals} 만 커진다.
	 *
	 * @param population       이 수를 센 모집단. 지금은 전부 {@code npm_all}.
	 * @param unit             {@code transitions}. 패키지 수가 아니라 전이 건수라는 표시.
	 * @param removals         X 를 뺀 전이의 수.
	 * @param noReplacement    뺀 릴리스에서 <b>아무것도 새로 넣지 않은</b> 전이.
	 * @param withReplacement  뺀 릴리스에서 다른 것을 함께 넣은 전이. <b>같은 자리의 대체라는
	 *                         보장은 없다</b> — 한 릴리스에 섞인 대청소일 수 있다.
	 * @param dependents       X 를 뺀 적 있는 <b>의존자 수</b>(중복 접음). 위 셋과 단위가 다르다.
	 * @param dataStatus       {@code COMPLETE} · {@code NO_DATA} · {@code OUT_OF_SCOPE} ·
	 *                         {@code NOT_COMPUTED}.
	 */
	@JsonInclude(JsonInclude.Include.ALWAYS)
	public record Series(
		String name,
		String population,
		String unit,
		Integer removals,
		Integer noReplacement,
		Integer withReplacement,
		Integer dependents,
		String dataStatus
	) {

		/** 수가 들어 있는 행. */
		public static Series counted(String name, int removals, int noReplacement,
			int withReplacement, int dependents) {
			return new Series(name, NPM_ALL, UNIT, removals, noReplacement, withReplacement,
				dependents, COMPLETE);
		}

		/**
		 * 대상인데 이 구간에 제거가 한 건도 없다. <b>0 이 맞는 값이라 {@code null} 로 두지
		 * 않는다</b> — 적재기가 {@code removals > 0} 인 행만 넣으므로 표에 행이 없는 것이
		 * 곧 "세어 보니 없었다" 다.
		 */
		public static Series none(String name) {
			return new Series(name, NPM_ALL, UNIT, 0, 0, 0, 0, NO_DATA);
		}

		/**
		 * 세어 보지 않은 행. 수를 전부 {@code null} 로 둔다.
		 *
		 * @param status {@code OUT_OF_SCOPE}(대상 밖) 또는 {@code NOT_COMPUTED}(회차 미적재)
		 */
		public static Series unknown(String name, String status) {
			return new Series(name, NPM_ALL, UNIT, null, null, null, null, status);
		}
	}
}
