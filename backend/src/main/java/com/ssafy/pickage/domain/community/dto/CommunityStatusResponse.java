package com.ssafy.pickage.domain.community.dto;

/**
 * {@code POST .../refresh}·{@code GET .../community} 공통 응답 본문(구현계획 §API 응답 예시).
 * 기존 {@code ApiResponseBody}로 한 번 더 감싸 {@code {"success":true,"data":{...}}}가 된다.
 */
public record CommunityStatusResponse(
	String packageName,
	ViewStatus viewStatus,
	Freshness freshness,
	RefreshInfoResponse refresh,
	CommunityResultResponse result
) {
}
