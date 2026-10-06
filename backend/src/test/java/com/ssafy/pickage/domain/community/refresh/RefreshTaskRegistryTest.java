package com.ssafy.pickage.domain.community.refresh;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class RefreshTaskRegistryTest {

	@Test
	void 진행_중인_task가_있으면_그대로_참여시킨다() {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();

		var first = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));
		var second = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));

		assertThat(first.created()).isTrue();
		assertThat(second.created()).isFalse();
		assertThat(second.task()).isSameAs(first.task());
	}

	@Test
	void 종료된_task는_참여_대상이_아니고_새로_만든다() {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		var first = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));
		first.task().markCompleted();

		var second = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));

		assertThat(second.created()).isTrue();
		assertThat(second.task()).isNotSameAs(first.task());
	}

	@Test
	void 서로_다른_package는_독립적이다() {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();

		var pkg1 = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));
		var pkg2 = registry.createOrJoin(2, () -> new RefreshTask(2, RefreshStatus.RUNNING));

		assertThat(pkg1.created()).isTrue();
		assertThat(pkg2.created()).isTrue();
		assertThat(registry.size()).isEqualTo(2);
	}

	@Test
	void 보존_기간이_지난_완료_task는_다음_접근에서_사라진다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry(Duration.ofMillis(20));
		var joined = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));
		joined.task().markCompleted();

		assertThat(registry.find(1)).isPresent();

		Thread.sleep(50);

		assertThat(registry.find(1)).isEmpty();
	}

	@Test
	void 동시에_같은_package로_경합해도_task는_하나만_만들어진다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		int threads = 20;
		ExecutorService executor = Executors.newFixedThreadPool(threads);
		CountDownLatch ready = new CountDownLatch(threads);
		CountDownLatch go = new CountDownLatch(1);
		AtomicInteger createdCount = new AtomicInteger();

		for (int i = 0; i < threads; i++) {
			executor.submit(() -> {
				ready.countDown();
				try {
					go.await();
				} catch (InterruptedException e) {
					Thread.currentThread().interrupt();
				}
				var result = registry.createOrJoin(1, () -> new RefreshTask(1, RefreshStatus.RUNNING));
				if (result.created()) {
					createdCount.incrementAndGet();
				}
			});
		}

		ready.await();
		go.countDown();
		executor.shutdown();
		assertThat(executor.awaitTermination(5, TimeUnit.SECONDS)).isTrue();

		assertThat(createdCount.get()).isEqualTo(1);
	}
}
