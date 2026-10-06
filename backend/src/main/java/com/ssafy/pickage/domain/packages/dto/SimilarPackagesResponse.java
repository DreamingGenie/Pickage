package com.ssafy.pickage.domain.packages.dto;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 유사 패키지 응답 (기능-03 · UC4).
 *
 * <p>배치가 미리 계산해 둔 {@code similar_package} 를 키 조회 한 번으로 읽는다.
 * <b>요청 경로에 모델이 없다</b> — 사용자 요청 때문에 임베딩이 도는 일은 없다.
 *
 * <h2>배치 입력이 아니라 기준 패키지 하나다</h2>
 *
 * 다른 조회들은 {@code names=a,b,c} 로 최대 3개를 받는데, 여기는 {@code name} 하나다.
 * "무엇의 대체재인가" 를 물으므로 기준이 둘일 수 없다. 상한 3개는 <b>비교 화면</b>의 규칙이라
 * 이 엔드포인트와 무관하다.
 *
 * @param base       기준 패키지 이름. 요청한 값을 그대로 돌려준다 — 화면이 무엇을 물었는지 알아야 한다.
 * @param modelVer   이 목록을 만든 모델. <b>스냅샷 날짜 대신 계보를 표시하는 값</b>이라 화면에 낸다.
 *                   목록이 비면 {@code null} 이다(만든 모델이 없다).
 * @param dataStatus {@code COMPLETE} 또는 {@code NO_DATA}. 후보 retrieval·ranking 실패는 배치가
 *                   상태를 남기기 시작하면 여기에 붙는다(구상안 §4.4). 지금은 두 값뿐이다.
 * @param candidates {@code rank} 오름차순. 빈 배열은 <b>아직 계산되지 않았다</b>는 뜻이며
 *                   오류가 아니다. 기준 이름이 없는 경우와 구분해야 한다 — 그쪽은 {@code not_found} 다.
 * @param notFound   {@code package} 테이블에 아예 없는 이름. 있으면 원소 하나뿐이다(기준이 하나이므로).
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record SimilarPackagesResponse(
	String base,
	String modelVer,
	String dataStatus,
	List<Candidate> candidates,
	List<String> notFound
) {

	/** 목록이 비었을 때. 모델 버전도 없다 — 만든 것이 없으므로 지어내지 않는다. */
	public static final String NO_DATA = "NO_DATA";
	public static final String COMPLETE = "COMPLETE";

	/** limit 기본·상한. 상한은 {@code CK_SIMILAR_PACKAGE_RANK}(1~50)와 같은 값이다. */
	public static final int LIMIT_DEFAULT = 20;
	public static final int LIMIT_MAX = 50;

	public static SimilarPackagesResponse of(String base, String modelVer,
		List<Candidate> candidates, List<String> notFound) {
		boolean empty = candidates.isEmpty();
		return new SimilarPackagesResponse(base, empty ? null : modelVer,
			empty ? NO_DATA : COMPLETE, candidates, notFound);
	}

	/**
	 * 후보 하나.
	 *
	 * <p><b>{@code package_id} 를 내보내지 않는다.</b> 재적재 시 재발번 여지가 있어 외부 식별자는
	 * {@code name} 이다(V1 설계 원칙). 화면이 이 이름으로 다시 조회하면 된다.
	 *
	 * @param rank           패키지 안에서 유일하다({@code UK_SIMILAR_PACKAGE_RANK}). 배열 순서와 같지만,
	 *                       걸러진 후보가 있으면 비어 있는 번호가 생길 수 있으므로 값도 함께 보낸다.
	 * @param score          유사도에 다른 신호를 더한 종합 점수. <b>비교용 상대값이지 확률이 아니다.</b>
	 *                       화면에서 "0.9 = 90% 대체 가능" 으로 읽히지 않게 표기해야 한다.
	 * @param latestVersion  최신 버전. <b>{@code ordinal} 로 고른다</b> — 문자열 정렬하면 {@code 4.9.0} 이
	 *                       {@code 4.19.2} 보다 뒤로 간다.
	 * @param description    최신 버전의 설명. 원본에 없으면 {@code null} 이며 빈 문자열과 구분된다.
	 */
	@JsonInclude(JsonInclude.Include.ALWAYS)
	public record Candidate(
		int rank,
		double score,
		String name,
		String latestVersion,
		String description
	) {
	}
}
