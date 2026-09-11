package com.ssafy.pickage.domain.community.refresh;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

class StartTokenBucketTest {

	@Test
	void burst_용량만큼은_즉시_연속으로_쓸_수_있다() {
		StartTokenBucket bucket = new StartTokenBucket(10, 4, () -> 0L);

		assertThat(bucket.tryAcquire()).isTrue();
		assertThat(bucket.tryAcquire()).isTrue();
		assertThat(bucket.tryAcquire()).isTrue();
		assertThat(bucket.tryAcquire()).isTrue();
		assertThat(bucket.tryAcquire()).isFalse();
	}

	@Test
	void 시간이_지나면_분당_리필률만큼_다시_채워진다() {
		AtomicLong clock = new AtomicLong(0L);
		StartTokenBucket bucket = new StartTokenBucket(10, 4, clock::get);

		// burst 4개를 전부 소진.
		for (int i = 0; i < 4; i++) {
			assertThat(bucket.tryAcquire()).isTrue();
		}
		assertThat(bucket.tryAcquire()).isFalse();

		// 10개/분 = 6초당 1개. 6초 지남을 시뮬레이션.
		clock.addAndGet(6_000_000_000L);
		assertThat(bucket.tryAcquire()).isTrue();
		assertThat(bucket.tryAcquire()).isFalse();
	}

	@Test
	void 리필은_burst_상한을_넘지_않는다() {
		AtomicLong clock = new AtomicLong(0L);
		StartTokenBucket bucket = new StartTokenBucket(10, 4, clock::get);

		// 아무것도 안 쓰고 1시간 지나도 4개 넘게 못 쓴다.
		clock.addAndGet(3_600_000_000_000L);
		for (int i = 0; i < 4; i++) {
			assertThat(bucket.tryAcquire()).isTrue();
		}
		assertThat(bucket.tryAcquire()).isFalse();
	}
}
