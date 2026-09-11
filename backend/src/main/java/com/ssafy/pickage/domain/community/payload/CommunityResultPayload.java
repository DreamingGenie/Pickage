package com.ssafy.pickage.domain.community.payload;

import java.time.Instant;
import java.util.List;

/** 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다. */
public record CommunityResultPayload(
        RepositoryPayload repository,
        String policyVersion,
        int lookbackDays,
        Instant summaryRetryAt,
        List<TopicPayload> topics,
        List<LimitationPayload> limitations) {
    public CommunityResultPayload {
        java.util.Objects.requireNonNull(policyVersion, "policyVersion");
        topics = List.copyOf(topics);
        limitations = List.copyOf(limitations);
    }
}
