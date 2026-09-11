package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.*;

import java.util.List;

/** C1 adapter의 구조화된 산출물. support는 검증 후 폐기하고 snapshot에 저장하지 않는다. */
public record TopicSummary(
        String titleKo,
        String summaryKo,
        List<DiscussionStepPayload> discussionFlow,
        List<MessagePayload> messages,
        SummaryStatus status,
        List<SourceRef> summarySupport,
        List<List<SourceRef>> flowSupport) {
    public record SourceRef(String type, String id) {}

    public static TopicSummary failed() {
        return new TopicSummary(
                null, null, List.of(), List.of(), SummaryStatus.FAILED, List.of(), List.of());
    }
}
