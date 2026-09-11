package com.ssafy.pickage.domain.community.dto;

/**
 * {@code result.summary} — topics의 값을 서버가 합산한다(구현계획 "통계는 topics에서
 * 서버가 계산하며 JSON에 중복 저장하지 않음"). 저장 payload에는 이 값이 없다.
 */
public record CommunitySummaryResponse(
	int analyzedIssueCount,
	int commentCount,
	int reactionCount,
	int openIssueCount
) {
}
