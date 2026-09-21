package com.ssafy.pickage.domain.community.dto;

import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;

import java.time.Instant;
import java.util.List;

/**
 * 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다.
 *
 * <p>`flow`(논의 흐름)는 내려주지 않는다(S15P21A506-412). 화면이 S15P21A506-406 부터 그리지 않는다.
 */
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
        List<MessageResponse> messages,
        List<SummaryMarkResponse> summaryMarks) {}
