package com.ssafy.pickage.domain.community;

import java.time.Duration;

/**
 * 구현계획 §설정과 보안의 숫자값 전부를 한 곳에 모은다. 2026-09-11 사용자 결정 —
 * {@code application.yaml}(공용 파일)을 건드리지 않고 상수 클래스로 시작한다. 운영에서
 * 실제로 조정이 필요해지면(문서: "20초가 충분한지는 운영 p95를 보고 조정") 그때
 * {@code @ConfigurationProperties}로 승격한다.
 */
public final class CommunityProperties {

	private CommunityProperties() {
	}

	/** 동시 실행 permit — 세마포어 크기. */
	public static final int MAX_CONCURRENT_EXECUTIONS = 2;

	/** {@code TAB_OPENED} 트리거가 permit을 못 얻었을 때 대기할 수 있는 큐 용량. */
	public static final int TAB_OPENED_QUEUE_CAPACITY = 4;

	/** 새 refresh 시작 토큰 버킷 — 분당 리필량. GitHub Search 한도(10/분)에 맞춘 값. */
	public static final int START_TOKENS_PER_MINUTE = 10;

	/** 토큰 버킷 burst 허용량. */
	public static final int START_TOKEN_BURST = 4;

	/** 작업 실행기 고정 worker 수. */
	public static final int EXECUTOR_WORKER_COUNT = 2;

	/** 저장소 검증→이슈 검색→댓글 수집→GMS→게시 전체에 허용된 시간. */
	public static final Duration TOTAL_BUDGET = Duration.ofSeconds(20);

	/** DB 게시 트랜잭션의 {@code statement_timeout} 예약(314의 실제 값과 별개로, 이 Phase가 기대하는 상한). */
	public static final Duration PUBLISH_BUDGET = Duration.ofSeconds(2);

	/** 완료된 작업을 registry에서 조회 가능하게 보존하는 시간. */
	public static final Duration COMPLETED_TASK_RETENTION = Duration.ofMinutes(10);

	/** 요약 실패(FAILED) 후 재시도를 허용하기까지의 쿨다운. */
	public static final Duration FAILURE_COOLDOWN = Duration.ofMinutes(5);

	/** 진행 중 조회 응답의 {@code poll_after_seconds} 안내값. */
	public static final int POLL_AFTER_SECONDS = 2;

	/** {@link RefreshTaskRegistry} 최대 항목 수(구현계획 "registry128"). */
	public static final int REGISTRY_MAX_ENTRIES = 128;

	/** 종료(shutdown) 시 실행 중 작업에 주는 유예 시간. */
	public static final Duration SHUTDOWN_GRACE_PERIOD = Duration.ofSeconds(5);
}
