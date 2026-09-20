package com.ssafy.pickage.domain.community;

import java.time.Duration;
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
        // 공용 풀이 아니라 전용 실행기다 — 이 스레드는 GMS 응답을 최대 30초 기다린다({@link CommunityAsync}).
        return CompletableFuture.supplyAsync(() -> summarize(source, budget), CommunityAsync.EXECUTOR);
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
