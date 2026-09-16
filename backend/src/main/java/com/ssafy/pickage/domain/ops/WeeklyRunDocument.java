package com.ssafy.pickage.domain.ops;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * {@code run.json} 의 모양. <b>수집기가 소유하는 계약이다</b> —
 * {@code pipeline/weekly/state.py} 가 쓰고 여기서는 읽기만 한다.
 *
 * <p>필드 이름은 snake_case 인데 {@code @JsonProperty} 를 붙이지 않는다.
 * {@link WeeklyStateStore} 의 전용 매퍼가 전략으로 처리한다 — 한 필드를 빠뜨려도
 * 컴파일이 통과하는 방식을 피하려는 것으로, {@code application.yaml} 이 응답 쪽에
 * 같은 이유로 전역 규칙을 쓰는 것과 같다.
 *
 * <p>모르는 필드는 무시한다. 수집기가 나중에 값을 더해도 이쪽 배포가 밀렸다고 500 이
 * 나면 안 된다 — 이건 인계 채널이 아니라 사람이 보는 창이다.
 *
 * @param coverage 이 회차가 <b>어느 날짜 데이터까지</b> 담는지. 운영자가 가장 먼저 보는 값이다
 */
public record WeeklyRunDocument(
	LocalDate weekOf,
	String status,
	Coverage coverage,
	OffsetDateTime startedAt,
	OffsetDateTime finishedAt,
	int consecutiveFailures,
	String lastError,
	OffsetDateTime manualClaimedAt,
	OffsetDateTime updatedAt,
	List<Step> steps
) {

	public List<Step> steps() {
		return steps == null ? List.of() : steps;
	}

	/**
	 * @param depsdevSnapshot  deps.dev 스냅샷 날짜(= 회차 날짜)
	 * @param downloadsThrough npm 다운로드를 이 날짜까지 받았다
	 * @param downloadsWindow  14일 창 [시작, 끝]
	 */
	public record Coverage(
		LocalDate depsdevSnapshot,
		LocalDate downloadsThrough,
		List<LocalDate> downloadsWindow
	) {
	}

	/**
	 * @param attemptCount 이 단계를 시작한 횟수. 이어받기로 여러 번 도는 것이 정상이다
	 * @param detail       단계별 요약 수치. 자격증명이나 원문은 들어 있지 않다
	 */
	public record Step(
		String step,
		String status,
		int attemptCount,
		OffsetDateTime startedAt,
		OffsetDateTime finishedAt,
		String errorMessage,
		Map<String, Object> detail
	) {
	}
}
