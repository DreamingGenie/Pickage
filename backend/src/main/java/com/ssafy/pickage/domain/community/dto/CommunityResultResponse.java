package com.ssafy.pickage.domain.community.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.ssafy.pickage.domain.community.DataStatus;

/**
 * {@code result} — 진행 중·최초 실패면 {@code null}이다(구현계획 §API "필드 규약"). 있으면
 * 항상 이 형태.
 */
public record CommunityResultResponse(
	UUID snapshotId,
	Instant collectedAt,
	Instant freshUntil,
	Instant serveUntil,
	DataStatus dataStatus,
	SummaryStatus summaryStatus,
	RepositoryInfoResponse repository,
	CommunitySummaryResponse summary,
	List<TopicResponse> topics,
	List<String> limitations,
	DataLimitsResponse dataLimits
) {
}
