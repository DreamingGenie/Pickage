package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

/**
 * GMS 요약 경계. 이 인터페이스 뒤에 실제 GMS Responses API 클라이언트가 나중에 들어온다 —
 * 이 Phase는 {@link FakeCommunitySummarizer}만 제공한다(Jira 317 "C1 GMS 실제 프로토콜...
 * 이번 이슈가 새로 수행/배정하지 않는다").
 *
 * <p>이슈 하나씩 독립 호출한다 — 구현계획 "이슈 최대 2건은 동시성 2로 독립 호출해 한쪽
 * 실패가 다른 쪽을 막지 않게 한다."
 */
public interface CommunitySummarizer {

	TopicSummary summarize(CollectedIssue issue);
}
