package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

/**
 * GMS 요약 경계. 이 인터페이스 뒤에 실제 GMS Responses API 클라이언트가 나중에 들어온다 —
 * 이 Phase는 {@link FakeCommunitySummarizer}만 제공한다(Jira 317 "C1 GMS 실제 프로토콜...
 * 이번 이슈가 새로 수행/배정하지 않는다").
 *
 * <p>이슈 하나씩 <b>독립적으로</b> 호출한다 — 한쪽이 던지는 예외가 다른 쪽 결과에 영향을
 * 주지 않는다({@link CommunityRefreshOrchestrator}가 각 호출을 개별적으로 try/catch한다,
 * 구현계획 "한쪽 실패가 다른 쪽을 막지 않게 한다"). 다만 <b>동시성(병렬 호출)까지는 아직
 * 아니다</b> — {@code CommunityRefreshOrchestrator.summarizeAndPublish}는 지금 순차
 * for 루프로 부른다. {@link FakeCommunitySummarizer}가 즉시 반환하는 지금은 차이가
 * 없지만, 실제 GMS 클라이언트가 이 자리에 들어오고 각 호출이 유의미한 시간을 쓰게 되면
 * 순차 호출이 {@code RefreshTask}의 20초 예산을 불필요하게 앞당겨 소진시킬 수 있다
 * (/code-review에서 발견 — 실제 병렬화는 이 Phase 범위 밖의 후속 작업으로 남긴다).
 */
public interface CommunitySummarizer {

	TopicSummary summarize(CollectedIssue issue);
}
