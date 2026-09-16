package com.ssafy.pickage.domain.ops.dto;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

/**
 * 회차 하나의 현황.
 *
 * <p>필드는 camelCase 로 두고 {@code @JsonProperty} 를 붙이지 않는다 —
 * {@code application.yaml} 의 전역 snake_case 규칙이 내보낼 때 바꿔 준다.
 *
 * @param status        {@code PENDING}·{@code RUNNING}·{@code SUCCEEDED}·{@code FAILED}·
 *                      {@code BLOCKED}, 그리고 <b>{@code MISSING}</b> — 그 주에 상태 객체가
 *                      아예 없다는 뜻이다. 타이머가 한 번도 돌지 않았거나 멈춰 있었다
 * @param manualPending 수동 실행 요청이 아직 집혀 가지 않았다. 요청을 넣고 다음 발화를
 *                      기다리는 중인지 운영자가 이 값으로 안다
 */
public record WeeklyRunResponse(
	LocalDate weekOf,
	String status,
	Coverage coverage,
	OffsetDateTime startedAt,
	OffsetDateTime finishedAt,
	int consecutiveFailures,
	String lastError,
	OffsetDateTime manualRequestAt,
	OffsetDateTime manualClaimedAt,
	boolean manualPending,
	OffsetDateTime updatedAt,
	List<WeeklyStepResponse> steps
) {

	public record Coverage(
		LocalDate depsdevSnapshot,
		LocalDate downloadsThrough,
		LocalDate windowStart,
		LocalDate windowEnd
	) {
	}
}
