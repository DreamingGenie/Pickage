package com.ssafy.pickage.domain.community.payload;

import java.time.Instant;
import java.util.List;

/**
 * 선택된 이슈 하나(최대 2건 중 하나, 구현계획 §API 응답 예시의 {@code topics} 원소).
 *
 * <p>{@code commentCount}·{@code reactionCount}·{@code openIssueCount} 같은 상단 합계는 서버가
 * 조회 시점에 이 topics 목록을 합산해 계산한다(구현계획 §"컬럼으로 만들지 않는 값") — 그래서
 * 이 record에는 <b>이슈 하나의</b> 댓글 수·반응 수만 있고 합계 필드는 없다.
 *
 * @param issueNumber      저장소 안의 이슈 번호(응답 식별자는 이것만 쓴다, DB PK가 아니다)
 * @param issueState       OPEN / CLOSED
 * @param issueUpdatedAt   이슈 갱신 시각
 * @param title            원문 제목
 * @param titleKo          한국어 제목(GMS 생성, 검증 통과분만)
 * @param commentCount     이 이슈의 전체 댓글 수(수집한 최신 100개가 아니라 GitHub 원천 총계)
 * @param reactionCount    이 이슈의 반응 수
 * @param collectionStatus COMPLETE / PARTIAL / TRUNCATED / FAILED 등 댓글 수집 결과
 * @param summaryStatus    READY / PARTIAL / FAILED / SKIPPED
 * @param summaryKo        이슈 상황 요약(한국어)
 * @param discussionFlow   논의 흐름 단계 (1~4개)
 * @param messages         대표 메시지 (0~3개)
 */
public record TopicPayload(
	int issueNumber,
	String issueState,
	Instant issueUpdatedAt,
	String title,
	String titleKo,
	int commentCount,
	int reactionCount,
	String collectionStatus,
	String summaryStatus,
	String summaryKo,
	List<DiscussionStepPayload> discussionFlow,
	List<MessagePayload> messages
) {
}
