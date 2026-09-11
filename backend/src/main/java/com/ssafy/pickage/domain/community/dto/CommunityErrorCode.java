package com.ssafy.pickage.domain.community.dto;

/**
 * 구현계획 §상태와 오류 — "공개 실패 코드는 이 여덟 가지로 제한한다." 내부 예외명·URL·키는
 * 응답에 넣지 않는다.
 */
public enum CommunityErrorCode {
	GITHUB_RATE_LIMITED,
	GITHUB_UNAVAILABLE,
	NPM_UNAVAILABLE,
	GMS_UNAVAILABLE,
	REFRESH_DEADLINE_EXCEEDED,
	PUBLISH_FAILED,
	CAPACITY_LIMITED,
	LOCAL_RATE_LIMITED
}
