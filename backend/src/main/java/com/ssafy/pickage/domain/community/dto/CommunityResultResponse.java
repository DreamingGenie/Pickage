package com.ssafy.pickage.domain.community.dto;

import com.ssafy.pickage.domain.community.DataStatus;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다. */
public record CommunityResultResponse(
        UUID snapshotId,
        Instant collectedAt,
        Instant freshUntil,
        Instant serveUntil,
        DataStatus dataStatus,
        SummaryStatus summaryStatus,
        Instant summaryRetryAt,
        RepositoryInfoResponse repository,
        CommunitySummaryResponse summary,
        List<TopicResponse> topics,
        List<LimitationResponse> limitations,
        DataLimitsResponse dataLimits) {}
