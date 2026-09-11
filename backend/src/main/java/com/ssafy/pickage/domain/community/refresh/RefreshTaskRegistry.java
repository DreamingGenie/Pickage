package com.ssafy.pickage.domain.community.refresh;

import com.ssafy.pickage.domain.community.CommunityProperties;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

/**
 * package_id → {@link RefreshTask}. {@link ConcurrentHashMap#computeIfAbsent}가 single-flight를 공짜로
 * 준다 — 같은 package에 대해 새 task가 둘 생기는 경합이 이 메서드 하나의 원자성으로 막힌다.
 *
 * <p>완료된 task는 {@link CommunityProperties#COMPLETED_TASK_RETENTION}(10분) 동안 조회 가능하게 남기고, 그 뒤에는 다음
 * 접근 시점에 지운다(별도 정리 스레드를 두지 않는다 — registry가 최대 {@link
 * CommunityProperties#REGISTRY_MAX_ENTRIES}(128)개라 매 접근마다 전체를 훑어도 비용이 작다).
 */
public class RefreshTaskRegistry {

    private final ConcurrentHashMap<Integer, RefreshTask> tasks = new ConcurrentHashMap<>();
    private final Duration retention;

    public RefreshTaskRegistry() {
        this(CommunityProperties.COMPLETED_TASK_RETENTION);
    }

    /** 시험 전용 — 10분을 기다리지 않고 보존 기간을 짧게 줘서 정리 로직을 검증한다. */
    RefreshTaskRegistry(Duration retention) {
        this.retention = retention;
    }

    public synchronized Optional<RefreshTask> find(int packageId) {
        evictExpired();
        return Optional.ofNullable(tasks.get(packageId));
    }

    /**
     * 이미 진행 중인 task가 있으면 그걸 돌려주고(참여), 없으면 {@code factory}로 새로 만들어 등록한다. {@code computeIfAbsent}의
     * 원자성이 "같은 package_id에 새 task가 둘 생기는" race를 막는다 — 이 메서드가 이 registry의 유일한 쓰기 진입점이어야 한다.
     *
     * <p>기존 task가 이미 종료(terminal) 상태라면 참여시키지 않고 새로 만든다 — "진행 중"만 single-flight 대상이다.
     */
    public synchronized JoinResult createOrJoin(int packageId, Supplier<RefreshTask> factory) {
        evictExpired();
        if (!tasks.containsKey(packageId)
                && tasks.size() >= CommunityProperties.REGISTRY_MAX_ENTRIES)
            throw new IllegalStateException("Community registry capacity");
        AtomicReference<Boolean> created = new AtomicReference<>(false);
        RefreshTask task =
                tasks.compute(
                        packageId,
                        (key, existing) -> {
                            if (existing != null && existing.isActive()) {
                                return existing;
                            }
                            created.set(true);
                            return factory.get();
                        });
        return new JoinResult(task, created.get());
    }

    /** 용량 확인용 — 활성+최근 완료 항목 수(구현계획 "registry128"). */
    public synchronized int size() {
        evictExpired();
        return tasks.size();
    }

    private void evictExpired() {
        Instant threshold = Instant.now().minus(retention);
        tasks.entrySet()
                .removeIf(
                        entry -> {
                            RefreshTask.Snapshot snapshot = entry.getValue().snapshot();
                            return snapshot.completedAt() != null
                                    && !snapshot.completedAt().isAfter(threshold);
                        });
    }

    /**
     * @param created {@code true}면 새로 만든 task(호출자가 실제 작업을 제출해야 함), {@code false}면 기존 task에 참여.
     */
    public record JoinResult(RefreshTask task, boolean created) {}
}
