package com.ssafy.pickage.domain.community.dto;

import java.time.Instant;
import java.util.UUID;

import com.ssafy.pickage.domain.community.refresh.RefreshStatus;

/**
 * 구현계획 §API 응답 예시의 {@code refresh} 객체. {@code stage}는 내부
 * {@link com.ssafy.pickage.domain.community.refresh.RefreshStage}의 wire 이름
 * (예: {@code "COLLECTING_DISCUSSIONS"})이다.
 */
public record RefreshInfoResponse(
	UUID refreshId,
	RefreshStatus status,
	String stage,
	String stageMessage,
	Instant startedAt,
	Instant lastUpdatedAt,
	Integer pollAfterSeconds,
	Instant retryAt,
	CommunityErrorCode errorCode
) {
}
