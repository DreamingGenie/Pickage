package com.ssafy.pickage.domain.packages.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.ssafy.pickage.domain.packages.DependencyKind;

/**
 * 관측된 교체 흐름 — "X 를 떠난 사람들은 어디로 갔나" (확장-02 · S15P21A506-424).
 *
 * <h2>{@link RemovalReasonsResponse} 와 답하는 질문이 다르다</h2>
 *
 * <table border="1">
 * <caption>세 응답의 역할</caption>
 * <tr><th></th><th>묻는 것</th><th>단위</th></tr>
 * <tr><td>{@link TransitionsResponse}</td><td>몇 개가 떠났나</td><td>패키지 수</td></tr>
 * <tr><td>{@link RemovalReasonsResponse}</td><td>대체를 동반했나</td><td>전이 건수</td></tr>
 * <tr><td>이 응답</td><td><b>어디로 갔나</b></td><td>가중 표(votes)</td></tr>
 * </table>
 *
 * <p>{@code removal-reasons} 의 {@code withReplacement} 는 <b>수일 뿐 도착지 이름이 없고</b>,
 * 그 주석이 적어 둔 대로 "같은 자리의 대체라는 보장"도 없다. 이 응답만이 이름을 답한다.
 *
 * <p><b>세 수를 더하거나 비율을 내면 안 된다.</b> 단위가 셋 다 다르다.
 *
 * <h2>기준일이 응답에 실려 있다</h2>
 *
 * <p>{@code snapshotAt} 은 종류마다 다르다 — {@code regular} 2026-08-31,
 * {@code dev} 2026-09-16. 서버가 계산하지 않고 <b>표가 가진 값</b>을 그대로 낸다. 읽을 행이
 * 없으면 {@code null} 이다. 지어낸 날짜를 내보내지 않는 것은 {@link TransitionsResponse} 와
 * 같은 규칙이다.
 *
 * @param metric    고정 문자열. 화면이 응답 종류를 분기하는 키다.
 * @param kind      적용된 {@link DependencyKind}. 생략 시 기본값을 그대로 돌려준다.
 * @param series    한 패키지가 한 줄이다.
 * @param notFound  {@code package} 표에 아예 없는 이름.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record MigrationPairsResponse(
	String metric,
	String kind,
	List<Series> series,
	List<String> notFound
) {

	public static final String METRIC = "migration_pairs";

	/**
	 * 점유율의 <b>분모</b>가 무엇인가.
	 *
	 * <p>표(votes)가 아니라 서로 다른 (발행자 × 달) 의 수다(S15P21A506-281·결정 2). 한 조직이
	 * 자기 패키지 수십 개를 한 달에 일괄 변경해도 이 분모는 1 만 는다. node-fetch 의 1위가
	 * 표 기준으로는 form-data(조직·달 8)인데 이 기준으로는 axios 로 바뀐다.
	 *
	 * <p><b>값으로 싣는 이유</b>는 {@link RemovalReasonsResponse#UNIT} 과 같다 — 주석이
	 * 아니라 필드여야 화면이 캡션에 쓴다.
	 */
	public static final String SHARE_BASIS = "publisher_months";

	// 네 상태 중 셋은 **transitions 와 같은 문자열이어야 한다.** 화면이 세 패널에 같은 분기를
	// 쓴다. 다시 적지 않고 가리키는 것은 한쪽만 고쳐지는 것을 막기 위해서다.
	/** 기본 필터를 통과한 도착지가 있다. */
	public static final String COMPLETE = TransitionsResponse.COMPLETE;
	/**
	 * 이동 기록이 없다. <b>0 이 맞는 값이다</b> — 이 패키지를 뺀 릴리스에서 무엇을 함께
	 * 넣었는지가 한 번도 관측되지 않았다.
	 *
	 * <p>드물지 않다. 상위 10만 중 64,034개가 여기이고, <b>데이터를 더 돌려도 나오지
	 * 않는다</b> — 의존하는 공개 패키지가 없어 원천에 기록 자체가 없다(S15P21A506-136 §1).
	 */
	public static final String NO_DATA = TransitionsResponse.NO_DATA;
	/** 이 종류의 회차가 아직 적재되지 않았다. 표 자체가 비어 있다. */
	public static final String NOT_COMPUTED = TransitionsResponse.NOT_COMPUTED;
	/**
	 * <b>쌍은 있으나 근거가 약하다</b> — 기본 필터를 통과한 도착지가 하나도 없다
	 * (S15P21A506-211 결정 5).
	 *
	 * <p>이 상태가 따로 필요한 이유는 {@link #NO_DATA} 와 <b>화면 문구가 반대</b>이기
	 * 때문이다. 저쪽은 "이동이 관측되지 않았습니다"(더 볼 것이 없다)이고, 이쪽은 "근거가
	 * 약해 감춥니다"(값은 있다)다. 하나로 합치면 관측된 이동이 있는 패키지에 "없음" 을
	 * 띄우게 된다.
	 *
	 * <p>이 경우에도 {@code destinations} 는 비지 않는다 — 접힌 {@code etc} 에 그 쌍들의
	 * 몫이 들어 있다.
	 */
	public static final String INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE";

	public static MigrationPairsResponse of(DependencyKind kind, List<Series> series,
		List<String> notFound) {
		return new MigrationPairsResponse(METRIC, kind.code(), series, notFound);
	}

	/**
	 * 한 패키지의 도착지 분포.
	 *
	 * @param snapshotAt    이 종류의 기준일. 읽을 행이 없으면 {@code null}.
	 * @param shareBasis    {@link #SHARE_BASIS}. 점유율 분모가 표가 아니라는 표시.
	 * @param destinations  상위 {@code TOP_DESTINATIONS} 개. 기본 필터를 통과한 것만,
	 *                      점유율 내림차순.
	 * @param etc           그 밖 전부를 접은 한 칸. <b>기본 필터에 못 미친 쌍도 여기 들어간다</b>
	 *                      — 그래야 {@code destinations + etc} 가 이 패키지의 관측된 이동
	 *                      전부가 되어 차트가 100% 를 이룬다. {@code null} 이면 접을 것이 없다.
	 * @param observedPairs 이 패키지에서 관측된 이동쌍 수(필터 전). 0 이면 {@link #NO_DATA}.
	 * @param dataStatus    {@code COMPLETE} · {@code INSUFFICIENT_EVIDENCE} · {@code NO_DATA} ·
	 *                      {@code NOT_COMPUTED}.
	 */
	@JsonInclude(JsonInclude.Include.ALWAYS)
	public record Series(
		String name,
		LocalDate snapshotAt,
		String shareBasis,
		List<Destination> destinations,
		Etc etc,
		Integer observedPairs,
		String dataStatus
	) {

		public static Series of(String name, LocalDate snapshotAt, List<Destination> destinations,
			Etc etc, int observedPairs, String dataStatus) {
			return new Series(name, snapshotAt, SHARE_BASIS, destinations, etc, observedPairs,
				dataStatus);
		}

		/**
		 * 세어 보지 않은 행. {@code observedPairs} 까지 {@code null} 로 둔다 — 0 으로 두면
		 * "관측해 보니 없었다" 와 구분되지 않는다.
		 */
		public static Series unknown(String name, String status) {
			return new Series(name, null, SHARE_BASIS, List.of(), null, null, status);
		}
	}

	/**
	 * 도착지 하나.
	 *
	 * <p><b>이름만 있고 {@code packageId} 가 없다.</b> 도착지 327쌍은 우리 {@code package}
	 * 표에 없는데, 그중 <b>61건이 기본 필터를 통과하면서 출발 패키지의 상위 5 안에 든다</b>
	 * (출발 55개, 점유율 100% 인 것 포함). 표에 FK 를 걸지 않은 것이 같은 이유다(V13 머리말).
	 * 화면은 이름으로 그리고, 상세로 갈 수 있는지는 별도 조회로 판단한다.
	 *
	 * @param sharePmPct  점유율. 분모는 {@link #SHARE_BASIS} 다.
	 * @param sharePct    표 기준 점유율. <b>라벨 필터용으로만 남긴 값이고 화면에 쓰지
	 *                    않는다</b>(S15P21A506-136 §3). 등급 판정의 입력이라 함께 낸다.
	 * @param evidence    {@code strict} · {@code recommended} · {@code loose}. 행을 지우는
	 *                    대신 붙이는 배지다(결정 1).
	 * @param variant     양방향 관측. <b>"같은 물건의 두 포장" 일 수 있다</b>(lodash ↔
	 *                    lodash-es). 지우지 말고 색만 달리 한다(결정 4 ③).
	 * @param lift        모집단 대비 배수. <b>다른 종류와 절댓값을 비교하지 말 것</b> —
	 *                    분모가 그 실행의 전이 수다.
	 */
	public record Destination(
		String name,
		BigDecimal votes,
		Integer coEvents,
		Integer publisherMonths,
		Integer dependents,
		BigDecimal lift,
		BigDecimal sharePmPct,
		BigDecimal sharePct,
		String evidence,
		boolean variant,
		LocalDate firstSeen,
		LocalDate lastSeen
	) {
	}

	/**
	 * 상위 밖을 접은 칸.
	 *
	 * <p><b>이 칸의 대부분은 잡음이다.</b> 꼬리의 82%가 "서로 다른 조직·달이 3개 미만" 인
	 * 일회성 추가다(S15P21A506-136 §1). 그래서 이름을 세우지 않고 접는다. 다만 지우지는
	 * 않는다 — 접은 몫을 보여야 상위 5개의 점유율을 읽을 수 있다.
	 *
	 * @param pairs       접은 쌍의 수.
	 * @param sharePmPct  접은 쌍의 점유율 합.
	 * @param belowFilter 그중 기본 필터에 못 미친 수. 화면이 "근거가 약해 접었다" 를 말할 근거다.
	 */
	public record Etc(int pairs, BigDecimal sharePmPct, int belowFilter) {
	}
}
