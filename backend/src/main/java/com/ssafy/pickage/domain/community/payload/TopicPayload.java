package com.ssafy.pickage.domain.community.payload;

import java.time.Instant;
import java.util.List;

/** 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다. */
public record TopicPayload(
        String sourceIssueId,
        int issueNumber,
        String state,
        Instant updatedAt,
        Instant createdAt,
        String titleOriginal,
        String titleKo,
        long commentsCount,
        long reactionsCount,
        String collectionStatus,
        String summaryStatus,
        String summaryKo,
        List<DiscussionStepPayload> flow,
        List<MessagePayload> messages) {}
