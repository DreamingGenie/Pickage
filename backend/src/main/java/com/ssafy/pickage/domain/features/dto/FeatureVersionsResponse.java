package com.ssafy.pickage.domain.features.dto;

import java.util.List;

/**
 * {@code GET /api/packages/versions} 응답 — 기능 비교의 버전 드롭다운 (기능-10-R02).
 *
 * <p>필드 이름은 {@code SNAKE_CASE} 전략이 붙여 준다({@code application.yaml}).
 *
 * <p><b>{@code GET /api/packages/version}(단수)과 다른 API 다.</b> 그쪽은 major 별 사용 지분
 * (명세 §6)이고, 이쪽은 정확한 버전 문자열 목록이다. 지분은 {@code 4} 같은 major 로 뭉쳐
 * 있어 드롭다운에 쓸 수 없다.
 *
 * @param packages 요청한 순서 그대로. 패키지는 있는데 고를 버전이 없으면 {@code versions} 가
 *                 빈 배열이고 {@code latestStable} 이 null 이다 — 화면은 "비교할 수 있는 버전이
 *                 없다" 로 적는다
 * @param notFound {@code package} 에 이름 자체가 없는 것
 */
public record FeatureVersionsResponse(
	List<Item> packages,
	List<String> notFound
) {

	/**
	 * 패키지 하나의 선택지.
	 *
	 * @param packageName  요청한 이름
	 * @param latestStable 드롭다운의 기본값. {@code versions} 의 맨 앞과 같다. 없으면 null
	 * @param versions     최신순. <b>전부 소비 조건({@code package_env})이 있는 정식 버전</b>이라
	 *                     어느 것을 골라도 핵심 비교 요약이 채워진다
	 */
	public record Item(
		String packageName,
		String latestStable,
		List<String> versions
	) {
	}
}
