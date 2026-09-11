package com.ssafy.pickage.domain.community.verification;

/**
 * 구현계획 §저장소와 Issue "패키지 연결과 Issue 귀속 범위" 표 + Jira 213 "DB-only root name
 * 필수" 규칙을 옮긴 순수 함수. {@link PackageJsonNameCheck}(이미 GitHub에서 받아온 결과)만
 * 입력으로 받고 HTTP 호출은 하지 않는다.
 */
final class RepositoryScopePolicy {

	private RepositoryScopePolicy() {
	}

	/**
	 * @param candidate     {@link RepositoryCandidatePolicy}가 고른 후보
	 * @param rootNameCheck 후보에 directory가 없을 때만 의미가 있다(directory가 있으면
	 *                      호출자가 이 값을 조회하지 않았을 수 있다 — {@code NOT_FOUND}로 넘겨도
	 *                      무방, 이 메서드는 그 경우 이 값을 보지 않는다)
	 * @param directoryNameCheck candidate에 directory가 있을 때만 의미가 있다
	 */
	static RepositoryVerificationResult classify(
		ResolvedCandidate candidate,
		PackageJsonNameCheck rootNameCheck,
		PackageJsonNameCheck directoryNameCheck,
		boolean archived) {

		if (!candidate.npmCorroborated()) {
			// "DB만 GitHub" — npm 교차검증이 전혀 없으므로 루트 이름이 맞을 때만 진행한다.
			// table 2의 관대한 "이름 불일치해도 REPOSITORY_WIDE" 대체를 쓰지 않는다(Jira 213
			// "DB-only root name 필수 규칙").
			if (rootNameCheck == PackageJsonNameCheck.MATCH) {
				return new RepositoryVerificationResult.Verified(
					candidate.owner(), candidate.repo(), RepositoryScope.PACKAGE_SCOPED, false, archived);
			}
			return new RepositoryVerificationResult.UnverifiedRepository(
				"DB 후보의 저장소 루트 package.json 이름이 요청 패키지 이름과 다르거나 확인할 수 없음");
		}

		if (candidate.directory() != null) {
			// npm이 monorepo 내 directory를 지정한 경우.
			return switch (directoryNameCheck) {
				case MATCH -> new RepositoryVerificationResult.Verified(
					candidate.owner(), candidate.repo(), RepositoryScope.REPOSITORY_WIDE, true, archived);
				case MISMATCH, NOT_FOUND -> new RepositoryVerificationResult.AmbiguousScope(
					candidate.owner(), candidate.repo());
			};
		}

		// directory 없음 — 루트 이름이 맞으면 PACKAGE_SCOPED, 아니면 저장소 연결만 확인된
		// REPOSITORY_WIDE(한계 표시)로 그래도 진행한다. npm이 이미 이 owner/repo를 직접
		// 가리켰으므로(교차검증 있음) DB-only처럼 완전히 포기하지 않는다.
		return switch (rootNameCheck) {
			case MATCH -> new RepositoryVerificationResult.Verified(
				candidate.owner(), candidate.repo(), RepositoryScope.PACKAGE_SCOPED, false, archived);
			case MISMATCH, NOT_FOUND -> new RepositoryVerificationResult.Verified(
				candidate.owner(), candidate.repo(), RepositoryScope.REPOSITORY_WIDE, true, archived);
		};
	}
}
