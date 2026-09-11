package com.ssafy.pickage.domain.community.refresh;

/**
 * {@code POST /api/packages/community/refresh}의 {@code trigger} 쿼리 파라미터(구현계획 §API).
 */
public enum RefreshTrigger {
	/** 비교 대상 확정 직후 여유가 있을 때만 사전 수집. 토큰·permit 부족 시 무대기 즉시 거절. */
	ANALYSIS_CONFIRMED,
	/** 탭을 연 사용자. permit이 없으면 대기 큐에 들어간다. */
	TAB_OPENED
}
