package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

import java.time.Duration;
import java.util.List;
import java.util.Set;

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

	/**
	 * Map-Reduce(S15P21A506-373 4단계)의 Reduce 단계 — 배치별로 <b>이미 검증된</b> 부분 결과를
	 * 하나의 {@link TopicSummary}로 합성한다. 원문 댓글이 아니라 {@link
	 * CommunitySummaryValidator}를 통과한 부분 결과만 넘긴다. 구현체는 {@code parts}에 담긴
	 * source id 밖의 값을 인용하지 않도록 스스로도 제한해야 한다(1차 방어) — 최종 검증(2차
	 * 방어)은 호출자({@link CommunityMapReduceSummarizer})가 배치들의 source id 합집합에
	 * 대해 다시 한다. 기본 구현은 {@link FakeCommunitySummarizer}와 같은 이유로 항상 실패를
	 * 반환한다 — 이 메서드를 정의하지 않는 기존 람다 기반 테스트 대역({@code
	 * CommunitySummarizer}를 함수형 인터페이스로 쓰는 곳)과의 호환을 위해 default로 둔다.
	 */
	default TopicSummary reduce(List<BatchSummary> parts, Duration budget) {
		return TopicSummary.failed();
	}

	/** 배치 하나의 검증된 부분 결과 + 그 배치에서 인용 가능했던 source id 전체. */
	record BatchSummary(TopicSummary summary, Set<TopicSummary.SourceRef> availableSources) {}
}
