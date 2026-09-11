package com.ssafy.pickage.domain.community.refresh;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Collections;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.CommunityProperties;

class RefreshAdmissionCoordinatorTest {

	private final List<RefreshAdmissionCoordinator> coordinators = new ArrayList<>();

	@AfterEach
	void 실행기를_정리한다() {
		coordinators.forEach(RefreshAdmissionCoordinator::shutdown);
	}

	private RefreshAdmissionCoordinator coordinator(RefreshTaskRegistry registry) {
		return coordinator(registry, CommunityProperties.TOTAL_BUDGET);
	}

	private RefreshAdmissionCoordinator coordinator(RefreshTaskRegistry registry, Duration taskBudget) {
		// permit·큐 용량만 검증하는 시험이 토큰 버킷에 먼저 걸리지 않도록 넉넉한 버킷을 준다.
		RefreshAdmissionCoordinator coordinator =
			new RefreshAdmissionCoordinator(registry, taskBudget, new StartTokenBucket(1_000_000, 1_000_000));
		coordinators.add(coordinator);
		return coordinator;
	}

	private static void await(CountDownLatch latch) throws InterruptedException {
		assertThat(latch.await(2, TimeUnit.SECONDS)).isTrue();
	}

	@Test
	void permit이_있으면_즉시_실행하고_Started를_돌려준다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch done = new CountDownLatch(1);

		AdmissionDecision decision =
			coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> done::countDown);

		assertThat(decision).isInstanceOf(AdmissionDecision.Started.class);
		assertThat(((AdmissionDecision.Started) decision).queued()).isFalse();
		await(done);
	}

	@Test
	void 이미_진행_중인_task가_있으면_참여시킨다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch started = new CountDownLatch(1);
		CountDownLatch release = new CountDownLatch(1);

		AdmissionDecision first = coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			started.countDown();
			awaitUnchecked(release);
		});
		await(started);

		AdmissionDecision second = coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> { });

		assertThat(first).isInstanceOf(AdmissionDecision.Started.class);
		assertThat(second).isInstanceOf(AdmissionDecision.Joined.class);
		assertThat(((AdmissionDecision.Joined) second).task())
			.isSameAs(((AdmissionDecision.Started) first).task());

		release.countDown();
	}

	@Test
	void 동시_실행_상한을_넘으면_TAB_OPENED는_대기_큐에_들어간다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch running = new CountDownLatch(2);
		CountDownLatch release = new CountDownLatch(1);

		coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		await(running);

		AdmissionDecision decision = coordinator.admit(3, RefreshTrigger.TAB_OPENED, task -> () -> { });

		assertThat(decision).isInstanceOf(AdmissionDecision.Started.class);
		assertThat(((AdmissionDecision.Started) decision).queued()).isTrue();

		release.countDown();
	}

	@Test
	void 동시_실행_상한을_넘으면_ANALYSIS_CONFIRMED는_대기_없이_거절된다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch running = new CountDownLatch(2);
		CountDownLatch release = new CountDownLatch(1);

		coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		await(running);

		AdmissionDecision decision = coordinator.admit(3, RefreshTrigger.ANALYSIS_CONFIRMED, task -> () -> { });

		assertThat(decision).isInstanceOf(AdmissionDecision.Rejected.class);

		release.countDown();
	}

	@Test
	void 대기_큐가_가득_차면_TAB_OPENED도_거절된다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch running = new CountDownLatch(2);
		CountDownLatch release = new CountDownLatch(1);

		coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		await(running);

		// 큐 용량(4)을 채운다.
		for (int packageId = 3; packageId <= 6; packageId++) {
			AdmissionDecision decision = coordinator.admit(packageId, RefreshTrigger.TAB_OPENED, task -> () -> { });
			assertThat(decision).isInstanceOf(AdmissionDecision.Started.class);
			assertThat(((AdmissionDecision.Started) decision).queued()).isTrue();
		}

		AdmissionDecision overflow = coordinator.admit(7, RefreshTrigger.TAB_OPENED, task -> () -> { });

		assertThat(overflow).isInstanceOf(AdmissionDecision.Rejected.class);

		release.countDown();
	}

	@Test
	void registry_용량이_차면_거절한다() {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);

		for (int packageId = 1; packageId <= CommunityProperties.REGISTRY_MAX_ENTRIES; packageId++) {
			int id = packageId;
			registry.createOrJoin(id, () -> new RefreshTask(id, RefreshStatus.RUNNING));
		}

		AdmissionDecision decision = coordinator.admit(9999, RefreshTrigger.TAB_OPENED, task -> () -> { });

		assertThat(decision).isInstanceOf(AdmissionDecision.Rejected.class);
	}

	@Test
	void 시작_토큰이_소진되면_permit_유무와_무관하게_거절한다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = new RefreshAdmissionCoordinator(
			registry, CommunityProperties.TOTAL_BUDGET, new StartTokenBucket(0, 1));
		coordinators.add(coordinator);
		CountDownLatch done = new CountDownLatch(1);

		AdmissionDecision first = coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> done::countDown);
		await(done);

		AdmissionDecision second = coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> { });

		assertThat(first).isInstanceOf(AdmissionDecision.Started.class);
		assertThat(second).isInstanceOf(AdmissionDecision.Rejected.class);
	}

	@Test
	void 대기_중이던_작업은_permit_반납_시점에_자신의_고유한_콜백으로_실행된다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry);
		CountDownLatch running1Started = new CountDownLatch(1);
		CountDownLatch running1Release = new CountDownLatch(1);
		CountDownLatch running2Started = new CountDownLatch(1);
		CountDownLatch running2Release = new CountDownLatch(1);
		CountDownLatch pkg3Done = new CountDownLatch(1);
		List<String> executed = Collections.synchronizedList(new ArrayList<>());

		coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			running1Started.countDown();
			awaitUnchecked(running1Release);
			executed.add("pkg1");
		});
		coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> {
			running2Started.countDown();
			awaitUnchecked(running2Release);
			executed.add("pkg2");
		});
		await(running1Started);
		await(running2Started);

		// permit이 없으므로 큐에 들어간다 — 이 콜백은 "pkg3"이라는 자기 고유 데이터를 캡처한다.
		AdmissionDecision decision3 = coordinator.admit(3, RefreshTrigger.TAB_OPENED, task -> () -> {
			executed.add("pkg3");
			pkg3Done.countDown();
		});
		assertThat(decision3).isInstanceOf(AdmissionDecision.Started.class);
		assertThat(((AdmissionDecision.Started) decision3).queued()).isTrue();

		// pkg1이 끝나 permit을 반납하면 큐의 pkg3이 "다른 요청(pkg2)의 콜백"이 아니라
		// 자기 자신의 콜백으로 실행돼야 한다 — 이전에 있던 버그의 회귀 시험.
		running1Release.countDown();
		await(pkg3Done);

		assertThat(executed).contains("pkg3").doesNotContain("pkg2");

		running2Release.countDown();
	}

	@Test
	void 큐에서_대기_중_예산이_지나면_실행되지_않고_용량_제한으로_끝난다() throws InterruptedException {
		RefreshTaskRegistry registry = new RefreshTaskRegistry();
		RefreshAdmissionCoordinator coordinator = coordinator(registry, Duration.ofMillis(20));
		CountDownLatch running = new CountDownLatch(2);
		CountDownLatch release = new CountDownLatch(1);

		coordinator.admit(1, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		coordinator.admit(2, RefreshTrigger.TAB_OPENED, task -> () -> {
			running.countDown();
			awaitUnchecked(release);
		});
		await(running);

		CountDownLatch wronglyExecuted = new CountDownLatch(1);
		AdmissionDecision decision3 =
			coordinator.admit(3, RefreshTrigger.TAB_OPENED, task -> wronglyExecuted::countDown);
		RefreshTask task3 = ((AdmissionDecision.Started) decision3).task();

		Thread.sleep(50);
		release.countDown();

		Thread.sleep(200);
		assertThat(task3.snapshot().status()).isEqualTo(RefreshStatus.CAPACITY_LIMITED);
		assertThat(wronglyExecuted.getCount()).isEqualTo(1L);
	}

	private static void awaitUnchecked(CountDownLatch latch) {
		try {
			latch.await(2, TimeUnit.SECONDS);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
		}
	}
}
