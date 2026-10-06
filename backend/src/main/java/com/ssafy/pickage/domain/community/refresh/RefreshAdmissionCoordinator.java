package com.ssafy.pickage.domain.community.refresh;

import com.ssafy.pickage.domain.community.CommunityProperties;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Function;

/** registry 모니터 하나로 admission 자원 변경을 직렬화한다. 실제 실행 종료 전에는 permit을 돌려주지 않는다. */
public class RefreshAdmissionCoordinator {
    private final RefreshTaskRegistry registry;
    private final StartTokenBucket tokens;
    private final Duration budget;
    private final ExecutorService executor =
            Executors.newFixedThreadPool(CommunityProperties.EXECUTOR_WORKER_COUNT);
    private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
    private final Deque<Work> queue = new ArrayDeque<>();
    private final Map<RefreshTask, Thread> running = new HashMap<>();
    private int occupied;
    private boolean closed;

    public RefreshAdmissionCoordinator(RefreshTaskRegistry registry) {
        this(
                registry,
                CommunityProperties.TOTAL_BUDGET,
                new StartTokenBucket(
                        CommunityProperties.START_TOKENS_PER_MINUTE,
                        CommunityProperties.START_TOKEN_BURST));
    }

    RefreshAdmissionCoordinator(
            RefreshTaskRegistry registry, Duration budget, StartTokenBucket tokens) {
        this.registry = registry;
        this.budget = budget;
        this.tokens = tokens;
        timer.scheduleWithFixedDelay(this::expire, 25, 25, TimeUnit.MILLISECONDS);
    }

    public AdmissionDecision admit(
            int packageId, RefreshTrigger trigger, Function<RefreshTask, Runnable> factory) {
        synchronized (registry) {
            var existing = registry.find(packageId);
            if (existing.filter(RefreshTask::isActive).isPresent())
                return new AdmissionDecision.Joined(existing.get());
            if (closed)
                return new AdmissionDecision.Rejected(CommunityErrorCode.COMMUNITY_DISABLED, null);
            if (existing.isEmpty() && registry.size() >= CommunityProperties.REGISTRY_MAX_ENTRIES)
                return new AdmissionDecision.Rejected();
            boolean queued = occupied >= CommunityProperties.MAX_CONCURRENT_EXECUTIONS;
            if (queued
                    && (trigger == RefreshTrigger.ANALYSIS_CONFIRMED
                            || queue.size() >= CommunityProperties.TAB_OPENED_QUEUE_CAPACITY))
                return new AdmissionDecision.Rejected();
            if (!tokens.tryAcquire())
                return new AdmissionDecision.Rejected(
                        CommunityErrorCode.LOCAL_RATE_LIMITED, Instant.now().plusSeconds(6));
            RefreshTask task = new RefreshTask(packageId, RefreshStatus.QUEUED, budget);
            Runnable runnable;
            try {
                runnable = factory.apply(task);
            } catch (RuntimeException e) {
                tokens.refund();
                throw e;
            }
            registry.createOrJoin(packageId, () -> task);
            var work = new Work(task, runnable);
            if (queued) queue.addLast(work);
            else submit(work);
            return new AdmissionDecision.Started(task, queued);
        }
    }

    private void submit(Work work) {
        occupied++;
        try {
            executor.execute(() -> execute(work));
        } catch (RejectedExecutionException e) {
            occupied--;
            tokens.refund();
            work.task.markFailed(CommunityErrorCode.COMMUNITY_DISABLED, null);
        }
    }

    private void execute(Work work) {
        boolean start;
        synchronized (registry) {
            start = work.task.markRunning(RefreshStage.REPOSITORY_VERIFY);
            if (start) running.put(work.task, Thread.currentThread());
        }
        try {
            if (start) work.runnable.run();
        } catch (RuntimeException e) {
            work.task.markFailed(
                    CommunityErrorCode.GITHUB_UNAVAILABLE, Instant.now().plusSeconds(300));
        } finally {
            synchronized (registry) {
                running.remove(work.task);
                occupied--;
                if (work.task.isActive())
                    work.task.markFailed(
                            CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED,
                            Instant.now().plusSeconds(300));
                dispatch();
            }
            Thread.interrupted();
        }
    }

    private void dispatch() {
        while (!closed
                && occupied < CommunityProperties.MAX_CONCURRENT_EXECUTIONS
                && !queue.isEmpty()) {
            Work next = queue.removeFirst();
            if (next.task.isPastDeadline() || !next.task.isActive()) {
                deadline(next.task);
                continue;
            }
            submit(next);
        }
    }

    private void expire() {
        synchronized (registry) {
            queue.removeIf(
                    work -> {
                        if (work.task.isPastDeadline()) {
                            deadline(work.task);
                            return true;
                        }
                        return false;
                    });
            running.forEach(
                    (task, thread) -> {
                        if (task.isPastDeadline()) {
                            deadline(task);
                            thread.interrupt();
                        }
                    });
            dispatch();
        }
    }

    private void deadline(RefreshTask task) {
        task.markFailed(
                CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, Instant.now().plusSeconds(300));
    }

    public void shutdown() {
        synchronized (registry) {
            closed = true;
        }
        executor.shutdown();
        try {
            executor.awaitTermination(
                    CommunityProperties.SHUTDOWN_GRACE_PERIOD.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        synchronized (registry) {
            queue.forEach(work -> deadline(work.task));
            queue.clear();
            running.forEach(
                    (task, thread) -> {
                        deadline(task);
                        thread.interrupt();
                    });
        }
        executor.shutdownNow();
        timer.shutdownNow();
    }

    private record Work(RefreshTask task, Runnable runnable) {}
}
