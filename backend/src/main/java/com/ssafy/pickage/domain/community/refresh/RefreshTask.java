package com.ssafy.pickage.domain.community.refresh;

import com.ssafy.pickage.domain.community.CommunityProperties;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

import java.time.*;
import java.util.UUID;

/** terminal 전이는 되돌리지 않는다. 게시 권한은 이 task 모니터에서 commit과 함께 판정한다. */
public final class RefreshTask {
    private final int packageId;
    private final UUID refreshId = UUID.randomUUID();
    private final Duration budget;
    private final Instant queuedAt;
    private Instant startedAt, deadline, lastUpdatedAt, completedAt, retryAt;
    private RefreshStatus status;
    private RefreshStage stage;
    private CommunityErrorCode errorCode;

    public RefreshTask(int packageId, RefreshStatus status) {
        this(packageId, status, CommunityProperties.TOTAL_BUDGET);
    }

    RefreshTask(int packageId, RefreshStatus status, Duration budget) {
        this.packageId = packageId;
        this.budget = budget;
        queuedAt = Instant.now();
        lastUpdatedAt = queuedAt;
        this.status = RefreshStatus.QUEUED;
        deadline = queuedAt.plus(budget);
        if (status == RefreshStatus.RUNNING) markRunning(RefreshStage.REPOSITORY_VERIFY);
    }

    public int packageId() {
        return packageId;
    }

    public synchronized Duration timeLeft() {
        var d = Duration.between(Instant.now(), deadline);
        return d.isNegative() ? Duration.ZERO : d;
    }

    public synchronized Duration collectionTimeLeft() {
        var d = timeLeft().minus(CommunityProperties.PUBLISH_BUDGET);
        return d.isNegative() ? Duration.ZERO : d;
    }

    public synchronized boolean isPastDeadline() {
        return !Instant.now().isBefore(deadline);
    }

    public synchronized boolean markRunning(RefreshStage next) {
        if (isTerminal() || isPastDeadline()) return false;
        if (startedAt == null) {
            startedAt = Instant.now();
            deadline = startedAt.plus(budget);
        }
        status = RefreshStatus.RUNNING;
        stage = next;
        lastUpdatedAt = Instant.now();
        return true;
    }

    public synchronized void advanceStage(RefreshStage next) {
        if (status == RefreshStatus.RUNNING && !isTerminal()) {
            stage = next;
            lastUpdatedAt = Instant.now();
        }
    }

    public synchronized void markCompleted() {
        if (!isActive() || isPastDeadline()) return;
        status = RefreshStatus.COMPLETED;
        terminal();
    }

    public synchronized void markFailed(CommunityErrorCode error, Instant retry) {
        if (isTerminal()) return;
        status = RefreshStatus.FAILED;
        errorCode = error;
        retryAt = retry;
        terminal();
    }

    public synchronized void markCapacityLimited() {
        if (isTerminal()) return;
        status = RefreshStatus.CAPACITY_LIMITED;
        errorCode = CommunityErrorCode.CAPACITY_LIMITED;
        retryAt = Instant.now().plusSeconds(2);
        terminal();
    }

    private void terminal() {
        stage = null;
        completedAt = Instant.now();
        lastUpdatedAt = completedAt;
    }

    public synchronized boolean isTerminal() {
        return completedAt != null;
    }

    public synchronized boolean isActive() {
        return !isTerminal() && (status == RefreshStatus.QUEUED || status == RefreshStatus.RUNNING);
    }

    public synchronized void requirePublishable() {
        if (status != RefreshStatus.RUNNING
                || isTerminal()
                || isPastDeadline()
                || Thread.currentThread().isInterrupted())
            throw new IllegalStateException("Community publication ownership expired");
    }

    public synchronized void publishOwned(Runnable transaction) {
        requirePublishable();
        transaction.run();
        // 기한 내 시작한 commit이 성공했다면 저장 결과와 task 상태를 함께 확정한다.
        status = RefreshStatus.COMPLETED;
        terminal();
    }

    public synchronized Snapshot snapshot() {
        return new Snapshot(
                refreshId,
                status,
                stage,
                startedAt,
                lastUpdatedAt,
                errorCode,
                retryAt,
                completedAt);
    }

    public record Snapshot(
            UUID refreshId,
            RefreshStatus status,
            RefreshStage stage,
            Instant startedAt,
            Instant lastUpdatedAt,
            CommunityErrorCode errorCode,
            Instant retryAt,
            Instant completedAt) {}
}
