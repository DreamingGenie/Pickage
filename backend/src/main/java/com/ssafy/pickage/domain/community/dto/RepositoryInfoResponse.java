package com.ssafy.pickage.domain.community.dto;

/**
 * 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다.
 *
 * <p>{@code issueCount}·{@code openIssueCount}: 저장소 전체 Issue 수(PR 제외)와 그중 열린 수(S15P21A506-413). 못 구했거나 이전
 * 스냅샷이면 {@code null} 이다.
 */
public record RepositoryInfoResponse(
        String owner,
        String name,
        String fullName,
        String scope,
        boolean archived,
        Integer issueCount,
        Integer openIssueCount) {}
