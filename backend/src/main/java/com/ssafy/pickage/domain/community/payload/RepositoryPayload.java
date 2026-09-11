package com.ssafy.pickage.domain.community.payload;

/**
 * 검증된 최종 저장소 식별자와 패키지 귀속 범위(구현계획 §저장소와 Issue).
 *
 * <p>후보 주소·검증 과정(DB/npm 어느 쪽이 후보였는지, 충돌 여부)은 여기 저장하지 않는다 —
 * 그건 수집 중 메모리와 구조화 로그에서만 쓰고 버리는 값이다. 여기 남는 것은 <b>검증이 끝난
 * 최종 결과</b>뿐이다.
 *
 * @param identifier {@code owner/repo}
 * @param scope      {@code PACKAGE_SCOPED} / {@code REPOSITORY_WIDE} / {@code AMBIGUOUS_SCOPE}
 */
public record RepositoryPayload(
	String identifier,
	String scope
) {
}
