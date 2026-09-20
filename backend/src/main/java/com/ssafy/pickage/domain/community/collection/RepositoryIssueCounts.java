package com.ssafy.pickage.domain.community.collection;

/**
 * 저장소 전체 Issue 수(PR 제외)와 그중 열려 있는 수(S15P21A506-413).
 *
 * <p>요약 수치 카드용 보조 정보다 — 값 하나하나가 {@code null} 일 수 있다(조회 실패·rate limit·불완전 결과). {@code null} 이면
 * 화면은 빈 값으로 보여 주고, 커뮤니티 결과 자체는 그대로 게시한다.
 */
public record RepositoryIssueCounts(Integer total, Integer open) {
    public static final RepositoryIssueCounts UNKNOWN = new RepositoryIssueCounts(null, null);
}
