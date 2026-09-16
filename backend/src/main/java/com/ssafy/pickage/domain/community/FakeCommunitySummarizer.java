package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

import java.time.Duration;

/** GMS 설정값이 없거나 비어 있을 때 폴백: 존재하는 topic의 요약은 실패로 알리고 사실 자료만 게시한다. */
public final class FakeCommunitySummarizer implements CommunitySummarizer {
    public TopicSummary summarize(CollectedIssue issue, Duration budget) {
        return TopicSummary.failed();
    }
}
