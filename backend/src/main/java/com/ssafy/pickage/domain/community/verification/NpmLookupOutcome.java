package com.ssafy.pickage.domain.community.verification;

/** {@link NpmRepositoryLookup#fetchRepositoryField} 결과. 네트워크/rate-limit 오류는 예외로 던진다(성공/실패 값이 아니다). */
sealed interface NpmLookupOutcome {

	record Found(String rawRepositoryUrl, String directory) implements NpmLookupOutcome {
	}

	/** {@code repository} 필드 자체가 없다 — npm에 이 필드가 필수가 아니다. */
	record NoRepositoryField() implements NpmLookupOutcome {
	}

	/** 패키지 자체가 npm에 없다(404) — 구현계획 §저장소와 Issue "npm 조회 404". */
	record NotFound() implements NpmLookupOutcome {
	}
}
