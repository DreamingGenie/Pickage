package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

/** C1 미연결: 존재하는 topic의 요약은 실패로 알리고 사실 자료만 게시한다. */
public final class FakeCommunitySummarizer implements CommunitySummarizer {
    public TopicSummary summarize(CollectedIssue issue) {
        return TopicSummary.failed();
    }
}
