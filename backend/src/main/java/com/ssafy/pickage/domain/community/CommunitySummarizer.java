package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

import java.time.Duration;

/**
 * GMS 요약 경계. {@link GmsCommunitySummarizer}(S15P21A506-365)가 실제 구현체다.
 *
 * <p>이슈 하나씩 <b>독립적으로</b> 호출한다 — 한쪽이 던지는 예외가 다른 쪽 결과에 영향을
 * 주지 않는다({@link CommunityRefreshOrchestrator}가 각 호출을 개별적으로 try/catch한다,
 * 구현계획 "한쪽 실패가 다른 쪽을 막지 않게 한다"). {@link CommunityRefreshOrchestrator}는
 * 이슈들을 병렬로 호출한다(S15P21A506-368 후속 — 실제 GMS 호출이 몇 초씩 걸리기 시작하면서
 * 순차 호출이 {@code RefreshTask}의 전체 예산을 불필요하게 앞당겨 소진시키는 문제가 실제로
 * 재현됐다). {@code budget}은 이 호출 하나에 남은 시간이다 — 구현체는 이 시간 안에서
 * 스스로 타임아웃해야 하며, 넘기면 {@link BoundedCommunitySummarizer}가 별도로 강제
 * 인터럽트한다(이중 안전장치).
 */
public interface CommunitySummarizer {

	TopicSummary summarize(CollectedIssue issue, Duration budget);
}
