package com.ssafy.pickage.domain.community.refresh;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.ssafy.pickage.domain.community.CommunityProperties;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

/**
 * 진행 중(또는 최근 완료된) 작업 하나의 가변 상태. 여러 스레드가 동시에 읽고
 * (GET 폴링) 쓴다(worker 스레드가 단계를 전진시킨다) — 모든 변경은 {@code synchronized}로
 * 감싸고, 읽는 쪽은 항상 {@link Snapshot} 불변 값을 받아간다(읽는 도중 값이 섞이지 않는다).
 *
 * <p><b>마감 시각은 이 task 하나에 딱 하나뿐이다.</b> Jira 317의 "TAB_OPENED queue4·대기20초"와
 * "실행20초" 예산을 별개의 두 타이머로 읽지 않고, "admission(큐 진입 포함)된 순간부터 20초"
 * 라는 단일 예산으로 해석했다 — 큐에서 기다린 시간도 이 20초 안에서 소진된다. 213/212가
 * 이미 "남은 시간을 매개변수로 받는다"는 계약으로 설계돼 있어({@code S15P21A506-212} §7)
 * 이 해석이 그대로 들어맞는다.
 */
public final class RefreshTask {

	private final int packageId;
	private final UUID refreshId;
	private final Instant startedAt;
	private final Instant deadline;

	private RefreshStatus status;
	private RefreshStage stage;
	private Instant lastUpdatedAt;
	private CommunityErrorCode errorCode;
	private Instant retryAt;
	private Instant completedAt;

	public RefreshTask(int packageId, RefreshStatus initialStatus) {
		this(packageId, initialStatus, CommunityProperties.TOTAL_BUDGET);
	}

	/** 시험 전용 — 20초를 기다리지 않고 예산을 짧게 줘서 마감 로직을 검증한다. */
	RefreshTask(int packageId, RefreshStatus initialStatus, Duration budget) {
		this.packageId = packageId;
		this.refreshId = UUID.randomUUID();
		this.startedAt = Instant.now();
		this.deadline = startedAt.plus(budget);
		this.status = initialStatus;
		this.stage = RefreshStage.REPOSITORY_VERIFY;
		this.lastUpdatedAt = startedAt;
	}

	public int packageId() {
		return packageId;
	}

	/** 213/212에 넘길 "남은 시간". 음수가 되지 않게 0으로 바닥을 둔다. */
	public Duration timeLeft() {
		Duration left = Duration.between(Instant.now(), deadline);
		return left.isNegative() ? Duration.ZERO : left;
	}

	public boolean isPastDeadline() {
		return !Instant.now().isBefore(deadline);
	}

	public synchronized void markRunning(RefreshStage stage) {
		this.status = RefreshStatus.RUNNING;
		this.stage = stage;
		this.lastUpdatedAt = Instant.now();
	}

	public synchronized void advanceStage(RefreshStage stage) {
		this.stage = stage;
		this.lastUpdatedAt = Instant.now();
	}

	public synchronized void markCompleted() {
		this.status = RefreshStatus.COMPLETED;
		this.stage = RefreshStage.PUBLISHING;
		Instant now = Instant.now();
		this.lastUpdatedAt = now;
		this.completedAt = now;
	}

	public synchronized void markFailed(CommunityErrorCode errorCode, Instant retryAt) {
		this.status = RefreshStatus.FAILED;
		this.errorCode = errorCode;
		this.retryAt = retryAt;
		Instant now = Instant.now();
		this.lastUpdatedAt = now;
		this.completedAt = now;
	}

	public synchronized void markCapacityLimited() {
		this.status = RefreshStatus.CAPACITY_LIMITED;
		Instant now = Instant.now();
		this.lastUpdatedAt = now;
		this.completedAt = now;
	}

	/** {@code COMPLETED}·{@code FAILED}·{@code CAPACITY_LIMITED} — registry 보존 시계가 시작되는 상태들. */
	public synchronized boolean isTerminal() {
		return completedAt != null;
	}

	/** registry의 single-flight 판단 — "진행 중"으로 취급해 참여시킬지. */
	public synchronized boolean isActive() {
		return status == RefreshStatus.QUEUED || status == RefreshStatus.RUNNING;
	}

	public synchronized Snapshot snapshot() {
		return new Snapshot(refreshId, status, stage, startedAt, lastUpdatedAt, errorCode, retryAt, completedAt);
	}

	/** GET/POST 응답 조립에 쓰는 불변 스냅샷. */
	public record Snapshot(
		UUID refreshId,
		RefreshStatus status,
		RefreshStage stage,
		Instant startedAt,
		Instant lastUpdatedAt,
		CommunityErrorCode errorCode,
		Instant retryAt,
		Instant completedAt
	) {
	}
}
