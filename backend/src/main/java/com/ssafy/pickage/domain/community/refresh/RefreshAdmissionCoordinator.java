package com.ssafy.pickage.domain.community.refresh;

import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

import com.ssafy.pickage.domain.community.CommunityProperties;

import lombok.extern.slf4j.Slf4j;

/**
 * Jira 317 "세부 항목"의 admission 규칙 전부를 한곳에서 조율한다 —
 * single-flight({@link RefreshTaskRegistry#createOrJoin})·시작 토큰 버킷·동시 실행
 * 세마포어(2)·{@code TAB_OPENED} 대기 큐(4)·고정 worker 2개.
 *
 * <p>admission 순서(§3.1, 문서 그대로): registry 용량 → 시작 토큰 → (permit 있으면 즉시
 * 실행) → 없으면 {@code ANALYSIS_CONFIRMED}는 무대기 거절, {@code TAB_OPENED}는 대기 큐.
 *
 * <p>이 클래스에 들어오기 <b>전에</b> "package 존재"·"기존 fresh 결과" 확인은 호출자
 * ({@code CommunityService}, Stage 3)가 이미 끝냈다고 가정한다 — 이 클래스는 순서 4번
 * (설정/호출량/용량)만 담당한다(Spec §3.1).
 *
 * <p><b>큐에 넣을 때 {@code Runnable}을 바로 만들어 저장한다.</b> 처음에는 대기 큐 항목에
 * task만 담고 실행할 작업은 그 항목을 꺼내 실행하는 시점(다른 요청이 permit을 반납한
 * 순간)에 넘겨받은 콜백으로 다시 만들려 했는데, 그러면 <b>A 요청이 큐에 넣은 작업이
 * B 요청의 permit 반납 시점에 B의 콜백으로 실행되는 버그</b>가 된다 — 서로 다른
 * package/요청마다 콜백이 캡처하는 값(패키지 이름, DB repo_url 등)이 다르기 때문이다.
 * 그래서 큐에 넣는 바로 그 시점에 {@code work.apply(task)}를 호출해 완성된
 * {@code Runnable} 자체를 저장한다.
 */
@Slf4j
public class RefreshAdmissionCoordinator {

	private final RefreshTaskRegistry registry;
	private final Semaphore executionPermits = new Semaphore(CommunityProperties.MAX_CONCURRENT_EXECUTIONS);
	private final StartTokenBucket startTokens;
	private final ExecutorService executor = Executors.newFixedThreadPool(CommunityProperties.EXECUTOR_WORKER_COUNT);
	private final Object queueLock = new Object();
	private final Deque<QueuedWork> tabOpenedQueue = new ArrayDeque<>();
	private final Duration taskBudget;

	public RefreshAdmissionCoordinator(RefreshTaskRegistry registry) {
		this(registry, CommunityProperties.TOTAL_BUDGET,
			new StartTokenBucket(CommunityProperties.START_TOKENS_PER_MINUTE, CommunityProperties.START_TOKEN_BURST));
	}

	/**
	 * 시험 전용 — 20초를 기다리지 않고 만든 task의 예산을 짧게 줄 수 있고, 시작 토큰 버킷도
	 * 갈아 끼울 수 있다(permit·큐 용량만 따로 검증하고 싶을 때 토큰 버킷이 먼저 걸리지
	 * 않도록 넉넉한 버킷을 넣는 식으로 쓴다).
	 */
	RefreshAdmissionCoordinator(RefreshTaskRegistry registry, Duration taskBudget, StartTokenBucket startTokens) {
		this.registry = registry;
		this.taskBudget = taskBudget;
		this.startTokens = startTokens;
	}

	/**
	 * @param work {@code RefreshTask}를 받아 실제 orchestrator 실행 콜백을 만드는 함수
	 *             (Stage 3에서 연결). 이 코디네이터는 <b>언제</b> 실행할지만 정하고
	 *             <b>무엇을</b> 실행할지는 모른다 — 다만 큐에 넣을 때는 그 콜백을 미리
	 *             만들어 고정한다(클래스 javadoc 참고).
	 */
	public AdmissionDecision admit(int packageId, RefreshTrigger trigger, Function<RefreshTask, Runnable> work) {
		Optional<RefreshTask> existing = registry.find(packageId);
		if (existing.filter(RefreshTask::isActive).isPresent()) {
			return new AdmissionDecision.Joined(existing.get());
		}

		// existing이 비어 있을 때만 "새 항목이 하나 늘어난다" — 이미 자리를 차지한 packageId의
		// 재시도는 registry.createOrJoin()의 compute()가 그 자리를 덮어쓸 뿐 늘리지 않는다
		// (/code-review에서 발견: 처음에는 이 조건 없이 registry.size()만 봐서, 정확히 128개가
		// 찬 상태에서 그중 하나(자기 자신)를 재시도해도 잘못 거절됐다).
		if (existing.isEmpty() && registry.size() >= CommunityProperties.REGISTRY_MAX_ENTRIES) {
			log.info("커뮤니티 admission 거절 — registry 용량 초과: packageId={}", packageId);
			return new AdmissionDecision.Rejected();
		}

		if (!startTokens.tryAcquire()) {
			log.info("커뮤니티 admission 거절 — 시작 토큰 소진: packageId={}, trigger={}", packageId, trigger);
			return new AdmissionDecision.Rejected();
		}

		if (executionPermits.tryAcquire()) {
			RefreshTaskRegistry.JoinResult join =
				registry.createOrJoin(packageId, () -> new RefreshTask(packageId, RefreshStatus.RUNNING, taskBudget));
			if (!join.created()) {
				// 토큰 확보와 registry 등록 사이에 다른 스레드가 먼저 만든 경우 — 방금 확보한
				// permit과 토큰 둘 다 이 요청이 실제로 쓰지 않았으니 돌려준다(/code-review —
				// 처음에는 permit만 돌려주고 토큰은 그대로 버려서, 같은 package로 중복 요청이
				// 반복되면 전역 시작 토큰이 조용히 새어 나갔다).
				executionPermits.release();
				startTokens.refund();
				return new AdmissionDecision.Joined(join.task());
			}
			RefreshTask task = join.task();
			task.markRunning(RefreshStage.REPOSITORY_VERIFY);
			submit(task, work.apply(task));
			return new AdmissionDecision.Started(task, false);
		}

		if (trigger == RefreshTrigger.ANALYSIS_CONFIRMED) {
			// "무대기 거절" — 토큰은 이미 소비했다(시도 자체에 대한 비용으로 간주).
			log.info("커뮤니티 admission 거절 — ANALYSIS_CONFIRMED 무대기: packageId={}", packageId);
			return new AdmissionDecision.Rejected();
		}

		synchronized (queueLock) {
			if (tabOpenedQueue.size() >= CommunityProperties.TAB_OPENED_QUEUE_CAPACITY) {
				// ANALYSIS_CONFIRMED의 무대기 거절과 다르다 — 그건 "permit이 없다"는 사실 자체를
				// 시도 비용으로 간주한다고 위에 명시돼 있지만, 여기는 대기조차 못 하고 버려지는
				// 것이라 실제로 시작한 것이 전혀 없다. 환불하지 않으면 큐가 계속 꽉 찬 상태에서
				// 들어오는 TAB_OPENED 요청마다 전역 토큰을 갉아먹어 다른 package의 정상 요청까지
				// 거절될 수 있다(리뷰에서 발견 — join 경합 패자를 환불하는 것과 같은 부류의 누수).
				startTokens.refund();
				log.info("커뮤니티 admission 거절 — TAB_OPENED 대기 큐 초과: packageId={}", packageId);
				return new AdmissionDecision.Rejected();
			}
			RefreshTaskRegistry.JoinResult join =
				registry.createOrJoin(packageId, () -> new RefreshTask(packageId, RefreshStatus.QUEUED, taskBudget));
			if (!join.created()) {
				startTokens.refund();
				return new AdmissionDecision.Joined(join.task());
			}
			RefreshTask task = join.task();
			tabOpenedQueue.addLast(new QueuedWork(task, work.apply(task)));
			return new AdmissionDecision.Started(task, true);
		}
	}

	/** 실행기에 제출한다. 끝나면(성공이든 예외든) permit을 반납하고 대기 큐 머리를 확인한다. */
	private void submit(RefreshTask task, Runnable runnable) {
		executor.submit(() -> {
			try {
				runnable.run();
			} catch (RuntimeException e) {
				log.error("커뮤니티 refresh 작업이 예외로 종료됨: packageId={}", task.packageId(), e);
			} finally {
				executionPermits.release();
				dispatchNextQueued();
			}
		});
	}

	/** worker 하나가 끝날 때마다 큐 머리를 확인한다 — 만료된(20초 예산 초과) 항목은 버리고 다음으로 넘어간다. */
	private void dispatchNextQueued() {
		QueuedWork next;
		synchronized (queueLock) {
			while (true) {
				next = tabOpenedQueue.pollFirst();
				if (next == null) {
					return;
				}
				if (!next.task().isPastDeadline()) {
					break;
				}
				log.info("커뮤니티 대기 큐 항목 만료(20초 예산 초과): packageId={}", next.task().packageId());
				next.task().markCapacityLimited();
			}
			if (!executionPermits.tryAcquire()) {
				// 방금 release 한 permit을 다른 admit() 호출이 먼저 가져간 경우 — 이 항목은
				// 큐 맨 앞으로 되돌려 다음 dispatch 기회를 기다린다.
				tabOpenedQueue.addFirst(next);
				return;
			}
		}
		next.task().markRunning(RefreshStage.REPOSITORY_VERIFY);
		submit(next.task(), next.runnable());
	}

	/** 애플리케이션 종료 시(Stage 3에서 {@code @PreDestroy}로 연결) 실행기를 정리한다. */
	public void shutdown() {
		executor.shutdown();
		try {
			if (!executor.awaitTermination(CommunityProperties.SHUTDOWN_GRACE_PERIOD.toMillis(), TimeUnit.MILLISECONDS)) {
				executor.shutdownNow();
			}
		} catch (InterruptedException e) {
			executor.shutdownNow();
			Thread.currentThread().interrupt();
		}
	}

	private record QueuedWork(RefreshTask task, Runnable runnable) {
	}
}
