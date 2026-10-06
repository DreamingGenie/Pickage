package com.ssafy.pickage.domain.packages;

import com.ssafy.pickage.domain.packages.dto.SimilarPackagesResponse;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 유사 패키지 조회 입력 (기능-03 · UC4).
 *
 * <p>{@link PackageNames} 를 쓰지 않는다. 그쪽은 <b>비교 화면의 규칙</b>(최대 3개)을 강제하는
 * 객체인데, 여기 입력은 기준 패키지 <b>하나</b>라서 상한이 의미가 없다. 억지로 재사용하면
 * "왜 유사 패키지에 3개 제한이 있지" 라는 질문이 영원히 남는다.
 *
 * <p>이름 규칙은 {@link PackageNames#isValidName} 을 그대로 쓴다 — 같은 이름 형식을 두 곳에서
 * 각자 정의하면 언젠가 한쪽만 고쳐진다.
 *
 * @param name  기준 패키지 이름
 * @param limit 실제로 적용할 후보 개수
 */
public record SimilarQuery(String name, int limit) {

	public static SimilarQuery of(String rawName, Integer rawLimit) {
		String name = rawName == null ? "" : rawName.trim();

		// 검증 순서는 명세의 에러 표를 따른다 — 누락(V001) → 상한(V002) → 형식(V004).
		if (name.isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING, "기준 패키지(name)는 필수입니다.");
		}
		if (rawLimit != null && rawLimit > SimilarPackagesResponse.LIMIT_MAX) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"limit은 최대 %d까지 가능합니다.".formatted(SimilarPackagesResponse.LIMIT_MAX));
		}
		// 0 이나 음수는 "0건을 달라" 가 아니라 잘못 만든 요청이다. 빈 목록을 조용히 돌려주면
		// 클라이언트 버그가 "추천이 안 뜬다" 로만 보인다.
		if (rawLimit != null && rawLimit < 1) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT, "limit은 1 이상이어야 합니다.");
		}
		if (!PackageNames.isValidName(name)) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT,
				"패키지 이름 형식이 올바르지 않습니다: " + name);
		}

		return new SimilarQuery(name, rawLimit != null ? rawLimit : SimilarPackagesResponse.LIMIT_DEFAULT);
	}
}
