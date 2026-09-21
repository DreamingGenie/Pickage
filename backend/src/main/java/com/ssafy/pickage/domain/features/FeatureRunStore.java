package com.ssafy.pickage.domain.features;

import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

/**
 * 진행 중·끝난 기능 비교 run 을 담아 두는 곳.
 *
 * <p><b>DB 에 쓰지 않는다.</b> {@code DEC-FEATURE-CACHE-20260917-01}(S15P21A506-381)이 판정
 * 결과를 서버에 영속화하지 않기로 정했다. 그래서 여기는 메모리이고, 재시작하면 잊는다 —
 * 그게 의도다. 프런트도 직전 결과를 자기 세션에 들고 있는 것을 전제로 만들어져 있다.
 *
 * <p>재시작으로 잃는 것은 "진행 중이던 run 의 상태" 뿐이다. 다시 누르면 된다.
 */
@Component
public class FeatureRunStore {

	/**
	 * 끝난 run 을 이만큼 들고 있다가 버린다.
	 *
	 * <p>프런트가 결과를 받아 간 뒤에도 잠시 남겨 두는 이유는, 새로고침이나 재연결로 같은
	 * run 을 다시 물어보는 경우가 있어서다. 무한정 들고 있으면 비교 하나에 수십 KB 인 결과가
	 * 쌓여 api 컨테이너(1.6 GB 상한)를 먹는다.
	 */
	private static final Duration KEEP = Duration.ofMinutes(30);

	/** 이 수를 넘으면 오래된 것부터 버린다. 한 사람이 계속 눌러도 메모리가 안 늘게 한다. */
	private static final int MAX_RUNS = 200;

	private final Map<String, Run> runs = new ConcurrentHashMap<>();

	/**
	 * run 하나의 상태.
	 *
	 * <p><b>{@code phase} 는 백엔드가 실제로 지나온 단계만 담는다.</b> 프런트의
	 * {@code RUN_STEPS} 는 여섯 단계지만 백엔드가 보는 것은 "RAG 를 불렀다 / 답이 왔다" 뿐이다.
	 * 여섯 칸을 시간으로 흉내 내면 화면이 끝나지 않은 단계를 완료로 그린다 —
	 * {@code use-analysis-run.ts} 주석이 "서버가 실제로 끝냈다고 알려줄 때만 체크가 올라간다"
	 * 고 적어 둔 그 문제다. 더 잘게 알리려면 rag-api 가 진행을 흘려보내야 한다.
	 */
	public record Run(
		String runId,
		String status,
		String phase,
		List<String> refs,
		Instant startedAt,
		Instant finishedAt,
		/** JSON 원문. 트리가 아닌 이유는 {@link RagClient} 머리말 */
		String result,
		String errorCode,
		/** JSON 원문 */
		String errorDetail
	) {

		public static final String RUNNING = "RUNNING";
		public static final String COMPLETED = "COMPLETED";
		public static final String FAILED = "FAILED";
	}

	public void put(Run run) {
		runs.put(run.runId(), run);
		evict();
	}

	public Optional<Run> find(String runId) {
		return Optional.ofNullable(runs.get(runId));
	}

	/**
	 * 오래된 것과 넘치는 것을 버린다.
	 *
	 * <p>진행 중인 run 은 시간이 지나도 안 버린다 — 느린 것을 버리면 사용자가 기다리는 동안
	 * 상태 조회가 404 가 된다.
	 */
	private void evict() {
		Instant cutoff = Instant.now().minus(KEEP);
		runs.values().removeIf(run -> run.finishedAt() != null && run.finishedAt().isBefore(cutoff));

		if (runs.size() <= MAX_RUNS) {
			return;
		}
		runs.values().stream()
			.filter(run -> run.finishedAt() != null)
			.sorted(Comparator.comparing(Run::finishedAt))
			.limit(Math.max(0, runs.size() - MAX_RUNS))
			.map(Run::runId)
			.toList()
			.forEach(runs::remove);
	}

	public int size() {
		return runs.size();
	}
}
