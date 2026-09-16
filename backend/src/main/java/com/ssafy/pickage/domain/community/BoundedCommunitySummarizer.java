package com.ssafy.pickage.domain.community;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;

/** refresh worker와 분리된 전역 pool/queue. 취소된 대기 작업도 queue에서 제거한다. */
public final class BoundedCommunitySummarizer implements AutoCloseable {
    private final CommunitySummarizer delegate;
    private final ThreadPoolExecutor executor =
            new ThreadPoolExecutor(
                    CommunityProperties.SUMMARIZER_WORKER_COUNT,
                    CommunityProperties.SUMMARIZER_WORKER_COUNT,
                    0,
                    TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(CommunityProperties.SUMMARIZER_QUEUE_CAPACITY));

    public BoundedCommunitySummarizer(CommunitySummarizer delegate) {
        this.delegate = delegate;
    }

    public TopicSummary summarize(CommunitySummarySourceBundle source, Duration budget) {
        return call(() -> delegate.summarize(source.issue(), budget), budget);
    }

    /**
     * {@link #summarize}와 같은 보장(예산 안에서 완료하거나 강제 인터럽트)을 별도 스레드에서
     * 기다리는 형태로 감싼다 — 호출자(={@link CommunityRefreshOrchestrator})가 이슈 여러 개를
     * 순차로 블로킹하지 않고 동시에 디스패치할 수 있게 한다(S15P21A506-368 후속). 실제 GMS
     * 호출 자체는 여전히 이 클래스의 {@code executor}에서만 돈다.
     */
    public CompletableFuture<TopicSummary> summarizeAsync(
            CommunitySummarySourceBundle source, Duration budget) {
        return CompletableFuture.supplyAsync(() -> summarize(source, budget));
    }

    /**
     * Map-Reduce(S15P21A506-373 4단계) Map 단계 — 배치 하나의 GMS 호출을 같은 bounded
     * executor에서 동시에 디스패치한다. 이슈 간 병렬 디스패치({@link #summarizeAsync})와
     * 같은 패턴이다.
     */
    CompletableFuture<TopicSummary> mapAsync(CommunitySummarySourceBundle batch, Duration budget) {
        return CompletableFuture.supplyAsync(
                () -> call(() -> delegate.summarize(batch.issue(), budget), budget));
    }

    /** Map-Reduce Reduce 단계 — 같은 bounded executor·타임아웃 보장을 공유한다. */
    TopicSummary reduce(List<CommunitySummarizer.BatchSummary> parts, Duration budget) {
        return call(() -> delegate.reduce(parts, budget), budget);
    }

    private TopicSummary call(Callable<TopicSummary> task, Duration budget) {
        if (budget.isZero() || budget.isNegative()) return TopicSummary.failed();
        Future<TopicSummary> future;
        try {
            future = executor.submit(task);
        } catch (RejectedExecutionException e) {
            return TopicSummary.failed();
        }
        try {
            return future.get(budget.toNanos(), TimeUnit.NANOSECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return TopicSummary.failed();
        } catch (ExecutionException | TimeoutException e) {
            return TopicSummary.failed();
        } finally {
            future.cancel(true);
            executor.purge();
        }
    }

    public void close() {
        executor.shutdownNow();
    }
}
