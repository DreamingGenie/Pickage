package com.ssafy.pickage.domain.ops.dto;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * 회차 안의 단계 하나.
 *
 * @param status {@code PENDING}·{@code RUNNING}·{@code SUCCEEDED}·{@code FAILED}·
 *               <b>{@code SKIPPED}</b>. 마지막 것은 실패가 아니라 "아직" 이다 —
 *               deps.dev 가 그 주 스냅샷을 아직 올리지 않은 경우이고,
 *               {@code detail.reason} 이 {@code source_not_ready} 다
 * @param errorMessage 실패한 단계의 로그 꼬리 4 KB. 전문은 수집 노드의 단계 로그에 있다
 */
public record WeeklyStepResponse(
	String step,
	String status,
	int attemptCount,
	OffsetDateTime startedAt,
	OffsetDateTime finishedAt,
	String errorMessage,
	Map<String, Object> detail
) {
}
