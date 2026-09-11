package com.ssafy.pickage.domain.community.refresh;

import static org.junit.jupiter.api.Assertions.*;

import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

@Timeout(12)
class ConcurrencyContractReviewTest {
    @Test
    void R09_workerGetsFullBudgetAfterQueueWait() throws Exception {
        var task = new RefreshTask(1, RefreshStatus.QUEUED, Duration.ofMillis(1000));
        Thread.sleep(150);
        assertTrue(task.markRunning(RefreshStage.REPOSITORY_VERIFY));
        assertTrue(task.timeLeft().compareTo(Duration.ofMillis(900)) > 0);
    }

    @Test
    void R09_shutdownFinishesQueuedTasksWithoutStartingThem() {
        var registry = new RefreshTaskRegistry();
        var coordinator = new RefreshAdmissionCoordinator(registry);
        var entered = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        var queuedRan = new AtomicInteger();
        try {
            for (int i = 1; i <= 2; i++)
                coordinator.admit(
                        i,
                        RefreshTrigger.TAB_OPENED,
                        t ->
                                () -> {
                                    entered.countDown();
                                    await(release);
                                });
            await(entered);
            coordinator.admit(3, RefreshTrigger.TAB_OPENED, t -> queuedRan::incrementAndGet);
            try (var closer = Executors.newSingleThreadExecutor()) {
                var shutdown = closer.submit(coordinator::shutdown);
                Thread.sleep(50);
                release.countDown();
                shutdown.get(3, TimeUnit.SECONDS);
            } catch (Exception e) {
                throw new AssertionError(e);
            }
            assertEquals(0, queuedRan.get());
            assertFalse(registry.find(3).orElseThrow().isActive());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(6, TimeUnit.SECONDS)) throw new AssertionError("fixture timeout");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static List<AdmissionDecision> burst(
            RefreshAdmissionCoordinator coordinator,
            int count,
            boolean same,
            CountDownLatch release,
            AtomicInteger factories)
            throws Exception {
        var start = new CyclicBarrier(count);
        var results = new ArrayList<Future<AdmissionDecision>>();
        try (var threads = Executors.newFixedThreadPool(count)) {
            for (int i = 0; i < count; i++) {
                int id = same ? 900 : 900 + i;
                results.add(
                        threads.submit(
                                () -> {
                                    start.await(3, TimeUnit.SECONDS);
                                    return coordinator.admit(
                                            id,
                                            RefreshTrigger.TAB_OPENED,
                                            t -> {
                                                factories.incrementAndGet();
                                                return () -> await(release);
                                            });
                                }));
            }
            var decisions = new ArrayList<AdmissionDecision>();
            for (var result : results) decisions.add(result.get(3, TimeUnit.SECONDS));
            return decisions;
        }
    }

    @Test
    void R09_registryAdmissionMustBeAtomicAt128() throws Exception {
        var registry = new RefreshTaskRegistry();
        for (int i = 1; i <= 127; i++) {
            int id = i;
            registry.createOrJoin(id, () -> new RefreshTask(id, RefreshStatus.RUNNING))
                    .task()
                    .markCompleted();
        }
        var coordinator =
                new RefreshAdmissionCoordinator(
                        registry, Duration.ofSeconds(20), new StartTokenBucket(100, 100));
        var release = new CountDownLatch(1);
        try {
            var decisions = burst(coordinator, 50, false, release, new AtomicInteger());
            assertEquals(
                    1,
                    decisions.stream().filter(d -> d instanceof AdmissionDecision.Started).count());
            assertEquals(128, registry.size());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    @Test
    void R09_fiftySamePackageRequestsShareOneTask() throws Exception {
        var registry = new RefreshTaskRegistry();
        var coordinator = new RefreshAdmissionCoordinator(registry);
        var release = new CountDownLatch(1);
        var factories = new AtomicInteger();
        try {
            var decisions = burst(coordinator, 50, true, release, factories);
            assertEquals(1, factories.get());
            assertEquals(
                    1,
                    decisions.stream().filter(d -> d instanceof AdmissionDecision.Started).count());
            assertEquals(
                    49,
                    decisions.stream().filter(d -> d instanceof AdmissionDecision.Joined).count());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    @Test
    void R09_fiftyDifferentPackagesRespectTwoWorkersFourQueued() throws Exception {
        var registry = new RefreshTaskRegistry();
        var coordinator =
                new RefreshAdmissionCoordinator(
                        registry, Duration.ofSeconds(20), new StartTokenBucket(100, 100));
        var release = new CountDownLatch(1);
        var factories = new AtomicInteger();
        try {
            var decisions = burst(coordinator, 50, false, release, factories);
            assertEquals(6, factories.get());
            assertEquals(6, registry.size());
            assertEquals(
                    4,
                    decisions.stream()
                            .filter(d -> d instanceof AdmissionDecision.Started s && s.queued())
                            .count());
            assertEquals(
                    44,
                    decisions.stream()
                            .filter(d -> d instanceof AdmissionDecision.Rejected)
                            .count());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    @Test
    void R09_rejectedPrefetchMustNotConsumeStartToken() {
        var registry = new RefreshTaskRegistry();
        var bucket = new StartTokenBucket(1, 3);
        var coordinator = new RefreshAdmissionCoordinator(registry, Duration.ofSeconds(20), bucket);
        var release = new CountDownLatch(1);
        try {
            coordinator.admit(1, RefreshTrigger.TAB_OPENED, t -> () -> await(release));
            coordinator.admit(2, RefreshTrigger.TAB_OPENED, t -> () -> await(release));
            assertInstanceOf(
                    AdmissionDecision.Rejected.class,
                    coordinator.admit(3, RefreshTrigger.ANALYSIS_CONFIRMED, t -> () -> {}));
            assertTrue(bucket.tryAcquire());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    @Test
    void R09_queuedTaskMustNotHaveWorkerStartTime() {
        assertNull(new RefreshTask(1, RefreshStatus.QUEUED).snapshot().startedAt());
    }

    @Test
    void R09_queuedDeadlineMustExpireWithoutWorkerCompletion() throws Exception {
        var registry = new RefreshTaskRegistry();
        var coordinator =
                new RefreshAdmissionCoordinator(
                        registry, Duration.ofMillis(100), new StartTokenBucket(100, 10));
        var release = new CountDownLatch(1);
        try {
            coordinator.admit(1, RefreshTrigger.TAB_OPENED, t -> () -> await(release));
            coordinator.admit(2, RefreshTrigger.TAB_OPENED, t -> () -> await(release));
            coordinator.admit(3, RefreshTrigger.TAB_OPENED, t -> () -> {});
            Thread.sleep(300);
            var task = registry.find(3).orElseThrow();
            assertFalse(task.isActive());
            assertEquals(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, task.snapshot().errorCode());
        } finally {
            release.countDown();
            coordinator.shutdown();
        }
    }

    @Test
    void R09_terminalTaskMustNotBecomeRunningAgain() {
        var task = new RefreshTask(1, RefreshStatus.RUNNING);
        task.markFailed(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, Instant.now());
        task.markRunning(RefreshStage.COMMENTS);
        assertFalse(task.isActive());
    }

    @Test
    void R09_shutdownRejectsNewTasksWithoutLeakingRegistry() {
        var registry = new RefreshTaskRegistry();
        var coordinator = new RefreshAdmissionCoordinator(registry);
        coordinator.shutdown();
        assertInstanceOf(
                AdmissionDecision.Rejected.class,
                coordinator.admit(1, RefreshTrigger.TAB_OPENED, t -> () -> {}));
        assertEquals(0, registry.size());
    }
}
