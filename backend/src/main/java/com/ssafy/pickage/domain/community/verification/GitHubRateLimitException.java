package com.ssafy.pickage.domain.community.verification;

import java.time.Instant;

/**
 * GitHub core/search rate limit에 걸렸다(구현계획 §설정과 보안 — "core remaining/reset과
 * retry-after를 함께 확인하고 무한 재시도하지 않는다"). 접근 거부(비공개 저장소 등) 403과
 * 반드시 구분해야 한다 — {@link GitHubRepositoryClient}가 응답 헤더의
 * {@code X-RateLimit-Remaining}이 {@code 0}이거나 {@code Retry-After}가 있을 때만 이 예외를
 * 던진다.
 */
public class GitHubRateLimitException extends RuntimeException {

	private final Instant retryAt;

	public GitHubRateLimitException(String message, Instant retryAt) {
		super(message);
		this.retryAt = retryAt;
	}

	/** {@code null}이면 정확한 재시도 시각을 헤더에서 못 읽었다는 뜻 — 호출자가 기본 쿨다운을 쓴다. */
	public Instant retryAt() {
		return retryAt;
	}
}
