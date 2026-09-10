package com.ssafy.pickage.domain.packages;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.OverviewRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.ShareRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;
import com.ssafy.pickage.domain.packages.dto.PackageSearchResponse;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 조회 서비스.
 *
 * <p>여기서 하는 일은 명세 0.7 이 정한 두 가지뿐이다 — <b>JSON 모양으로 바꾸고, 요청 순서로
 * 재배열한다.</b> 합계·비율·증감은 전부 DB 에서 끝난다. 같은 계산을 애플리케이션이 다시 하면
 * 언젠가 두 곳의 숫자가 달라진다.
 *
 * <h2>{@code not_found} 는 "행이 없음" 이 아니라 "이름이 없음" 이다</h2>
 *
 * 네 엔드포인트가 <b>같은 기준</b>으로 계산해야 한다. 프론트가 세 응답의 {@code not_found} 를
 * 합집합으로 묶어 "찾지 못한 패키지" 를 띄우기 때문이다(`ecosystem/adapter.ts`).
 *
 * <p>그래서 조회 결과가 비었다고 {@code not_found} 에 넣지 않는다. 예를 들어 스냅샷이 아직
 * 없는 패키지는 추이 행이 0개인데, 그걸 "못 찾음" 으로 치면 <b>개요에는 카드가 뜨는데 동시에
 * "이 패키지를 찾지 못했습니다" 가 함께 뜬다.</b> 존재하는 이름은 빈 시리즈·빈 조각으로 내보내고,
 * {@code not_found} 에는 {@code package} 테이블에 아예 없는 이름만 담는다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PackageService {

	private final PackageQueryRepository repository;

	/* ------------------------------------------------------------------ *
	 * §3 개요
	 * ------------------------------------------------------------------ */

	@Transactional(readOnly = true)
	public PackagesOverviewResponse getOverview(PackageNames names) {
		List<OverviewRow> rows = repository.findOverview(names);

		// 0.5 — DB 는 순서를 보장하지 않는다. 요청한 이름 순서로 다시 세운다.
		Map<String, OverviewRow> byName = rows.stream()
			.collect(Collectors.toMap(OverviewRow::name, Function.identity()));

		List<PackagesOverviewResponse.Item> items = names.values().stream()
			.map(byName::get)
			.filter(Objects::nonNull)
			.map(PackageService::toItem)
			.toList();

		List<String> notFound = names.notFoundAmong(items.stream()
			.map(PackagesOverviewResponse.Item::name)
			.toList());

		warnIfSilentlyDropped(names, notFound);

		// snapshot_at 은 적재 전이면 null 이다. 0.5 가 "모든 현재값의 기준" 으로 정한 값이라
		// 임의의 날짜로 채우면 화면이 있지도 않은 기준일을 표시하게 된다.
		return new PackagesOverviewResponse(repository.findLatestSnapshot(), items, notFound);
	}

	/**
	 * 개요 SQL 은 {@code latest_ver} 를 INNER JOIN 하므로 <b>{@code version} 행이 하나도 없는
	 * 패키지가 결과에서 빠진다.</b> 그러면 존재하는 이름이 {@code not_found} 로 분류되고,
	 * 화면은 "이름을 확인하세요" 를 띄운다 — 사용자는 멀쩡한 이름을 계속 다시 친다.
	 *
	 * <p>실제 DB 로 갈라 확인한 결과, 스냅샷만 없는 경우(consola)는 정상 동작하고
	 * {@code version} 행이 아예 없는 경우만 해당된다. 파이프라인이 {@code package} 를
	 * versions 에서 파생시키므로 실제로는 생기지 않을 것으로 보지만, <b>전제가 깨졌을 때
	 * 조용히 지나가지 않도록</b> 로그를 남긴다. 이 경고가 찍히기 시작하면 SQL 을 LEFT JOIN 으로
	 * 바꾸고 {@code latest_version} 을 nullable 로 열어야 한다(프론트 타입도 함께).
	 */
	private void warnIfSilentlyDropped(PackageNames names, List<String> notFound) {
		if (notFound.isEmpty()) return;

		List<String> dropped = notFound.stream()
			.filter(repository.findExistingNames(names)::contains)
			.toList();

		if (!dropped.isEmpty()) {
			log.warn("package 에는 있으나 version 행이 없어 응답에서 빠진 이름: {}."
				+ " not_found 로 잘못 분류된다 — 개요 SQL 의 latest_ver JOIN 을 봐야 한다.", dropped);
		}
	}

	private static PackagesOverviewResponse.Item toItem(OverviewRow r) {
		return new PackagesOverviewResponse.Item(
			r.name(),
			r.repoUrl(),
			r.latestVersion(),
			// version.published_at 은 시간대 없는 TIMESTAMP 다. 적재된 값이 UTC 라는 전제로
			// UTC 를 붙인다. atZone(systemDefault()) 을 쓰면 KST 로 해석되어 9시간이 밀리고,
			// 에러 없이 조용히 틀린다.
			r.publishedAt() == null ? null : r.publishedAt().toInstant(ZoneOffset.UTC),
			r.description(),
			r.licenses(),
			r.isDeprecated(),
			r.downloads(),
			r.stars(),
			r.starsDelta(),
			r.openIssues(),
			r.openIssuesDelta());
	}

	/* ------------------------------------------------------------------ *
	 * §4·§5 추이
	 * ------------------------------------------------------------------ */

	@Transactional(readOnly = true)
	public TrendResponse getDownloadsTrend(PackageNames names, LocalDate from, LocalDate to) {
		Existing existing = existing(names);
		return TrendResponse.downloads(
			toSeries(trendRows(from, to, window -> repository.findDownloadsTrend(names, window)), existing),
			existing.notFound());
	}

	@Transactional(readOnly = true)
	public TrendResponse getDependentsTrend(PackageNames names, LocalDate from, LocalDate to) {
		Existing existing = existing(names);
		return TrendResponse.dependents(
			toSeries(trendRows(from, to, window -> repository.findDependentsTrend(names, window)), existing),
			existing.notFound());
	}

	/**
	 * 구간을 정하고 조회한다.
	 *
	 * <p>§4 — 기본 구간의 기준은 오늘이 아니라 <b>최신 스냅샷</b>이다.
	 *
	 * <p><b>스냅샷이 하나도 없으면 구간 자체가 없다</b>({@link SnapshotWindow#of}). 그때는 DB 에
	 * 묻지 않고 빈 행 집합을 돌려준다 — 존재하는 이름은 {@link #toSeries} 를 지나며 빈 시리즈가
	 * 되고, 응답은 200 이다. 적재 전이거나 첫 스냅샷을 기다리는 동안의 <b>정상 상태</b>이지
	 * 장애가 아니다.
	 */
	private List<TrendRow> trendRows(LocalDate from, LocalDate to,
		Function<SnapshotWindow, List<TrendRow>> query) {
		return SnapshotWindow.of(from, to, repository.findLatestSnapshot())
			.map(query)
			.orElseGet(List::of);
	}

	/**
	 * 평평한 행을 <b>(이름, major)</b> 별로 묶는다.
	 *
	 * <p>downloads 는 {@code major} 가 항상 {@code null} 이라 이름당 하나로 묶이고,
	 * dependents 는 major 개수만큼 갈라진다. <b>SQL 이 이미 정렬해 보낸 순서를 그대로 지킨다</b> —
	 * 여기서 다시 정렬하면 major 를 숫자로 세우려고 SQL 에 넣은 규칙이 무의미해진다.
	 *
	 * <p>존재하지만 구간에 점이 하나도 없는 패키지는 <b>{@code major} 가 {@code null} 인 빈
	 * 시리즈</b> 하나로 내보낸다. 빼버리면 프론트가 그 이름을 못 찾은 것으로 오해할 여지가
	 * 생긴다. 쪼갤 행이 없으므로 major 를 지어내지 않는다.
	 */
	private static List<TrendResponse.Series> toSeries(List<TrendRow> rows, Existing existing) {
		// 행이 하나라도 온 이름. 그렇지 않은 이름만 빈 시리즈를 받는다.
		Map<SeriesKey, List<TrendResponse.Point>> byKey = new LinkedHashMap<>();
		for (TrendRow r : rows) {
			if (!existing.names().contains(r.name())) continue;
			byKey.computeIfAbsent(new SeriesKey(r.name(), r.major()), k -> new java.util.ArrayList<>())
				.add(new TrendResponse.Point(r.snapshotAt(), r.value()));
		}

		List<TrendResponse.Series> series = new java.util.ArrayList<>();
		for (String name : existing.names()) {
			List<Map.Entry<SeriesKey, List<TrendResponse.Point>>> mine = byKey.entrySet().stream()
				.filter(e -> e.getKey().name().equals(name))
				.toList();

			if (mine.isEmpty()) {
				series.add(new TrendResponse.Series(name, null, List.of()));
				continue;
			}
			for (var e : mine) {
				series.add(new TrendResponse.Series(name, e.getKey().major(), List.copyOf(e.getValue())));
			}
		}
		return List.copyOf(series);
	}

	private record SeriesKey(String name, String major) {
	}

	/* ------------------------------------------------------------------ *
	 * §6 버전 분포
	 * ------------------------------------------------------------------ */

	@Transactional(readOnly = true)
	public VersionShareResponse getVersionShare(PackageNames names, LocalDate snapshotAt) {
		LocalDate latest = repository.findLatestSnapshot();
		Existing existing = existing(names);

		Map<String, List<VersionShareResponse.Slice>> byName = new LinkedHashMap<>();
		for (String name : existing.names()) byName.put(name, new java.util.ArrayList<>());

		for (ShareRow r : repository.findVersionShare(names, snapshotAt)) {
			List<VersionShareResponse.Slice> slices = byName.get(r.name());
			if (slices != null) {
				slices.add(new VersionShareResponse.Slice(r.major(), r.dependents(), r.pct()));
			}
		}

		List<VersionShareResponse.Item> items = byName.entrySet().stream()
			.map(e -> new VersionShareResponse.Item(e.getKey(), List.copyOf(e.getValue())))
			.toList();

		// §6 — 형식은 맞지만 데이터가 없는 날짜는 에러가 아니다. 빈 조각으로 나가고,
		// 기준 시점은 요청한 날짜를 그대로 되돌려준다(화면이 무엇을 물었는지 알아야 한다).
		return VersionShareResponse.of(snapshotAt != null ? snapshotAt : latest, items,
			existing.notFound());
	}

	/* ------------------------------------------------------------------ *
	 * §2.4 검색
	 * ------------------------------------------------------------------ */

	@Transactional(readOnly = true)
	public PackageSearchResponse search(String q, Integer limit) {
		SearchQuery query = SearchQuery.of(q, limit);
		return new PackageSearchResponse(query.q(), repository.searchNames(query.q(), query.limit()));
	}

	/* ------------------------------------------------------------------ *
	 * 공통
	 * ------------------------------------------------------------------ */

	/**
	 * 요청한 이름 중 실제로 존재하는 것과 아닌 것.
	 *
	 * <p>둘 다 <b>요청 순서</b>를 지킨다(0.5). 네 엔드포인트가 이 한 곳을 쓰므로
	 * {@code not_found} 의 기준이 갈라질 수 없다.
	 */
	private Existing existing(PackageNames names) {
		List<String> found = repository.findExistingNames(names);
		List<String> ordered = names.values().stream().filter(found::contains).toList();
		return new Existing(ordered, names.notFoundAmong(ordered));
	}

	private record Existing(List<String> names, List<String> notFound) {
	}
}
