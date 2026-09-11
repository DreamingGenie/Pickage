package com.ssafy.pickage.domain.community;

import java.util.List;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;

/**
 * 실제 GMS 연동 전까지 쓰는 기본 구현 — 항상 {@link SummaryStatus#SKIPPED}를 돌려준다.
 * 화면은 이 경우 "GitHub 사실 값과 요약 실패·대상 없음 안내"로 표시한다(구현계획
 * §API "상황 → 화면" 표, "FRESH AVAILABLE·FAILED/SKIPPED").
 *
 * <p>이 클래스가 쓰이고 있다는 사실 자체가 "C1(GMS) 미연결"의 증거다 — Jira 317 완료
 * 판단 기준: "C1/C6 미연결 상태를 실연동 완료로 표시하지 않는다."
 */
public class FakeCommunitySummarizer implements CommunitySummarizer {

	@Override
	public TopicSummary summarize(CollectedIssue issue) {
		return new TopicSummary(null, null, List.of(), List.of(), SummaryStatus.SKIPPED);
	}
}
