package com.ssafy.pickage.domain.community.refresh;

import java.util.function.LongSupplier;

/**
 * 새 refresh 시작 속도 제한(구현계획 §설정과 보안 "전체 시작 10건/분·burst 4") — 표준
 * 토큰 버킷. GitHub Search 한도(10/분)에 맞춰, 두 트리거(ANALYSIS_CONFIRMED·TAB_OPENED)
 * 모두 "새 작업을 시작"할 때는 반드시 이 버킷을 먼저 통과해야 한다.
 *
 * <p>시각 소스를 {@link LongSupplier}(나노초)로 주입받는다 — 시험에서 실제로 잠들지 않고
 * 가짜 시계를 흘려보내 리필을 확인하기 위해서다.
 */
public class StartTokenBucket {

	private final double capacity;
	private final double refillPerNano;
	private final LongSupplier nanoClock;

	private double tokens;
	private long lastRefillNanos;

	public StartTokenBucket(int perMinute, int burstCapacity) {
		this(perMinute, burstCapacity, System::nanoTime);
	}

	/** 시험 전용 — 가짜 시계를 넣는다. */
	StartTokenBucket(int perMinute, int burstCapacity, LongSupplier nanoClock) {
		this.capacity = burstCapacity;
		this.refillPerNano = perMinute / 60_000_000_000.0;
		this.nanoClock = nanoClock;
		this.tokens = burstCapacity;
		this.lastRefillNanos = nanoClock.getAsLong();
	}

	/** @return 토큰을 하나 소비할 수 있었으면 {@code true}. */
	public synchronized boolean tryAcquire() {
		refill();
		if (tokens >= 1.0) {
			tokens -= 1.0;
			return true;
		}
		return false;
	}

	/**
	 * 소비한 토큰 하나를 되돌린다 — {@link RefreshAdmissionCoordinator}가 "새 작업을 시작하는
	 * 줄 알고 토큰을 썼는데 실제로는 이미 진행 중인 task에 참여하게 된" 경우에만 쓴다
	 * (/code-review에서 발견: registry 등록 직전 경합에서 진 요청의 토큰이 그냥 버려지고
	 * 있었다 — burst 상한을 넘지 않는다).
	 */
	public synchronized void refund() {
		tokens = Math.min(capacity, tokens + 1.0);
	}

	private void refill() {
		long now = nanoClock.getAsLong();
		long elapsedNanos = now - lastRefillNanos;
		if (elapsedNanos > 0) {
			tokens = Math.min(capacity, tokens + elapsedNanos * refillPerNano);
			lastRefillNanos = now;
		}
	}
}
