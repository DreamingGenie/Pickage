package com.ssafy.pickage.domain.community.verification;

/**
 * GitHub 404(저장소 없음) 또는 rate-limit이 아닌 403(비공개 저장소 등) — 구현계획 §저장소와
 * Issue "GitHub 404 또는 접근 불가 403 | rate-limit과 구분해 UNVERIFIED_REPOSITORY". 두 상태를
 * 하나로 묶는다 — 어느 쪽이든 최종 판정은 같다(연결 실패, 다른 후보로 대체하지 않음).
 */
public class GitHubRepositoryNotFoundException extends RuntimeException {

	public GitHubRepositoryNotFoundException(String message) {
		super(message);
	}
}
