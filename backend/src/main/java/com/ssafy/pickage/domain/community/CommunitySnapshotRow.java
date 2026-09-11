package com.ssafy.pickage.domain.community;

import java.time.Instant;
import java.util.UUID;

import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;

/**
 * {@code community_snapshot} 한 행. {@code fresh_until}·{@code serve_until}·요약 합계처럼
 * 계산으로 만드는 값은 여기 없다 — {@link CommunitySnapshotTtl}과 이후 Phase(317)가
 * {@link #collectedAt()}으로 계산한다.
 */
public record CommunitySnapshotRow(
	int packageId,
	UUID snapshotId,
	short payloadVersion,
	Instant collectedAt,
	DataStatus dataStatus,
	CommunityResultPayload result
) {
}
