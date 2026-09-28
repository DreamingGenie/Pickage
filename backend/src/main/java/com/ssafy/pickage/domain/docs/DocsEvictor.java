package com.ssafy.pickage.domain.docs;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/*
* 문헌 폴더가 예산을 넘지 않게 오래 안 읽힌 것부터 지운다.
*
* 주기로 돌지 않는다. 폴더가 커지는 경로가 하나뿐이라 — 미스 때 DocStore.write 가 부르는
* 것 — 언제 커지는지를 이미 알고 있고, 주기로 물어보면 대부분 "안 넘었다" 만 확인하게 된다.
* 대신 기동 때 한 번 훑어 현재 크기를 잡고, 쓸 때마다 더하고, 넘으면 그때 깨운다.
*
* 오래됨의 기준은 atime 이다. 이 서버의 루트가 relatime 으로 붙어 있어 그날 처음 읽을 때
* 갱신된다. 하루 단위지만 19만 개 중 대부분이 평생 한 번도 안 읽히는 상황에서는 충분하다.
* mtime 을 쓰면 "오래전에 받았지만 매일 읽히는 문헌" 이 먼저 지워진다.
*/
@Component
public class DocsEvictor {

	private static final Logger log = LoggerFactory.getLogger(DocsEvictor.class);

	private final DocStore store;

	// 지금 폴더가 차지하는 디스크 크기. 기동 스캔이 채우고 쓰기·퇴출이 더하고 뺀다.
	private final AtomicLong used = new AtomicLong(0);

	// 기동 스캔이 끝나기 전에는 퇴출을 돌리지 않는다. 기준 없이 지우게 되기 때문이다.
	private final AtomicBoolean ready = new AtomicBoolean(false);

	// 퇴출은 한 번에 하나만 돈다. 여럿이 같이 돌면 같은 파일을 두 번 지우고 누적이 어긋난다.
	private final AtomicBoolean running = new AtomicBoolean(false);

	private final ExecutorService worker =
		Executors.newSingleThreadExecutor(r -> {
			Thread t = new Thread(r, "docs-evictor");
			t.setDaemon(true);
			return t;
		});

	public DocsEvictor(DocStore store) {
		this.store = store;
	}

	/*
	 * 기동할 때 한 번 폴더를 훑는다.
	 *
	 * 기동을 막지 않으려고 따로 돌린다 — 19만 개를 stat 하는 데 수십 초가 걸릴 수 있고,
	 * 그동안 헬스체크가 실패하면 컨테이너가 재시작 루프에 빠진다.
	 *
	 * 문헌 개수를 반드시 로그에 남긴다. 볼륨이 안 붙었으면 Docker 가 빈 폴더를 만들어
	 * 주는데 에러가 안 나서, 0 개라는 로그가 그걸 알아채는 유일한 신호다.
	 */
	@EventListener(ApplicationReadyEvent.class)
	public void scanOnStartup() {
		worker.submit(() -> {
			long started = System.nanoTime();
			long total = 0;
			long count = 0;
			try (Stream<Path> files = Files.walk(store.root())) {
				for (Path p : (Iterable<Path>) files.filter(Files::isRegularFile)::iterator) {
					total += DocStore.allocated(Files.size(p));
					count++;
				}
			} catch (IOException e) {
				log.warn("문헌 폴더를 훑지 못했다. 퇴출을 끈 채로 돈다: {}", store.root(), e);
				return;
			}
			used.set(total);
			ready.set(true);
			log.info("문헌 {}건 {}MB ({}초). 상한 {}MB", count, total >> 20,
				(System.nanoTime() - started) / 1_000_000_000L,
				DocsProperties.BUDGET_BYTES >> 20);
			maybeEvict();
		});
	}

	// 문헌 하나를 새로 쓴 만큼 누적에 더하고, 상한을 넘겼으면 퇴출을 깨운다.
	public void added(long bytes) {
		used.addAndGet(bytes);
		maybeEvict();
	}

	public long used() {
		return used.get();
	}

	// 상한을 넘었을 때만 퇴출을 띄운다. 이미 돌고 있으면 그냥 돌아간다.
	private void maybeEvict() {
		if (!ready.get() || used.get() <= DocsProperties.BUDGET_BYTES) {
			return;
		}
		if (running.compareAndSet(false, true)) {
			worker.submit(() -> {
				try {
					evict();
				} finally {
					running.set(false);
				}
			});
		}
	}

	/*
	 * 오래 안 읽힌 것부터 지워 LOW_BYTES 아래로 내린다.
	 *
	 * 한 번에 MAX_DELETE_PER_RUN 까지만 지운다. 5만 개를 한 호흡에 지우면 그동안 디스크가
	 * 계속 바쁘다. 남으면 다음 쓰기가 다시 깨운다 — 예산을 조금 넘긴 채로 잠시 있는 편이 낫다.
	 */
	private void evict() {
		List<Victim> victims = new ArrayList<>();
		try (Stream<Path> files = Files.walk(store.root())) {
			for (Path p : (Iterable<Path>) files.filter(Files::isRegularFile)::iterator) {
				BasicFileAttributes a = Files.readAttributes(p, BasicFileAttributes.class);
				victims.add(new Victim(p, a.lastAccessTime().toMillis(),
					DocStore.allocated(a.size())));
			}
		} catch (IOException e) {
			log.warn("퇴출 후보를 모으지 못했다: {}", store.root(), e);
			return;
		}

		victims.sort(Comparator.comparingLong(Victim::accessedAt));

		long freed = 0;
		int deleted = 0;
		for (Victim v : victims) {
			if (used.get() - freed <= DocsProperties.LOW_BYTES
				|| deleted >= DocsProperties.MAX_DELETE_PER_RUN) {
				break;
			}
			long gone = store.delete(v.path());
			if (gone > 0) {
				freed += gone;
				deleted++;
			}
		}
		used.addAndGet(-freed);
		log.info("문헌 {}건 {}MB 퇴출. 남은 사용량 {}MB", deleted, freed >> 20, used.get() >> 20);
	}

	private record Victim(Path path, long accessedAt, long bytes) {}
}
