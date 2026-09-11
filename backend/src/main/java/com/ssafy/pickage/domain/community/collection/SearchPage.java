package com.ssafy.pickage.domain.community.collection;

import java.util.List;

/**
 * GitHub Search API 응답 그대로. {@code totalCount}(= "raw" 건수)는
 * {@link IssueSelectionPolicy} 필터 <b>이전</b> 값이라 "raw 0일 때만 365일로 확장"
 * 판단에 필요하다.
 *
 * <p>{@code public}이다 — {@link GitHubIssueSearchClient#searchActiveIssues}가 이미
 * public이라 반환 타입도 맞춰야 한다(리뷰에서 발견한 가시성 불일치 수정).
 */
public record SearchPage(int totalCount, boolean incompleteResults, List<SearchResultItem> items) {
}
