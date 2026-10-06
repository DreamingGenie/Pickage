package com.ssafy.pickage.domain.packages.dto;

import java.util.List;

/**
 * {@code GET /api/packages/search} 응답 (명세 §2.4).
 *
 * <p><b>이름만 반환한다.</b> 다운로드 순 정렬이라 배열 순서가 곧 인기순이고, 사전 파일과
 * 형태가 같아 클라이언트가 두 결과를 그대로 합칠 수 있다. 설명이나 다운로드 수를 함께
 * 보내면 사전 결과와 모양이 달라져, 화면이 출처별로 다른 항목을 그리게 된다.
 *
 * @param query 서버가 실제로 사용한 검색어. 응답이 늦게 도착했을 때 클라이언트가
 *              현재 입력과 대조해 버릴지 판단하는 데 쓴다.
 */
public record PackageSearchResponse(String query, List<String> items) {

	/** §2.4 — {@code limit} 기본값·상한. */
	public static final int LIMIT_DEFAULT = 20;
	public static final int LIMIT_MAX = 50;
}
