package com.ssafy.pickage.domain.community.payload;

/**
 * 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다.
 *
 * <p>{@code issueCount}·{@code openIssueCount} 는 저장소 **전체** Issue 수(PR 제외)와 그중 열린 수다(S15P21A506-413). 요약한 Issue
 * 몇 건이 아니라 저장소 규모를 보여주는 값이라 수집 범위와 무관하다. {@code payload_version} 을 올리지 않고 더한 선택 필드다 — 이전에
 * 저장된 스냅샷에는 없고, 조회에 실패했을 때도 {@code null} 이다. 둘 다 {@code null} 이어도 결과는 정상이다.
 */
public record RepositoryPayload(
        String owner,
        String name,
        String fullName,
        String scope,
        boolean archived,
        Integer issueCount,
        Integer openIssueCount) {

    /** 저장소 Issue 수 없이 만드는 기존 생성자. */
    public RepositoryPayload(
            String owner, String name, String fullName, String scope, boolean archived) {
        this(owner, name, fullName, scope, archived, null, null);
    }

    public RepositoryPayload withIssueCounts(Integer issueCount, Integer openIssueCount) {
        return new RepositoryPayload(
                owner, name, fullName, scope, archived, issueCount, openIssueCount);
    }
}
