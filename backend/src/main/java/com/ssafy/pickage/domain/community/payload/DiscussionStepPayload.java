package com.ssafy.pickage.domain.community.payload;

/**
 * 이슈 하나의 논의 흐름 한 단계(구현계획 §설정과 보안 — GMS {@code discussion_flow}).
 *
 * <p>GMS가 반환하는 {@code support_source_ids}(근거 댓글 ID)는 서버가 검증(source ID가 실제
 * 입력 목록에 있는지)까지만 쓰고 통과 후에는 저장하지 않는다 — 공개 응답과 저장 payload
 * 어디에도 원문 식별자를 남기지 않는다(구현계획 §API "미노출").
 */
public record DiscussionStepPayload(
	int stepOrder,
	String textKo
) {
}
