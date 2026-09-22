package com.ssafy.pickage.domain.packages;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.BriefRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.MigrationPairRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.OverviewRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.RemovalReasonRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.ShareRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.SimilarRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TransitionRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;
import com.ssafy.pickage.domain.packages.dto.MigrationPairsResponse;
import com.ssafy.pickage.domain.packages.dto.PackageSearchResponse;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.RemovalReasonsResponse;
import com.ssafy.pickage.domain.packages.dto.SimilarPackagesResponse;
import com.ssafy.pickage.domain.packages.dto.TransitionsResponse;
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
	 * 개요 SQL 은 최신 버전을 {@code CROSS JOIN LATERAL} 로 붙이므로 <b>{@code version} 행이
	 * 하나도 없는 패키지가 결과에서 빠진다.</b> 그러면 존재하는 이름이 {@code not_found} 로 분류되고,
	 * 화면은 "이름을 확인하세요" 를 띄운다 — 사용자는 멀쩡한 이름을 계속 다시 친다.
	 *
	 * <p>실제 DB 로 갈라 확인한 결과, 스냅샷만 없는 경우(consola)는 정상 동작하고
	 * {@code version} 행이 아예 없는 경우만 해당된다. 파이프라인이 {@code package} 를
	 * versions 에서 파생시키므로 실제로는 생기지 않을 것으로 보지만, <b>전제가 깨졌을 때
	 * 조용히 지나가지 않도록</b> 로그를 남긴다. 이 경고가 찍히기 시작하면 SQL 을
	 * {@code LEFT JOIN LATERAL} 로 바꾸고 {@code latest_version} 을 nullable 로 열어야 한다
	 * (프론트 타입도 함께).
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

	/**
	 * <b>기준일 달력이 불규칙해도 응답은 월요일 주간 격자다</b>(S15P21A506-403). DB 의 구간 합계를
	 * 일평균으로 펼쳐 주간 합계로 환산한다({@link WeeklyTrend#downloads}). PDF 도 이 메서드를 부르므로
	 * 화면과 PDF 가 같은 값을 쓴다.
	 */
	@Transactional(readOnly = true)
	public TrendResponse getDownloadsTrend(PackageNames names, LocalDate from, LocalDate to) {
		Existing existing = existing(names);
		return TrendResponse.downloads(
			toSeries(trendRows(from, to,
				window -> WeeklyTrend.downloads(repository.findDownloadsTrend(names, window), window)), existing),
			existing.notFound());
	}

	/** 의존 수도 월요일 격자다. 관측이 없는 주는 양옆을 선형 보간해 잇는다({@link WeeklyTrend#dependents}). */
	@Transactional(readOnly = true)
	public TrendResponse getDependentsTrend(PackageNames names, LocalDate from, LocalDate to) {
		Existing existing = existing(names);
		return TrendResponse.dependents(
			toSeries(trendRows(from, to,
				window -> WeeklyTrend.dependents(repository.findDependentsTrend(names, window), window)), existing),
			existing.notFound());
	}

	/**
	 * 구간을 정하고 조회한다.
	 *
	 * <p>§4 — 끝의 기준은 오늘이 아니라 <b>최신 스냅샷</b>이다.
	 *
	 * <p><b>{@code from} 을 생략하면 최초 스냅샷부터다</b> — 조회 기간 상한(104주)과 기본
	 * 26주를 없애고 "생략 = 보유한 전부" 로 바꿨다(S15P21A506-374). 현장에서 전체 구간을
	 * 보고 싶다는 요구가 반복됐는데, 상한 때문에 이른 {@code from} 을 주면 거절당해
	 * 전체를 볼 방법이 아예 없었다.
	 *
	 * <p><b>스냅샷이 하나도 없으면 구간 자체가 없다</b>({@link SnapshotWindow#of}). 그때는 DB 에
	 * 묻지 않고 빈 행 집합을 돌려준다 — 존재하는 이름은 {@link #toSeries} 를 지나며 빈 시리즈가
	 * 되고, 응답은 200 이다. 적재 전이거나 첫 스냅샷을 기다리는 동안의 <b>정상 상태</b>이지
	 * 장애가 아니다.
	 */
	private List<TrendRow> trendRows(LocalDate from, LocalDate to,
		Function<SnapshotWindow, List<TrendRow>> query) {
		return SnapshotWindow
			.of(from, to, repository.findEarliestSnapshot(), repository.findLatestSnapshot())
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
	 * 기능-03 · UC4 유사 패키지
	 * ------------------------------------------------------------------ */

	/**
	 * 유사 패키지 목록.
	 *
	 * <p><b>조회를 둘로 나눈다.</b> 먼저 순위·점수를 가져오고, 그 이름들로 설명·최신 버전을
	 * 따로 가져와 합친다. 한 쿼리로 조인하면 순위가 뜨는 시점이 정보 조회 속도에 묶인다 —
	 * 지표별로 엔드포인트를 나눈 것과 같은 이유다(명세 §1).
	 *
	 * <p>여기서는 두 조회를 <b>서버 안에서</b> 이어 붙인다. 밖으로 두 번 부르게 하면 화면이
	 * 순서를 관리해야 하고, 후보 20개를 받을 수 있는 공개 엔드포인트를 따로 열어야 한다 —
	 * 그러면 "비교는 최대 3개" 규칙이 새어나간다.
	 */
	@Transactional(readOnly = true)
	public SimilarPackagesResponse getSimilar(SimilarQuery query) {
		// 기준 이름 자체가 없는 것과 후보가 아직 없는 것은 다르다. 앞은 not_found, 뒤는 빈 목록이다.
		PackageNames base = PackageNames.of(List.of(query.name()));
		if (repository.findExistingNames(base).isEmpty()) {
			return SimilarPackagesResponse.of(query.name(), null, List.of(), List.of(query.name()));
		}

		List<SimilarRow> ranked = repository.findSimilar(query.name(), query.limit());
		if (ranked.isEmpty()) {
			return SimilarPackagesResponse.of(query.name(), null, List.of(), List.of());
		}

		// 2단계는 채우기만 한다. **순서의 정답은 1단계다** — DB 는 순서를 보장하지 않으므로
		// 이어 붙이면 순위가 섞인다.
		Map<String, BriefRow> briefs = repository
			.findBriefByNames(ranked.stream().map(SimilarRow::name).toArray(String[]::new))
			.stream()
			.collect(Collectors.toMap(BriefRow::name, Function.identity()));

		List<SimilarPackagesResponse.Candidate> candidates = ranked.stream()
			.map(r -> {
				// 정보가 없어도 후보에서 빼지 않는다. FK 가 걸려 있어 생길 수 없는 일이지만,
				// 생겼을 때 목록에서 조용히 사라지면 "왜 19개지" 를 추적할 수 없다.
				BriefRow b = briefs.get(r.name());
				return new SimilarPackagesResponse.Candidate(
					r.rank(), r.score(), r.name(),
					b == null ? null : b.latestVersion(),
					b == null ? null : b.description());
			})
			.toList();

		return SimilarPackagesResponse.of(query.name(), ranked.getFirst().modelVer(), candidates, List.of());
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
	 * 기능-08 유지·유입·이탈
	 * ------------------------------------------------------------------ */

	/** 표의 {@code CK_DEPENDENT_TRANSITION_KIND} 와 같은 목록·순서. */
	private static final List<String> KINDS = List.of("regular", "peer", "optional");

	/**
	 * 이름과 kind 를 한 키로 잇는 구분자.
	 *
	 * <p>탭은 {@link PackageNames} 의 허용 문자에 없어 이름에 섞일 수 없다. 두 값을 그냥
	 * 이어 붙이면 {@code ("ab", "c")} 와 {@code ("a", "bc")} 가 같은 키가 된다.
	 */
	private static final String KEY_SEPARATOR = "\t";

	/**
	 * 구간 양 끝의 dependent 선언 집합 비교 결과.
	 *
	 * <p><b>0 과 "모름" 을 구분해 내보낸다.</b> 세 갈래다.
	 * <ul>
	 *   <li>{@code not_found} — {@code package} 에 이름 자체가 없다</li>
	 *   <li>{@code OUT_OF_SCOPE} — 이름은 있는데 계산 대상(상위 10만) 밖이다. 실측 2.3%</li>
	 *   <li>{@code NO_DATA} — 대상이고 계산도 됐는데 그 {@code kind} 의 dependent 가 0 이다</li>
	 * </ul>
	 * 셋을 뭉뚱그려 0 으로 주면 화면이 "의존자가 없다" 와 "세어 보지 않았다" 를 구분할 수 없다.
	 *
	 * <p>{@code t1}·{@code t2} 는 <b>표가 가진 값을 읽는다.</b> 서버가 다시 계산하면
	 * 파이프라인이 구간 정의를 바꿨을 때 조용히 어긋난다. 표가 통째로 비어 있을 때만
	 * ({@code NOT_COMPUTED}) 구간에서 만들어 채운다.
	 */
	@Transactional(readOnly = true)
	public TransitionsResponse getTransitions(PackageNames names, TransitionPeriod period) {
		Existing existing = existing(names);
		List<TransitionRow> rows = existing.names().isEmpty()
			? List.of()
			: repository.findTransitions(PackageNames.of(existing.names()), period.code());

		// 조회 결과가 비었다는 것만으로는 "아직 안 만들었다" 와 "이 패키지들이 계산 대상이
		// 아니다" 를 가를 수 없다. 비교 대상 세 개가 모두 대상 밖일 수 있고(실측 2.3%),
		// 그때 NOT_COMPUTED 를 주면 화면이 "준비 중" 을 띄워 사용자는 기다리면 나온다고
		// 믿는다. 영원히 안 나온다.
		String missing = rows.isEmpty() && !repository.hasAnyTransition()
			? TransitionsResponse.NOT_COMPUTED
			: TransitionsResponse.OUT_OF_SCOPE;

		// 요청한 이름 × kind 를 모두 만들고 조회 결과를 얹는다. 행을 빼면 받는 쪽이
		// "조회 실패" 와 "dependent 가 없음" 을 구분할 수 없다 — 파이프라인과 같은 규칙이다.
		Map<String, TransitionRow> byKey = rows.stream()
			.collect(Collectors.toMap(r -> r.name() + KEY_SEPARATOR + r.kind(), Function.identity()));

		List<TransitionsResponse.Series> series = existing.names().stream()
			.flatMap(name -> KINDS.stream().map(kind -> {
				TransitionRow row = byKey.get(name + KEY_SEPARATOR + kind);
				if (row == null) {
					return TransitionsResponse.Series.unknown(name, kind, missing);
				}
				return TransitionsResponse.Series.counted(name, kind, row.retained(),
					row.inflow(), row.inflowNew(), row.outflow(), row.unobserved(),
					row.unobservedRecent(), row.unobservedStale(), row.unobservedDormant());
			}))
			.toList();

		// 표가 가진 값만 쓴다. 읽을 행이 없으면 **모른다고 한다** — 다른 데이터셋의
		// 스냅샷(snapshot 표)으로 대신하면 화면이 실제 계산 구간과 다른 기준일을 표시하고,
		// 사용자는 그 구간의 숫자라고 믿는다. 기능-08-R02 가 요구하는 표시가 거짓이 된다.
		LocalDate t1 = rows.stream().map(TransitionRow::t1).findFirst().orElse(null);
		LocalDate t2 = rows.stream().map(TransitionRow::t2).findFirst().orElse(null);

		return TransitionsResponse.of(period.code(), t1, t2, series, existing.notFound());
	}

	/* ------------------------------------------------------------------ *
	 * 기능-08 이탈 사유 (S15P21A506-396)
	 * ------------------------------------------------------------------ */

	/**
	 * 대체를 동반한 이탈과 아무것도 안 넣은 이탈.
	 *
	 * <p><b>{@link #getTransitions} 와 단위가 다르다.</b> 저쪽은 패키지 수를 세고 이쪽은 전이
	 * 건수를 센다. 그래서 응답을 따로 내고 {@code unit} 을 값으로 싣는다.
	 *
	 * <p><b>네 갈래를 가른다.</b> 위 세 갈래에 하나가 더 붙는다.
	 * <ul>
	 *   <li>{@code not_found} — {@code package} 에 이름 자체가 없다</li>
	 *   <li>{@code OUT_OF_SCOPE} — 이름은 있는데 유지·유입·이탈 대상이 아니다</li>
	 *   <li>{@code NO_DATA} — 대상인데 이 구간에 <b>한 번도 빠진 적이 없다.</b> 0 이 맞다</li>
	 *   <li>{@code NOT_COMPUTED} — 이탈 사유 회차가 아직 적재되지 않았다</li>
	 * </ul>
	 *
	 * <p>세 번째가 이 지표에서 특히 중요하다 — 대상 97,745개 중 <b>57,201개(58.5%)</b>가
	 * 거기 해당한다. 적재기가 {@code removals > 0} 인 행만 넣으므로 표에 행이 없는 것이
	 * 곧 "세어 보니 없었다" 이고, 조회가 {@code dependent_transition} 을 함께 보는 이유가
	 * 그것이다.
	 *
	 * <p>네 번째를 {@link PackageQueryRepository#hasAnyRemovalReason()} 로 따로 확인한다.
	 * 유지·유입·이탈만 적재된 상태에서는 조회가 모든 대상에 행을 돌려주되 수가 전부
	 * {@code null} 이라, 이 검사가 없으면 <b>적재를 안 했을 뿐인데 "한 번도 버려진 적
	 * 없습니다" 를 띄운다.</b>
	 */
	@Transactional(readOnly = true)
	public RemovalReasonsResponse getRemovalReasons(PackageNames names, TransitionPeriod period) {
		Existing existing = existing(names);
		List<RemovalReasonRow> rows = existing.names().isEmpty()
			? List.of()
			: repository.findRemovalReasons(PackageNames.of(existing.names()), period.code());

		// **행이 왔는가가 곧 범위 안인가다.** 조회가 범위 표를 JOIN 하므로 행이 없다는 것은
		// "대상이 아니다" 한 가지 뜻뿐이고, 이탈 사유 회차를 올렸는지와는 무관하다.
		// 여기에 적재 상태를 섞으면 표가 비어 있는 동안 대상 밖 패키지가 NOT_COMPUTED 로
		// 나가 화면이 "집계 대기 중" 을 띄운다 — 영원히 안 나올 값인데도.
		//
		// getTransitions 가 hasAnyTransition() 으로 둘을 가르는 것과 다른 상황이다.
		// 그쪽은 행의 출처가 dependent_transition 자신이라 "행 없음" 이 두 뜻을 겸한다.
		Map<String, RemovalReasonRow> byName = rows.stream()
			.collect(Collectors.toMap(RemovalReasonRow::name, Function.identity()));

		// 회차 적재 여부는 **범위 안인데 수가 빈 행**에만 필요하다. 그 상태가 "아무도 안
		// 뺐다"(0)인지 "아직 안 올렸다"(모름)인지는 표를 봐야 알 수 있다.
		//
		// 한 행이라도 수가 들어 있으면 표가 빈 게 아님이 자명하므로 묻지 않는다. 정상
		// 경로에 질의를 더하지 않으려는 것이고, hasAnyTransition() 을 조회 결과가 빌 때만
		// 부르는 것과 같은 규칙이다.
		boolean loaded = rows.stream().anyMatch(RemovalReasonRow::counted)
			|| repository.hasAnyRemovalReason();

		List<RemovalReasonsResponse.Series> series = existing.names().stream()
			.map(name -> {
				RemovalReasonRow row = byName.get(name);
				if (row == null) {
					return RemovalReasonsResponse.Series.unknown(name,
						RemovalReasonsResponse.OUT_OF_SCOPE);
				}
				if (!row.counted()) {
					// 범위는 맞는데 수가 없다. 회차가 없으면 모름, 있으면 0 이다.
					return loaded ? RemovalReasonsResponse.Series.none(name)
						: RemovalReasonsResponse.Series.unknown(name,
							RemovalReasonsResponse.NOT_COMPUTED);
				}
				return RemovalReasonsResponse.Series.counted(name, row.removals(),
					row.noReplacement(), row.withReplacement(), row.dependents());
			})
			.toList();

		// transitions 와 같은 규칙 — 표가 가진 값만 쓴다. 읽을 행이 없으면 모른다고 한다.
		// 두 응답의 t1·t2 가 같은 값인 것은 적재기가 같은 표에서 가져오기 때문이다.
		LocalDate t1 = rows.stream().map(RemovalReasonRow::t1).findFirst().orElse(null);
		LocalDate t2 = rows.stream().map(RemovalReasonRow::t2).findFirst().orElse(null);

		return RemovalReasonsResponse.of(period.code(), t1, t2, series, existing.notFound());
	}

	/**
	 * 확장-02 — 관측된 교체 흐름. "X 를 떠난 사람들은 어디로 갔나".
	 *
	 * <h2>여기서만 접는 이유 — 명세 0.7 과 어긋나 보이는 자리</h2>
	 *
	 * <p>"집계는 DB 에서 끝낸다" 가 이 서비스의 규칙인데, 상위 5와 {@code etc} 를 자바에서
	 * 만든다. <b>두 규칙이 충돌해서 고른 것이다.</b> S15P21A506-211 결정 4는 하한을 한 곳에만
	 * 두라고 요구한다 — 전체 흐름 · focus · 최대 6개 방향이 같은 값을 봐야 한다. SQL 에도
	 * 하한을 적으면 {@link MigrationPairFilter} 와 두 벌이 되고, 한쪽만 고쳐져도 양쪽 다
	 * 그럴듯해서 알아채지 못한다.
	 *
	 * <p>0.7 이 막으려던 것은 <b>같은 계산을 두 곳이 하는 것</b>인데 여기서는 한 곳뿐이다.
	 * 그리고 옮기는 행이 수천을 넘지 않는다(표 전체가 23,140행).
	 *
	 * <h2>네 상태를 가르는 순서</h2>
	 *
	 * <ol>
	 * <li>행이 하나라도 왔다 → 통과한 것이 있으면 {@code COMPLETE}, 없으면
	 *     {@code INSUFFICIENT_EVIDENCE}</li>
	 * <li>행이 없다 → 그 종류가 적재됐으면 {@code NO_DATA}(관측이 없다), 아니면
	 *     {@code NOT_COMPUTED}(아직 안 올렸다)</li>
	 * </ol>
	 *
	 * <p>둘째 줄이 {@code getRemovalReasons} 와 다르다. 그쪽은 조회가 범위 표를 조인해서
	 * "행 없음" 이 곧 "대상 밖" 이지만, 이 표에는 범위 개념이 없다 — 이동이 관측된 패키지만
	 * 행을 가진다. 그래서 {@code getTransitions} 처럼 적재 여부를 따로 묻는다.
	 */
	public MigrationPairsResponse getMigrationPairs(PackageNames names, DependencyKind kind) {
		Existing existing = existing(names);
		List<MigrationPairRow> rows = existing.names().isEmpty()
			? List.of()
			: repository.findMigrationPairs(PackageNames.of(existing.names()), kind.code());

		Map<String, List<MigrationPairRow>> byName = rows.stream()
			.collect(Collectors.groupingBy(MigrationPairRow::fromName, LinkedHashMap::new,
				Collectors.toList()));

		// 적재 여부는 **행이 하나도 없는 이름이 있을 때만** 묻는다. 한 이름이라도 행이 있으면
		// 그 종류가 올라와 있다는 뜻이라 물을 필요가 없다. getRemovalReasons 와 같은 규칙이다.
		boolean loaded = !rows.isEmpty()
			|| existing.names().isEmpty()
			|| repository.hasAnyMigrationPair(kind.code());

		List<MigrationPairsResponse.Series> series = existing.names().stream()
			.map(name -> {
				List<MigrationPairRow> pairs = byName.get(name);
				if (pairs == null || pairs.isEmpty()) {
					return loaded
						? MigrationPairsResponse.Series.of(name, null, List.of(), null, 0,
							MigrationPairsResponse.NO_DATA)
						: MigrationPairsResponse.Series.unknown(name,
							MigrationPairsResponse.NOT_COMPUTED);
				}
				return fold(name, pairs);
			})
			.toList();

		return MigrationPairsResponse.of(kind, series, existing.notFound());
	}

	/**
	 * 한 패키지의 쌍을 "상위 몇 개 + 그 밖" 으로 접는다.
	 *
	 * <p>조회가 이미 {@code share_pm_pct} 내림차순으로 정렬해 주므로 여기서 다시 정렬하지
	 * 않는다 — 정렬 기준이 두 곳에 있으면 갈라진다.
	 *
	 * <p><b>접는 칸에 필터 미달 쌍도 넣는다.</b> 그래야 상위와 {@code etc} 의 합이 이
	 * 패키지의 관측된 이동 전부가 되어 차트가 100% 를 이룬다. 다만 몇 개가 근거 부족으로
	 * 접혔는지는 따로 세어 준다 — 화면이 "잡음이라 접었다" 와 "여섯 번째부터라 접었다" 를
	 * 구분해 말할 수 있어야 한다.
	 */
	private MigrationPairsResponse.Series fold(String name, List<MigrationPairRow> pairs) {
		List<MigrationPairRow> passed = pairs.stream()
			.filter(row -> MigrationPairFilter.passesDefault(row.votes(), row.publisherMonths()))
			.toList();

		List<MigrationPairRow> top = passed.stream()
			.limit(MigrationPairFilter.TOP_DESTINATIONS)
			.toList();

		List<MigrationPairsResponse.Destination> destinations = top.stream()
			.map(PackageService::destination)
			.toList();

		// 남은 것 = 전체 - 세운 것. 필터에 못 미친 쌍이 여기 포함된다.
		// 도착지 이름으로 빼는 것은 PK 가 (출발, 종류, 도착이름) 이라 한 응답 안에서 이름이
		// 곧 키이기 때문이다. 행 자체로 비교하면 BigDecimal 의 equals 가 소수 자릿수까지 보는
		// 것에 기대게 된다.
		Set<String> taken = top.stream().map(MigrationPairRow::toName)
			.collect(Collectors.toSet());
		List<MigrationPairRow> rest = pairs.stream()
			.filter(row -> !taken.contains(row.toName()))
			.toList();

		MigrationPairsResponse.Etc etc = rest.isEmpty() ? null
			: new MigrationPairsResponse.Etc(
				rest.size(),
				rest.stream().map(MigrationPairRow::sharePmPct)
					.reduce(BigDecimal.ZERO, BigDecimal::add),
				(int)rest.stream()
					.filter(row -> !MigrationPairFilter.passesDefault(row.votes(),
						row.publisherMonths()))
					.count());

		// 기준일은 그 종류의 모든 행이 같은 값이다(적재기가 원천마다 하나씩 붙인다).
		// 그래도 서버가 상수로 적지 않고 표에서 읽는다 — 원천을 다시 뽑으면 날짜가 바뀐다.
		LocalDate snapshotAt = pairs.get(0).snapshotAt();

		String status = passed.isEmpty()
			? MigrationPairsResponse.INSUFFICIENT_EVIDENCE
			: MigrationPairsResponse.COMPLETE;

		return MigrationPairsResponse.Series.of(name, snapshotAt, destinations, etc, pairs.size(),
			status);
	}

	private static MigrationPairsResponse.Destination destination(MigrationPairRow row) {
		return new MigrationPairsResponse.Destination(
			row.toName(), row.votes(), row.coEvents(), row.publisherMonths(), row.dependents(),
			row.lift(), row.sharePmPct(), row.sharePct(),
			MigrationPairFilter.grade(row.votes(), row.publisherMonths(), row.aPct(),
				row.sharePct()),
			row.bidirectional(), row.firstSeen(), row.lastSeen());
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
