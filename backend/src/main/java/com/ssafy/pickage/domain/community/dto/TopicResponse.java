package com.ssafy.pickage.domain.community.dto;

import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;

import java.time.Instant;
import java.util.List;

/** 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다. */
public record TopicResponse(
        int issueNumber,
        String state,
        Instant updatedAt,
        Instant createdAt,
        String titleOriginal,
        String titleKo,
        long commentsCount,
        long reactionsCount,
        CommentCollectionStatus collectionStatus,
        SummaryStatus summaryStatus,
        String summaryKo,
        List<DiscussionStepResponse> flow,
        List<MessageResponse> messages,
        List<SummaryMarkResponse> summaryMarks) {}
