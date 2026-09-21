package com.ssafy.pickage.domain.community.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.time.Instant;
import java.util.List;

/**
 * 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다.
 *
 * <p>논의 흐름 `flow` 는 더 만들지도 저장하지도 않는다(S15P21A506-412). 그 전에 저장된 스냅샷에는 `flow` 키가 남아 있어서
 * — 이 매퍼는 모르는 필드를 거부한다 — `flow` 만 골라 읽고 버린다. 다른 모르는 필드는 여전히 거부한다.
 */
@JsonIgnoreProperties("flow")
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
        List<MessagePayload> messages,
        List<SummaryMarkPayload> summaryMarks) {
    /**
     * `summary_marks` 는 payload_version 2 를 올리지 않고 나중에 더한 선택 필드다 — 이전에 저장된 스냅샷에는 없으므로
     * null 이 오면 빈 목록으로 읽는다.
     */
    public TopicPayload {
        summaryMarks = summaryMarks == null ? List.of() : List.copyOf(summaryMarks);
    }

    /** 강조 정보 없이 만드는 기존 생성자. */
    public TopicPayload(
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
            List<MessagePayload> messages) {
        this(
                sourceIssueId,
                issueNumber,
                state,
                updatedAt,
                createdAt,
                titleOriginal,
                titleKo,
                commentsCount,
                reactionsCount,
                collectionStatus,
                summaryStatus,
                summaryKo,
                messages,
                List.of());
    }
}
