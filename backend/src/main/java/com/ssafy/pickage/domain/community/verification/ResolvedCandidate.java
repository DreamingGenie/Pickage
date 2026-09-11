package com.ssafy.pickage.domain.community.verification;

/**
 * {@link RepositoryCandidatePolicy}가 DB·npm 두 후보를 대조해 고른 최종 저장소.
 *
 * @param npmCorroborated npm이 이 owner/repo를 직접 가리켰는지(단독이든 DB와 일치해서든).
 *                        {@code false}면 DB만의 후보라는 뜻이고, 이 경우
 *                        {@link RepositoryScopePolicy}는 구현계획 §저장소와 Issue의 "DB만
 *                        GitHub" 규칙(루트 이름 불일치 시 전체 실패, table 2의 관대한
 *                        REPOSITORY_WIDE 대체를 쓰지 않음)을 적용한다 — DB 후보는 npm
 *                        교차검증이 전혀 없는 가장 약한 신호이기 때문이다.
 * @param conflictWithDb DB와 npm이 서로 다른 저장소를 가리켜 npm 후보로 진행하기로 한 경우
 *                        {@code true}. 호출자(서비스)가 이 값을 구조화 로그에 남긴다 — 이
 *                        record 자체는 순수 값이라 로깅하지 않는다.
 */
record ResolvedCandidate(String owner, String repo, String directory, boolean npmCorroborated,
	boolean conflictWithDb) {
}
