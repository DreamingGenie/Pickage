package com.ssafy.pickage.domain.community.payload;

import java.time.Instant;

/**
 * 화면에 표시할 대표 메시지 한 개(이슈당 최대 3개, 구현계획 §저장소와 Issue "대표 메시지").
 *
 * <p>{@code sourceIssueId}·{@code sourceCommentId}·{@code association}·{@code isIssueAuthor}는
 * Jira S15P21A506-314 세부 항목이 명시한 대로 <b>재시작 후 복원</b>을 위해 저장한다 — 표시
 * 역할({@code author_role})은 조회 시점에 {@code association}·{@code isIssueAuthor}로 매번
 * 다시 계산하고 JSON에는 계산된 역할을 저장하지 않는다(구현계획 §"컬럼으로 만들지 않는 값").
 *
 * <p>원문(댓글·이슈 본문 텍스트)은 어디에도 없다 — {@code summaryKo}만 저장한다.
 *
 * @param sourceIssueId   이 메시지가 속한 이슈 번호(문자열 보존 — 큰 GitHub ID를 숫자로 다루면
 *                        정밀도가 깨질 수 있다)
 * @param sourceCommentId 댓글 ID. 이슈 본문 자체가 메시지면 {@code null}
 * @param authorLogin     GitHub 로그인
 * @param association     GitHub 원천 {@code author_association} 원문값(OWNER/MEMBER/COLLABORATOR/
 *                         CONTRIBUTOR/그 외). 표시용으로 이미 바뀐 값이 아니라 원천 그대로
 * @param isIssueAuthor   댓글 작성자가 이슈 작성자와 같은지 — 같으면 표시 역할은 association과
 *                        무관하게 항상 {@code ISSUE_AUTHOR}
 * @param messageKind     {@code NORMAL} / {@code USER_SOLUTION} 등 메시지 종류(작성자 역할이 아님)
 * @param sourceCreatedAt 원 작성 시각 (messages 정렬 기준)
 * @param summaryKo       대표 메시지 핵심 논지 한국어 요약
 */
public record MessagePayload(
	String sourceIssueId,
	String sourceCommentId,
	String authorLogin,
	String association,
	boolean isIssueAuthor,
	String messageKind,
	Instant sourceCreatedAt,
	String summaryKo
) {
}
