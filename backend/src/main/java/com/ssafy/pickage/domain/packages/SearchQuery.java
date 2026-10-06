package com.ssafy.pickage.domain.packages;

import com.ssafy.pickage.domain.packages.dto.PackageSearchResponse;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 검색 입력 (API 명세 §2.4).
 *
 * <p>검색만 {@code names} 배열 규칙의 예외다 — 입력이 이름이 아니라 <b>접두사 문자열</b>이라서다.
 * 그래도 검증 규칙을 값 객체로 빼 두는 이유는 {@link PackageNames} 와 같다: 컨트롤러에
 * 흩어 놓으면 나중에 문구나 상한이 갈라진다.
 *
 * @param q     이스케이프 전의 원본 접두사. {@code LIKE} 와일드카드 처리는 저장소가 한다 —
 *              SQL 문법에 속한 일이라 그쪽에 두는 편이 맞다.
 * @param limit 실제로 적용할 개수
 */
public record SearchQuery(String q, int limit) {

	public static SearchQuery of(String rawQ, Integer rawLimit) {
		String q = rawQ == null ? "" : rawQ.trim();

		// 검증 순서는 명세의 에러 표를 따른다 — 누락(V001) → 상한(V002) → 형식(V004).
		if (q.isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING, "검색어(q)는 필수입니다.");
		}
		if (rawLimit != null && rawLimit > PackageSearchResponse.LIMIT_MAX) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"limit은 최대 %d까지 가능합니다.".formatted(PackageSearchResponse.LIMIT_MAX));
		}
		// 0 이나 음수는 "0건을 달라" 가 아니라 잘못 만든 요청이다. 빈 목록을 조용히 돌려주면
		// 클라이언트 버그가 "검색이 안 된다" 로만 보인다.
		if (rawLimit != null && rawLimit < 1) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT, "limit은 1 이상이어야 합니다.");
		}
		if (q.length() < 1) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT, "검색어는 1자 이상이어야 합니다.");
		}

		return new SearchQuery(q, rawLimit != null ? rawLimit : PackageSearchResponse.LIMIT_DEFAULT);
	}
}
