package com.ssafy.pickage.domain.summary;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.domain.packages.PackageService;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.summary.dto.EcosystemSummaryResponse;

/**
 * 생태계 요약을 만들고 캐시한다.
 *
 * <p><b>캐시 키 = 정렬한 이름 + 기준일(최신 스냅샷).</b> 지표는 스냅샷이 바뀔 때만 바뀌므로 같은 조합은
 * 주 1회만 모델을 부른다. 같은 조합이 동시에 들어와도 호출은 한 번이다(같은 future 를 나눠 가진다).
 * 실패는 캐시하지 않는다 — 다음 요청이 다시 시도한다.
 *
 * <p>Redis 를 쓰지 않는 구조라(build.gradle 참고) 메모리에 둔다. 재기동하면 비워지고, 그때 한 번씩만 다시 부른다.
 */
public class EcosystemSummaryService {

	/** 이만큼 쌓이면 통째로 비운다. 조합 수가 이보다 많아질 일은 드물다. */
	private static final int CACHE_MAX = 512;
	/** 3개월 추세를 내려면 13주 + 평균 4주면 된다. 여유를 둬 20주만 읽는다. */
	private static final int TREND_READ_WEEKS = 20;

	private final PackageService packages;
	private final GmsEcosystemSummarizer summarizer;
	private final Map<String, CompletableFuture<EcosystemSummaryResponse>> cache = new ConcurrentHashMap<>();

	/** summarizer 가 null 이면 GMS 설정이 없는 것이다 — UNAVAILABLE 로 답한다. */
	public EcosystemSummaryService(PackageService packages, GmsEcosystemSummarizer summarizer) {
		this.packages = packages;
		this.summarizer = summarizer;
	}

	public EcosystemSummaryResponse summarize(PackageNames names) {
		PackagesOverviewResponse overview = packages.getOverview(names);
		LocalDate snapshotAt = overview.snapshotAt();
		if (summarizer == null) return EcosystemSummaryResponse.empty("UNAVAILABLE", snapshotAt);
		if (overview.items().isEmpty()) return EcosystemSummaryResponse.empty("NO_DATA", snapshotAt);

		String key = overview.items().stream().map(PackagesOverviewResponse.Item::name).sorted().toList()
			+ "@" + snapshotAt;
		CompletableFuture<EcosystemSummaryResponse> mine = new CompletableFuture<>();
		CompletableFuture<EcosystemSummaryResponse> existing = cache.putIfAbsent(key, mine);
		if (existing != null) {
			EcosystemSummaryResponse hit = existing.join();
			return "READY".equals(hit.status()) ? hit.asCached() : hit;
		}
		if (cache.size() > CACHE_MAX) {
			cache.clear();
			cache.put(key, mine);
		}

		EcosystemSummaryResponse result;
		try {
			result = call(overview, snapshotAt);
		} catch (RuntimeException e) {
			result = EcosystemSummaryResponse.empty("FAILED", snapshotAt);
		}
		if (!"READY".equals(result.status())) cache.remove(key, mine);
		mine.complete(result);
		return result;
	}

	private EcosystemSummaryResponse call(PackagesOverviewResponse overview, LocalDate snapshotAt) {
		List<EcosystemFacts> facts = factsOf(overview, snapshotAt);
		Optional<GmsEcosystemSummarizer.Result> r = summarizer.summarize(facts);
		return r.map(v -> new EcosystemSummaryResponse("READY", snapshotAt, v.common(), v.ecosystem(), false, v.usage()))
			.orElseGet(() -> EcosystemSummaryResponse.empty("FAILED", snapshotAt));
	}

	private List<EcosystemFacts> factsOf(PackagesOverviewResponse overview, LocalDate snapshotAt) {
		PackageNames found = PackageNames.of(overview.items().stream().map(PackagesOverviewResponse.Item::name).toList());
		LocalDate from = snapshotAt == null ? null : snapshotAt.minusWeeks(TREND_READ_WEEKS);
		TrendResponse downloads = packages.getDownloadsTrend(found, from, snapshotAt);
		TrendResponse dependents = packages.getDependentsTrend(found, from, snapshotAt);

		List<EcosystemFacts> facts = new ArrayList<>();
		for (PackagesOverviewResponse.Item item : overview.items()) {
			facts.add(new EcosystemFacts(
				item.name(),
				EcosystemFacts.shorten(item.description()),
				item.isDeprecated(),
				EcosystemFacts.levelOf(item.downloads()),
				EcosystemFacts.trendOf(pointsOf(downloads, item.name()), EcosystemFacts.DOWNLOADS_SMOOTH),
				EcosystemFacts.trendOf(pointsOf(dependents, item.name()), 1)));
		}
		return facts;
	}

	/** 한 이름의 시리즈를 날짜별로 합친다. 의존 등록 수는 major 마다 나뉘어 오므로 더해서 전체 선을 만든다. */
	static List<EcosystemFacts.Point> pointsOf(TrendResponse trend, String name) {
		TreeMap<LocalDate, Long> byDate = new TreeMap<>();
		for (TrendResponse.Series s : trend.series()) {
			if (!s.name().equals(name)) continue;
			for (TrendResponse.Point p : s.points()) byDate.merge(p.snapshotAt(), p.value(), Long::sum);
		}
		return byDate.entrySet().stream().map(e -> new EcosystemFacts.Point(e.getKey(), e.getValue())).toList();
	}
}
