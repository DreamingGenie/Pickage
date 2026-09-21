package com.ssafy.pickage.domain.packages.dto;

import java.time.LocalDate;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 유지·유입·이탈 응답 (기능-08 · 구상안 §12.6).
 *
 * <p>배치가 미리 계산해 둔 {@code dependent_transition} 을 키 조회 한 번으로 읽는다.
 * 구간을 프리셋으로 묶은 것이 이것을 가능하게 했다 — 임의 날짜를 받으면 요청마다 수천만 행을
 * 집계해야 한다(react 하나가 regular dependent 192,736 개다).
 *
 * <h2>MVP 의 signed {@code delta} 와 다른 지표다</h2>
 *
 * {@code DEC-DEPENDENCY-DELTA-20260910-01}. {@code /packages/dependents} 의 증감은
 * <b>버전별 합계의 총수 차이</b>이고, 이쪽은 <b>dependent 를 이름으로 식별한 상태 전이</b>다.
 * {@code delta = inflow - outflow} 는 성립하지 않는다 — 모집단도 계산도 다르다.
 *
 * @param period    요청한 구간. 생략 시 적용된 기본값을 그대로 돌려준다 — 화면이 무엇을
 *                  물었는지 알아야 한다.
 * @param t1        구간 시작 <b>날짜</b>. 그날 23:59:59 까지 발행된 것이 T1 시점이다.
 * @param t2        구간 끝 <b>날짜</b> = 원천 스냅샷 날짜. <b>"오늘" 이 아니다</b> — 매일 값이
 *                  바뀌면 어제 본 숫자와 달라지므로 고정한다. 저장은 23:59:59 까지 담고 여기서
 *                  날짜만 잘라 준다. 기존 조회들이 {@code snapshot_at} 을 날짜로 주는 것과 맞춘다.
 * @param series    <b>한 패키지가 {@code kind} 수만큼 반복된다.</b> {@code /packages/dependents} 가
 *                  major 별로 같은 {@code name} 을 반복하는 것과 같은 모양이다.
 * @param notFound  {@code package} 테이블에 아예 없는 이름. {@code OUT_OF_SCOPE} 와 다르다 —
 *                  그쪽은 이름은 있는데 계산 대상이 아닌 것이다.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record TransitionsResponse(
	String metric,
	String period,
	LocalDate t1,
	LocalDate t2,
	List<Series> series,
	List<String> notFound
) {

	public static final String METRIC = "dependent_transitions";

	/** 정상. 네 범주에 수가 들어 있다. */
	public static final String COMPLETE = "COMPLETE";
	/** 대상은 맞는데 그 {@code kind} 의 dependent 가 하나도 없다. <b>0 이 맞는 값이다.</b> */
	public static final String NO_DATA = "NO_DATA";
	/**
	 * 다운로드 상위 10만 밖이라 계산 대상이 아니다. <b>0 이 아니라 {@code null} 을 준다</b> —
	 * 0 으로 주면 "의존자가 없다" 로 읽히는데 실제로는 <b>세어 보지 않은</b> 것이다.
	 *
	 * <p>생각보다 자주 나온다. 대상 목록은 ecosyste.ms 순위(2026-09-02)이고
	 * {@code package} 는 deps.dev 스냅샷(2026-08-31)에서 와서, 저쪽에는 있는데 이쪽에
	 * 적격 릴리스가 없는 패키지가 2,251개(2.3%) 있다.
	 */
	public static final String OUT_OF_SCOPE = "OUT_OF_SCOPE";
	/** 회차가 아직 적재되지 않았다. 표 자체가 비어 있는 상태다. */
	public static final String NOT_COMPUTED = "NOT_COMPUTED";

	/** 이 수를 센 모집단. dev 회차가 붙으면 그쪽만 {@code top100k} 이 된다. */
	public static final String NPM_ALL = "npm_all";

	public static TransitionsResponse of(String period, LocalDate t1, LocalDate t2,
		List<Series> series, List<String> notFound) {
		return new TransitionsResponse(METRIC, period, t1, t2, series, notFound);
	}

	/**
	 * 한 패키지의 한 {@code kind}.
	 *
	 * <p><b>네 범주를 모두 화면에 내야 한다.</b> {@code unobserved} 를 {@code retained} 에
	 * 합치면 숫자가 거짓이 된다 — 1년 구간에서 전체의 75.3% 가 여기 들어가고, 합치면
	 * 유지율이 87.2% 가 아니라 98.8% 로 보인다. 기능-08-R03 이 "자료 없음을 이탈로 분류하지
	 * 않는다" 고 못 박은 것과 같은 이유로 유지로 분류하는 것도 잘못이다.
	 *
	 * @param population     이 수를 센 모집단. 지금은 전부 {@code npm_all}(4,065,913).
	 * @param retained       <b>계속 씀</b> — 구간 안에 새 릴리스를 내면서도 계속 선언했다.
	 * @param inflow         <b>새로 씀</b> — T1 엔 없고 T2 엔 있다.
	 * @param inflowNew      그중 <b>T1 때 아직 존재하지도 않던</b> 패키지. {@code inflow} 의 부분집합.
	 * @param inflowAdopted  {@code inflow - inflowNew}. <b>기존 패키지가 실제로 채택한 수</b>다.
	 *                       파생값이지만 서버가 직접 주는 이유는, 뺄셈은 자명해도 <b>무엇을
	 *                       빼야 하는지가 자명하지 않기</b> 때문이다. {@code inflow} 를 그대로
	 *                       그리면 모든 패키지가 다 잘나가는 지표가 되는데, 숫자 자체는 맞아서
	 *                       틀렸다는 것을 아무도 모른다. 실측상 유입의 93.8~97.5% 가 신생이다.
	 * @param outflow        <b>그만 씀</b> — T1 엔 있고 T2 엔 없다.
	 * @param unobserved     <b>판정 불가</b> — 양 끝에 선언이 있는데 구간 안에 대표 릴리스가
	 *                       바뀌지 않았다. 계속 쓰는지 뺐는지 <b>알 방법이 없다.</b>
	 * @param unobservedRecent   {@code unobserved} 중 마지막 대표 릴리스가 {@code t2} 기준
	 *                       <b>3년 안</b>. 셋의 합이 {@code unobserved} 다.
	 * @param unobservedStale    그중 <b>3~5년 전</b>.
	 * @param unobservedDormant  그중 <b>5년 초과</b> — 사실상 방치된 프로젝트다. 기본 구간(3년)
	 *                       에서 판정 불가의 63.2% 가 여기다. "판정할 수 없다" 와 "사실상
	 *                       죽었다" 는 받는 쪽에 전혀 다른 정보다.
	 * @param dataStatus     {@code COMPLETE} · {@code NO_DATA} · {@code OUT_OF_SCOPE} ·
	 *                       {@code NOT_COMPUTED}. 0 과 "모름" 을 구분하기 위한 값이다.
	 */
	@JsonInclude(JsonInclude.Include.ALWAYS)
	public record Series(
		String name,
		String kind,
		String population,
		Integer retained,
		Integer inflow,
		Integer inflowNew,
		Integer inflowAdopted,
		Integer outflow,
		Integer unobserved,
		Integer unobservedRecent,
		Integer unobservedStale,
		Integer unobservedDormant,
		String dataStatus
	) {

		/**
		 * 수가 들어 있는 행. {@code inflowAdopted} 는 여기서 계산한다.
		 *
		 * <p><b>분해 셋은 {@code dataStatus} 와 별개로 {@code null} 일 수 있다.</b>
		 * {@code COMPLETE} 인데도 셋만 {@code null} 인 상태가 정상적으로 존재한다 —
		 * 마이그레이션(배포)과 재적재 사이에는 분해를 모르는 행이 표에 남아 있기 때문이다
		 * (S15P21A506-421 · {@code V11}). 그때 0 을 주면 "5년 넘게 방치된 의존자가 0명" 이
		 * 되어 숫자가 맞아 보이는 거짓이 된다. 받는 쪽은 셋이 {@code null} 이면 분해를
		 * 그리지 않는다.
		 *
		 * <p>셋은 <b>전부 있거나 전부 없다.</b> 일부만 채워진 행은 DB CHECK 가 막는다.
		 */
		public static Series counted(String name, String kind, int retained, int inflow,
			int inflowNew, int outflow, int unobserved,
			Integer unobservedRecent, Integer unobservedStale, Integer unobservedDormant) {
			boolean empty = retained == 0 && inflow == 0 && outflow == 0 && unobserved == 0;
			return new Series(name, kind, NPM_ALL, retained, inflow, inflowNew,
				inflow - inflowNew, outflow, unobserved,
				unobservedRecent, unobservedStale, unobservedDormant,
				empty ? NO_DATA : COMPLETE);
		}

		/**
		 * 세어 보지 않은 행. 수를 전부 {@code null} 로 둔다.
		 *
		 * @param status {@code OUT_OF_SCOPE}(계산 대상 밖) 또는 {@code NOT_COMPUTED}(회차 미적재)
		 */
		public static Series unknown(String name, String kind, String status) {
			return new Series(name, kind, NPM_ALL, null, null, null, null, null, null,
				null, null, null, status);
		}
	}
}
