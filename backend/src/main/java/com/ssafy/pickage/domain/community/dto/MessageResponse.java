package com.ssafy.pickage.domain.community.dto;

import java.time.Instant;

/**
 * {@code result.topics[].messages[]}. 저장 payload({@code MessagePayload})의
 * {@code sourceIssueId}·{@code sourceCommentId}는 여기 없다 — 구현계획 §API "미노출"이
 * 내부 식별자를 공개 응답에서 제거하라고 명시한다. {@code authorRole}은
 * {@code association}·{@code isIssueAuthor}에서 조회 시점에 계산한 값이다(저장하지 않음).
 */
public record MessageResponse(
	String authorLogin,
	String authorRole,
	String messageKind,
	Instant sourceCreatedAt,
	String summaryKo
) {
}
