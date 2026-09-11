package com.ssafy.pickage.domain.community;

import java.time.Duration;
import java.util.concurrent.*;

/** refresh worker와 분리된 전역 pool2/queue2. 취소된 대기 작업도 queue에서 제거한다. */
public final class BoundedCommunitySummarizer implements AutoCloseable {
    private final CommunitySummarizer delegate;
    private final ThreadPoolExecutor executor =
            new ThreadPoolExecutor(2, 2, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(2));

    public BoundedCommunitySummarizer(CommunitySummarizer delegate) {
        this.delegate = delegate;
    }

    public TopicSummary summarize(CommunitySummarySourceBundle source, Duration budget) {
        if (budget.isZero() || budget.isNegative()) return TopicSummary.failed();
        Future<TopicSummary> future;
        try {
            future = executor.submit(() -> delegate.summarize(source.issue()));
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
