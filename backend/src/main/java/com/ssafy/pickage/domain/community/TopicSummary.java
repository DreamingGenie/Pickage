package com.ssafy.pickage.domain.community;

import java.util.List;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.DiscussionStepPayload;
import com.ssafy.pickage.domain.community.payload.MessagePayload;

/**
 * {@link CommunitySummarizer}의 산출물 — 이미 저장 payload 조각 형태({@code TopicPayload}에
 * 바로 끼워 넣을 수 있는 모양)다.
 *
 * <p>GMS의 실제 반환 형식(source_id 기반 대표 메시지 선정, 근거 검증 등,
 * {@code docs/for_community/GMS_연동_참고.md})을 여기서 그대로 흉내내지 않는다 — 그
 * 형식을 이 저장 형태로 바꾸는 책임을 {@link CommunitySummarizer} 구현체(진짜 GMS
 * 클라이언트가 나중에 만들어질 자리) 안으로 미뤘다. 이 Phase(317)는 GMS 실제 프로토콜을
 * 다루지 않으므로({@code docs/for_community/specs/S15P21A506-317.md} §1) 이 경계 안쪽을
 * 굳이 설계하지 않는다.
 */
public record TopicSummary(
	String titleKo,
	String summaryKo,
	List<DiscussionStepPayload> discussionFlow,
	List<MessagePayload> messages,
	SummaryStatus status
) {
}
