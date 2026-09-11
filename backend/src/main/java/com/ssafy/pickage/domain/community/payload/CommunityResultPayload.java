package com.ssafy.pickage.domain.community.payload;

import java.time.Instant;
import java.util.List;

/**
 * {@code community_snapshot.result} JSONB 의 타입이 정해진 형태.
 *
 * <p>이 record는 <b>저장 payload</b>다 — Phase 4({@code S15P21A506-317})가 만들 <b>공개 API
 * 응답 DTO</b>와는 다른 타입이다(구현계획 §백엔드 "Entity·외부 DTO·저장 payload·API DTO를
 * 공유하지 않는다"). 공개 응답은 이 payload에서 {@code source_issue_id}·{@code sourceCommentId}
 * 같은 내부 식별자를 제거하고, {@code fresh_until}·{@code summary}(합계)·표시 역할처럼 저장하지
 * 않는 값을 계산해 덧붙여 만든다 — 그 변환은 이 Phase의 범위가 아니다.
 *
 * @param repository      검증된 최종 저장소와 귀속 범위
 * @param policyVersion   이슈 선정에 쓰인 정책 버전(예: {@code github-active-v1}=1). 정책이
 *                        바뀌면 이 값으로 재수집 여부를 판단한다(재시작 후 복원 대상,
 *                        Jira 314 세부 항목)
 * @param lookbackDays    실제 적용된 조회 기간(180 또는 365 — 365일로 한 번 확장했는지 복원)
 * @param summaryRetryAt  전체 요약이 FAILED일 때 재시도를 허용하는 시각(5분 쿨다운). 요약이
 *                        FAILED가 아니면 {@code null}
 * @param topics          선택된 이슈 (최대 2건)
 * @param limitations     검색 불완전·댓글 100개 초과·입력 절단·저장소 전체 범위·archived 같은
 *                        제한 코드
 */
public record CommunityResultPayload(
	RepositoryPayload repository,
	int policyVersion,
	int lookbackDays,
	Instant summaryRetryAt,
	List<TopicPayload> topics,
	List<String> limitations
) {
}
