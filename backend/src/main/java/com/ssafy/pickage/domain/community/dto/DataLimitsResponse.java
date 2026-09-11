package com.ssafy.pickage.domain.community.dto;

/** {@code result.data_limits} — 이번 결과에 적용된 상한을 그대로 보여준다(변경 이력 추적용). */
public record DataLimitsResponse(int maxIssueCount, int maxCommentsPerIssue) {
}
