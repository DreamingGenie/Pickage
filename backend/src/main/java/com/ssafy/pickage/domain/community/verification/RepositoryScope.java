package com.ssafy.pickage.domain.community.verification;

/**
 * 검증된 저장소와 요청 패키지의 귀속 범위(구현계획 §저장소와 Issue "패키지 연결과 Issue 귀속
 * 범위" 표).
 *
 * <p>{@code AMBIGUOUS_SCOPE}는 여기 없다 — 그건 "범위를 알 수 없다"는 뜻이라 성공적으로
 * 분류된 스코프가 아니라 {@link RepositoryVerificationResult.AmbiguousScope}(이슈 조회
 * 중단)로 표현한다.
 */
public enum RepositoryScope {

	/**
	 * 저장소 전체가 곧 이 패키지다(directory 없이 루트 package.json 이름이 일치). Issue를
	 * 필터링 없이 그대로 이 패키지의 논의로 다룬다.
	 */
	PACKAGE_SCOPED,

	/**
	 * 저장소 연결은 확인됐지만 이슈 전체가 이 패키지 전용이라는 증거는 아니다(monorepo의
	 * 한 directory만 확인됐거나, 루트 이름이 일치하지 않아 저장소 수준의 연결만 확인한
	 * 경우). v1은 label·경로·본문으로 Issue를 패키지별로 다시 거르지 않는다 — 구현계획이
	 * 명시적으로 금지한다.
	 */
	REPOSITORY_WIDE
}
