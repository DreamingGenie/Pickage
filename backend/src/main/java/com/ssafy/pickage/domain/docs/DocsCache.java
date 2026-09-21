package com.ssafy.pickage.domain.docs;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/*
* 기능-12 가 문헌을 얻는 입구. 파일에 있으면 읽고, 없으면 받아 만들어 같은 자리에 쓴다.
*
* 대부분의 요청은 파일 하나 여는 것으로 끝난다 — 19만 건이 미리 깔려 있다.
*/
@Component
public class DocsCache {

	private static final Logger log = LoggerFactory.getLogger(DocsCache.class);

	private final DocStore store;
	private final DocFetcher fetcher;
	private final DocsEvictor evictor;

	/*
	 * 지금 받고 있는 것들. 같은 패키지에 동시 요청이 셋 와도 호출은 한 번이다.
	 *
	 * 파일 쓰기는 이름 바꾸기라 동시에 써도 깨지지 않지만, 같은 것을 세 번 받는 것은
	 * jsDelivr 한도를 세 배로 쓰는 일이다. 비교 화면을 두 사람이 동시에 열면 그대로 겹친다.
	 */
	private final Map<String, CompletableFuture<Optional<String>>> inFlight =
		new ConcurrentHashMap<>();

	/*
	 * CDN 에 없다고 확인된 것들. 만료 전에는 다시 묻지 않는다.
	 *
	 * 파일로 남기지 않는 이유는 빈 파일이 "문헌이 있다" 와 구분되지 않아서다. 재시작하면
	 * 잊는데, 프리로드 실측으로 그런 버전이 754건뿐이라 다시 묻는 비용이 작다.
	 */
	private final Map<String, Instant> absent = new ConcurrentHashMap<>();

	public DocsCache(DocStore store, DocFetcher fetcher, DocsEvictor evictor) {
		this.store = store;
		this.fetcher = fetcher;
		this.evictor = evictor;
	}

	public record Ref(String name, String version) {}

	/*
	 * 문헌 여럿을 한 번에 얻는다. 못 얻은 것은 결과에 없다.
	 *
	 * 예산은 셋이 나눠 쓰는 것이 아니라 셋이 함께 쓰는 벽시계다. 그래서 미스들을 동시에
	 * 보낸다 — 순서대로 받으면 앞의 하나가 느릴 때 뒤의 것들이 예산을 못 받는다.
	 *
	 * 넣은 순서를 지킨다. 프롬프트에서 패키지 순서가 바뀌면 비교 문장이 엉뚱한 쪽을 가리킨다.
	 */
	public Map<Ref, String> load(List<Ref> refs) {
		Map<Ref, String> found = new LinkedHashMap<>();
		Map<Ref, CompletableFuture<Optional<String>>> pending = new LinkedHashMap<>();
		long deadline = System.nanoTime() + DocsProperties.TOTAL_BUDGET.toNanos();

		for (Ref ref : refs) {
			Optional<String> hit = store.read(ref.name(), ref.version());
			if (hit.isPresent()) {
				found.put(ref, hit.get());
			} else {
				pending.put(ref, obtain(ref, deadline));
			}
		}

		for (Map.Entry<Ref, CompletableFuture<Optional<String>>> e : pending.entrySet()) {
			try {
				e.getValue().join().ifPresent(doc -> found.put(e.getKey(), doc));
			} catch (Exception ex) {
				log.debug("문헌을 얻지 못했다 {}", e.getKey(), ex);
			}
		}

		// 넣은 순서대로 다시 담는다. 미스가 늦게 끝나 순서가 섞였을 수 있다.
		Map<Ref, String> ordered = new LinkedHashMap<>();
		for (Ref ref : refs) {
			String doc = found.get(ref);
			if (doc != null) {
				ordered.put(ref, doc);
			}
		}
		return ordered;
	}

	// 하나만 얻는다. 예산은 이 한 건이 전부 쓴다.
	public Optional<String> load(Ref ref) {
		Optional<String> hit = store.read(ref.name(), ref.version());
		if (hit.isPresent()) {
			return hit;
		}
		return obtain(ref, System.nanoTime() + DocsProperties.TOTAL_BUDGET.toNanos()).join();
	}

	/*
	 * 미스 하나를 받아 온다. 이미 같은 것을 받고 있으면 그 결과를 같이 기다린다.
	 *
	 * 끝나면 목록에서 뺀다. 안 빼면 한 번 실패한 패키지가 영원히 그 실패를 돌려준다.
	 */
	private CompletableFuture<Optional<String>> obtain(Ref ref, long deadline) {
		String key = ref.name() + "@" + ref.version();

		Instant until = absent.get(key);
		if (until != null) {
			if (until.isAfter(Instant.now())) {
				return CompletableFuture.completedFuture(Optional.empty());
			}
			absent.remove(key);
		}

		return inFlight.computeIfAbsent(key, k ->
			CompletableFuture.supplyAsync(() -> build(ref, k, deadline))
				.whenComplete((r, t) -> inFlight.remove(k)));
	}

	/*
	 * 받아서 쓰고 돌려준다.
	 *
	 * 쓰기에 실패해도 문헌은 돌려준다. 디스크가 가득 찼거나 권한이 없을 때 이번 분석까지
	 * 못 하게 할 이유가 없다 — 다음 요청이 다시 받을 뿐이다.
	 */
	private Optional<String> build(Ref ref, String key, long deadline) {
		Optional<String> made = fetcher.fetch(ref.name(), ref.version(), deadline);
		if (made.isEmpty()) {
			absent.put(key, Instant.now().plus(DocsProperties.MISSING_TTL));
			return Optional.empty();
		}
		try {
			long bytes = store.write(ref.name(), ref.version(), made.get());
			evictor.added(bytes);
		} catch (IOException e) {
			log.warn("문헌을 쓰지 못했다 {}: {}", key, e.toString());
		}
		return made;
	}

	// 음성 캐시에서 만료된 것을 털어 낸다. 놔두면 못 찾는 이름이 쌓이는 만큼 메모리를 먹는다.
	public void sweepAbsent() {
		Instant now = Instant.now();
		absent.entrySet().removeIf(e -> e.getValue().isBefore(now));
	}

	// 지금 받고 있는 건수. 상태 확인용이다.
	public int inFlightCount() {
		return inFlight.size();
	}

	static Duration budget() {
		return DocsProperties.TOTAL_BUDGET;
	}
}
