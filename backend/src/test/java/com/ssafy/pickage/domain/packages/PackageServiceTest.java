package com.ssafy.pickage.domain.packages;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.BriefRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.OverviewRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.ShareRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.SimilarRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;

/**
 * 서비스 계층 규칙.
 *
 * <p>DB 없이 도는 시험이다. SQL 자체(윈도 함수·조인)는 여기서 검증할 수 없고 —
 * 그건 실제 Postgres 가 필요하다 — 여기서는 <b>SQL 결과를 응답으로 옮기는 규칙</b>만 본다:
 * 요청 순서 재배열, {@code not_found} 계산, {@code null} 보존, 시간대 변환.
 *
 * <p>Mockito 를 쓰지 않고 손으로 만든 대역을 쓴다. 조회 두 개뿐이라 프레임워크가 주는 이득보다
 * "이 시험이 무엇을 가정하는지" 가 코드에 그대로 보이는 편이 낫다.
 */
class PackageServiceTest {

	private static final LocalDate SNAPSHOT = LocalDate.parse("2026-08-31");

	/** 이름 → 행. 넣은 순서와 무관하게 돌려주도록 일부러 뒤집어 반환한다. */
	private static PackageService serviceOf(List<OverviewRow> rows, List<String> existing) {
		PackageQueryRepository fake = new PackageQueryRepository(null) {
			@Override
			public LocalDate findLatestSnapshot() {
				return SNAPSHOT;
			}

			@Override
			public List<OverviewRow> findOverview(PackageNames names) {
				// DB 는 순서를 보장하지 않는다. 그 사실을 시험이 실제로 밟도록 뒤집어 준다.
				return rows.reversed();
			}

			@Override
			public List<String> findExistingNames(PackageNames names) {
				return existing;
			}
		};
		return new PackageService(fake);
	}

	private static OverviewRow row(String name) {
		return new OverviewRow(name, "https://github.com/x/" + name, "1.0.0",
			LocalDateTime.parse("2026-07-14T09:02:11"), "desc", List.of("MIT"),
			false, 100L, 10, 1, 5, -1);
	}

	@Test
	@DisplayName("0.5 — items 는 DB 순서가 아니라 요청한 이름 순서로 나간다")
	void ordersByRequest() {
		PackageService service = serviceOf(List.of(row("express"), row("fastify"), row("koa")), List.of());

		var res = service.getOverview(PackageNames.of(List.of("express", "fastify", "koa")));

		assertEquals(List.of("express", "fastify", "koa"),
			res.items().stream().map(PackagesOverviewResponse.Item::name).toList());
	}

	@Test
	@DisplayName("0.2 — 일부를 못 찾아도 나머지는 그대로 나가고 not_found 에 담긴다")
	void partialFailure() {
		PackageService service = serviceOf(List.of(row("express")), List.of("express"));

		var res = service.getOverview(PackageNames.of(List.of("express", "expres", "lodahs")));

		assertEquals(List.of("express"), res.items().stream().map(PackagesOverviewResponse.Item::name).toList());
		// not_found 도 요청 순서를 지킨다
		assertEquals(List.of("expres", "lodahs"), res.notFound());
	}

	@Test
	@DisplayName("0.2 — 전부 못 찾아도 items 는 빈 배열이다 (404 가 아니다)")
	void allMissing() {
		PackageService service = serviceOf(List.of(), List.of());

		var res = service.getOverview(PackageNames.of(List.of("nope-a", "nope-b")));

		assertTrue(res.items().isEmpty());
		assertEquals(List.of("nope-a", "nope-b"), res.notFound());
		assertEquals(SNAPSHOT, res.snapshotAt());
	}

	@Test
	@DisplayName("0.5 — 스냅샷 미수신은 not_found 가 아니라 items 안의 null 이다")
	void pendingMetricsStayInItems() {
		OverviewRow pending = new OverviewRow("consola", "https://github.com/unjs/consola", "3.4.2",
			LocalDateTime.parse("2026-07-30T21:02:00"), "Elegant Console Logger", List.of("MIT"),
			false, null, null, null, null, null);
		PackageService service = serviceOf(List.of(pending), List.of("consola"));

		var res = service.getOverview(PackageNames.of(List.of("consola")));

		assertTrue(res.notFound().isEmpty(), "존재하는 패키지가 not_found 로 가면 안 된다");
		var item = res.items().getFirst();
		// 0 으로 채우면 "아무도 안 받는 패키지" 처럼 보인다. null 이어야 화면이 "집계 대기" 로 그린다.
		assertNull(item.downloads());
		assertNull(item.stars());
		assertNull(item.starsDelta());
		// 메타데이터는 그대로 있다
		assertEquals("3.4.2", item.latestVersion());
	}

	/**
	 * 위 시험(스냅샷 미수신)과 <b>결과가 갈리는 경우</b>다.
	 *
	 * <p>실제 Postgres 로 둘을 갈라 확인했다.
	 * <pre>
	 *   version 있음 + package_snapshot 없음 → items 에 남고 지표만 null  (명세 0.5 대로)
	 *   version 자체가 없음                  → 결과에서 빠져 not_found 로  (명세와 어긋남)
	 * </pre>
	 *
	 * <p>뒤쪽은 개요 SQL 이 {@code latest_ver} 를 INNER JOIN 하기 때문이다. 파이프라인이
	 * {@code package} 를 versions 에서 파생시키므로 실제로는 생기지 않을 것으로 보지만,
	 * <b>지금 동작을 여기 못 박아 둔다.</b> 누군가 LEFT JOIN 으로 바꾸면 이 시험이 깨지고,
	 * 그때 프론트의 {@code latest_version: string} 타입도 nullable 로 함께 열어야 한다는 것을
	 * 알게 된다. 시험이 깨지는 것이 이 경우의 목적이다.
	 */
	@Test
	@DisplayName("version 행이 없는 패키지는 not_found 로 간다 (현재 동작 — 바꾸려면 프론트 타입도 함께)")
	void versionlessPackageFallsIntoNotFound() {
		// 조회 결과에는 없지만 package 테이블에는 있는 이름
		PackageService service = serviceOf(List.of(row("express")), List.of("express", "ghost-pkg"));

		var res = service.getOverview(PackageNames.of(List.of("express", "ghost-pkg")));

		assertEquals(List.of("express"), res.items().stream().map(PackagesOverviewResponse.Item::name).toList());
		assertEquals(List.of("ghost-pkg"), res.notFound());
		// 서비스는 이 경우를 감지해 경고를 남긴다 (PackageService#warnIfSilentlyDropped).
		// 로그를 단언하지는 않는다 — 단언하면 문구를 못 고치게 된다.
	}

	@Test
	@DisplayName("published_at 은 UTC 로 나간다 — 시스템 시간대(KST)로 해석하면 9시간이 밀린다")
	void publishedAtIsUtc() {
		PackageService service = serviceOf(List.of(row("express")), List.of());

		var res = service.getOverview(PackageNames.of(List.of("express")));

		assertEquals("2026-07-14T09:02:11Z", res.items().getFirst().publishedAt().toString());
	}

	@Test
	@DisplayName("0.1 — 중복은 제거되고, 응답도 한 번만 나온다")
	void dedupes() {
		PackageService service = serviceOf(List.of(row("express"), row("pino")), List.of());

		var res = service.getOverview(PackageNames.of(List.of("pino", "express", "pino")));

		assertEquals(List.of("pino", "express"),
			res.items().stream().map(PackagesOverviewResponse.Item::name).toList());
	}

	/* ------------------------------------------------------------------ *
	 * S15P21A506-298 — 스냅샷이 없거나 모자란 구간
	 * ------------------------------------------------------------------ */

	/**
	 * 추이·분포 시험용 대역.
	 *
	 * <p>두 가지를 의도적으로 심어 두었다.
	 *
	 * <ul>
	 *   <li><b>조회 메서드가 행을 갖고 있다.</b> 구간이 없을 때 그 행이 응답에 나오면
	 *       서비스가 DB 를 물었다는 뜻이라 시험이 깨진다.
	 *   <li><b>넘겨받은 구간을 {@link #queried} 에 기록한다.</b> 구간은 응답에 실리지 않아
	 *       밖에서 볼 수 없다. 기본 구간이 최신 스냅샷 기준으로 잡히는지 확인하려면
	 *       저장소가 무엇을 받았는지 봐야 한다.
	 * </ul>
	 */
	private static final class FakeRepository extends PackageQueryRepository {

		private final LocalDate latest;
		private final List<String> existing;
		private final List<TrendRow> rows;

		/** 서비스가 실제로 조회한 구간. 비어 있으면 DB 를 묻지 않았다는 뜻이다. */
		private final List<SnapshotWindow> queried = new ArrayList<>();

		private FakeRepository(LocalDate latest, List<String> existing, List<TrendRow> rows) {
			super(null);
			this.latest = latest;
			this.existing = existing;
			this.rows = rows;
		}

		@Override
		public LocalDate findLatestSnapshot() {
			return latest;
		}

		@Override
		public List<String> findExistingNames(PackageNames names) {
			return existing;
		}

		@Override
		public List<OverviewRow> findOverview(PackageNames names) {
			return List.of();
		}

		@Override
		public List<TrendRow> findDownloadsTrend(PackageNames names, SnapshotWindow window) {
			queried.add(window);
			return rows;
		}

		@Override
		public List<TrendRow> findDependentsTrend(PackageNames names, SnapshotWindow window) {
			queried.add(window);
			return rows;
		}

		@Override
		public List<ShareRow> findVersionShare(PackageNames names, LocalDate snapshotAt) {
			return List.of();
		}
	}

	/* ------------------------------------------------------------------ *
	 * 기능-03 · UC4 유사 패키지
	 * ------------------------------------------------------------------ */

	/**
	 * 유사 패키지 대역.
	 *
	 * <p><b>정보 조회를 일부러 뒤집어 돌려준다.</b> 두 조회를 이어 붙이면 순위가 섞이는데,
	 * DB 가 우연히 순위대로 돌려주면 그 버그가 시험을 통과한다.
	 */
	private static final class FakeSimilarRepository extends PackageQueryRepository {

		private final List<String> existing;
		private final List<SimilarRow> ranked;
		private final List<BriefRow> briefs;

		/** 정보 조회가 실제로 받은 이름들. 상한 3개가 새어 들어오지 않았는지 본다. */
		private String[] briefArgument;

		private FakeSimilarRepository(List<String> existing, List<SimilarRow> ranked, List<BriefRow> briefs) {
			super(null);
			this.existing = existing;
			this.ranked = ranked;
			this.briefs = briefs;
		}

		@Override
		public List<String> findExistingNames(PackageNames names) {
			return existing;
		}

		@Override
		public List<SimilarRow> findSimilar(String name, int limit) {
			return ranked;
		}

		@Override
		public List<BriefRow> findBriefByNames(String[] names) {
			briefArgument = names;
			return briefs.reversed();
		}
	}

	private static SimilarRow rank(int n, String name) {
		return new SimilarRow(name, n, 0.94 - n * 0.035, "mock-v1-20260831");
	}

	private static BriefRow brief(String name) {
		return new BriefRow(name, "1.0.0", name + " 설명");
	}

	@Test
	@DisplayName("UC4 — 후보는 rank 순서로 나가고, 정보 조회 순서에 흔들리지 않는다")
	void similarKeepsRankOrder() {
		var fake = new FakeSimilarRepository(
			List.of("express"),
			List.of(rank(1, "koa"), rank(2, "fastify"), rank(3, "hapi")),
			List.of(brief("koa"), brief("fastify"), brief("hapi")));
		PackageService service = new PackageService(fake);

		var res = service.getSimilar(SimilarQuery.of("express", null));

		assertEquals(List.of("koa", "fastify", "hapi"),
			res.candidates().stream().map(c -> c.name()).toList());
		assertEquals(List.of(1, 2, 3), res.candidates().stream().map(c -> c.rank()).toList());
		assertEquals("koa 설명", res.candidates().getFirst().description());
		assertEquals("mock-v1-20260831", res.modelVer());
		assertEquals("COMPLETE", res.dataStatus());
	}

	/**
	 * 정보 조회에 넘기는 이름은 <b>사용자 입력이 아니라 서버가 만든 후보 목록</b>이다.
	 * {@link PackageNames} 의 3개 상한이 여기 걸리면 후보 20개를 받을 수 없다.
	 */
	@Test
	@DisplayName("UC4 — 후보가 3개를 넘어도 정보 조회가 막히지 않는다")
	void briefLookupIsNotCappedAtThree() {
		List<SimilarRow> many = List.of(rank(1, "a"), rank(2, "b"), rank(3, "c"), rank(4, "d"), rank(5, "e"));
		var fake = new FakeSimilarRepository(List.of("express"), many,
			many.stream().map(r -> brief(r.name())).toList());
		PackageService service = new PackageService(fake);

		var res = service.getSimilar(SimilarQuery.of("express", null));

		assertEquals(5, res.candidates().size());
		assertEquals(5, fake.briefArgument.length);
	}

	@Test
	@DisplayName("UC4 — 후보가 아직 없는 것은 not_found 가 아니라 NO_DATA 다")
	void emptyCandidatesAreNotNotFound() {
		PackageService service = new PackageService(
			new FakeSimilarRepository(List.of("express"), List.of(), List.of()));

		var res = service.getSimilar(SimilarQuery.of("express", null));

		assertTrue(res.candidates().isEmpty());
		assertTrue(res.notFound().isEmpty(), "존재하는 이름이 not_found 로 가면 안 된다");
		assertEquals("NO_DATA", res.dataStatus());
		// 만든 모델이 없으므로 버전을 지어내지 않는다.
		assertNull(res.modelVer());
	}

	@Test
	@DisplayName("UC4 — 기준 이름 자체가 없으면 not_found 에 담긴다")
	void unknownBaseGoesToNotFound() {
		PackageService service = new PackageService(
			new FakeSimilarRepository(List.of(), List.of(), List.of()));

		var res = service.getSimilar(SimilarQuery.of("nope-pkg", null));

		assertEquals(List.of("nope-pkg"), res.notFound());
		assertTrue(res.candidates().isEmpty());
		assertEquals("nope-pkg", res.base(), "화면이 무엇을 물었는지 알아야 한다");
	}

	/**
	 * FK 가 걸려 있어 실제로는 생기지 않지만, 생겼을 때 <b>목록에서 조용히 사라지면</b>
	 * "왜 19개지" 를 추적할 수 없다. 후보는 남기고 정보만 비운다.
	 */
	@Test
	@DisplayName("UC4 — 정보를 못 찾은 후보도 목록에서 빠지지 않는다")
	void candidateWithoutBriefStays() {
		var fake = new FakeSimilarRepository(
			List.of("express"),
			List.of(rank(1, "koa"), rank(2, "ghost")),
			List.of(brief("koa")));
		PackageService service = new PackageService(fake);

		var res = service.getSimilar(SimilarQuery.of("express", null));

		assertEquals(2, res.candidates().size());
		var ghost = res.candidates().get(1);
		assertEquals("ghost", ghost.name());
		assertNull(ghost.latestVersion());
		assertNull(ghost.description());
	}

	private static final List<TrendRow> ONE_ROW =
		List.of(new TrendRow("express", null, SNAPSHOT, 100L));

	/**
	 * 추이 두 개는 <b>같은 규칙</b>을 쓴다. 한 시험에서 둘 다 부른다 — 나눠 두면 한쪽만
	 * 되돌아갔을 때 나머지 하나가 계속 초록불이라 그 사실이 가려진다.
	 */
	@Test
	@DisplayName("298 — 스냅샷이 하나도 없으면 추이 둘 다 500 이 아니라 빈 시리즈다")
	void emptySnapshotYieldsEmptyTrends() {
		FakeRepository fake = new FakeRepository(null, List.of("express"), ONE_ROW);
		PackageService service = new PackageService(fake);
		PackageNames names = PackageNames.of(List.of("express"));

		var downloads = service.getDownloadsTrend(names, null, null);
		var dependents = service.getDependentsTrend(names, null, null);

		for (var res : List.of(downloads, dependents)) {
			assertEquals(1, res.series().size());
			assertEquals("express", res.series().getFirst().name());
			assertTrue(res.series().getFirst().points().isEmpty());
			// 이름이 없는 것과 자료가 없는 것은 다르다. 존재하는 이름을 not_found 로 보내면
			// 화면이 "이름을 확인하세요" 를 띄우고, 사용자는 멀쩡한 이름을 계속 다시 친다.
			assertTrue(res.notFound().isEmpty());
		}
		assertTrue(fake.queried.isEmpty(), "구간이 없으면 DB 를 묻지 않는다");
	}

	@Test
	@DisplayName("298 — 스냅샷이 없으면 버전 분포는 snapshot_at 이 null 이고 조각이 비어 있다")
	void emptySnapshotYieldsEmptyVersionShare() {
		PackageService service = new PackageService(
			new FakeRepository(null, List.of("express"), List.of()));

		var res = service.getVersionShare(PackageNames.of(List.of("express")), null);

		// 날짜를 지어내지 않는다. 요청도 없었고 기준일도 없으므로 null 이 사실이다.
		assertNull(res.snapshotAt());
		assertEquals(1, res.items().size());
		assertTrue(res.items().getFirst().slices().isEmpty());
		assertTrue(res.notFound().isEmpty());
	}

	@Test
	@DisplayName("298 — 스냅샷이 없어도 from·to 를 명시하면 그 구간 그대로 조회한다")
	void explicitWindowSurvivesEmptySnapshot() {
		FakeRepository fake = new FakeRepository(null, List.of("express"), ONE_ROW);
		PackageService service = new PackageService(fake);

		var res = service.getDownloadsTrend(PackageNames.of(List.of("express")),
			LocalDate.parse("2026-08-01"), LocalDate.parse("2026-08-31"));

		// 사용자가 물어본 구간을 서버가 지어내거나 비우지 않는다.
		assertEquals(1, fake.queried.size());
		assertEquals(new SnapshotWindow(LocalDate.parse("2026-08-01"), LocalDate.parse("2026-08-31")),
			fake.queried.getFirst());
		assertEquals(1, res.series().getFirst().points().size());
	}

	/**
	 * §4 — 기본 구간은 <b>오늘이 아니라 최신 스냅샷</b>에서 거꾸로 센다. 오늘을 기준으로 세면
	 * 아직 만들어지지 않은 주가 구간에 들어가 매번 다른 길이의 시리즈가 나온다.
	 *
	 * <p>스냅샷이 하나뿐이어도 구간은 성립한다 — 26주를 채울 자료가 없는 것과 구간이 없는 것은
	 * 다르다. 앞은 점 하나짜리 정상 응답이다.
	 */
	@Test
	@DisplayName("298 — 기본 구간은 최신 스냅샷에서 26주를 거꾸로 센다 (양 끝 포함)")
	void defaultWindowCountsBackFromLatestSnapshot() {
		FakeRepository fake = new FakeRepository(SNAPSHOT, List.of("express"), ONE_ROW);
		PackageService service = new PackageService(fake);

		var res = service.getDownloadsTrend(PackageNames.of(List.of("express")), null, null);

		assertEquals(new SnapshotWindow(SNAPSHOT.minusWeeks(25), SNAPSHOT), fake.queried.getFirst());
		assertEquals(1, res.series().getFirst().points().size());
	}

	/* ------------------------------------------------------------------ *
	 * §5 — major 별 쪼개기
	 * ------------------------------------------------------------------ */

	/**
	 * major 정렬은 <b>SQL 이 한다</b>(문자열 정렬이면 {@code '1' < '10' < '2'} 가 되므로
	 * 숫자로 세운다). 서비스가 다시 정렬하면 그 규칙이 무의미해지므로, 받은 순서를 그대로
	 * 지키는지 본다 — 일부러 숫자 순서로는 어긋난 순서를 넣지 않고, SQL 이 준 순서를 흉내 낸다.
	 */
	@Test
	@DisplayName("§5 — 같은 이름이 major 개수만큼 갈라지고, SQL 이 준 순서를 그대로 지킨다")
	void dependentsSplitByMajorKeepsSqlOrder() {
		List<TrendRow> rows = List.of(
			new TrendRow("express", "4", SNAPSHOT, 700L),
			new TrendRow("express", "5", SNAPSHOT, 300L),
			new TrendRow("express", "10", SNAPSHOT, 50L),
			new TrendRow("koa", "2", SNAPSHOT, 120L));
		PackageService service = new PackageService(
			new FakeRepository(SNAPSHOT, List.of("express", "koa"), rows));

		var res = service.getDependentsTrend(PackageNames.of(List.of("express", "koa")), null, null);

		assertEquals(List.of("express", "express", "express", "koa"),
			res.series().stream().map(s -> s.name()).toList());
		assertEquals(List.of("4", "5", "10", "2"),
			res.series().stream().map(s -> s.major()).toList());
		// 버전별 합산이라는 사실은 major 로 접어도 그대로다.
		assertEquals(Boolean.TRUE, res.sumOverVersions());
	}

	/**
	 * <b>이 시험이 회귀를 막는 지점이다.</b> major 로 쪼갠 뒤 전부 더한 값이 쪼개기 전의
	 * 합계와 달라지면 어딘가에서 행이 새거나 겹친 것이다. 화면의 {@code TOTAL} 이 그 덧셈을
	 * 그대로 하므로, 여기가 어긋나면 사용자가 보는 숫자가 바뀐다.
	 */
	@Test
	@DisplayName("§5 — major 별 값을 날짜마다 더하면 쪼개기 전 합계와 같다")
	void majorSlicesSumBackToTotal() {
		LocalDate week1 = SNAPSHOT.minusWeeks(1);
		List<TrendRow> rows = List.of(
			new TrendRow("express", "4", week1, 900L),
			new TrendRow("express", "4", SNAPSHOT, 700L),
			new TrendRow("express", "5", week1, 100L),
			new TrendRow("express", "5", SNAPSHOT, 300L));
		PackageService service = new PackageService(
			new FakeRepository(SNAPSHOT, List.of("express"), rows));

		var res = service.getDependentsTrend(PackageNames.of(List.of("express")), null, null);

		Map<LocalDate, Long> total = new LinkedHashMap<>();
		for (var s : res.series()) {
			for (var p : s.points()) total.merge(p.snapshotAt(), p.value(), Long::sum);
		}
		assertEquals(1000L, total.get(week1));
		assertEquals(1000L, total.get(SNAPSHOT));
	}

	/**
	 * 존재하는 이름인데 구간에 행이 하나도 없으면 쪼갤 것이 없다. major 를 지어내지 않고
	 * {@code null} 로 둔다 — 화면은 이것을 "자료 없음" 으로 읽고, {@code not_found}(이름 자체가
	 * 없음)와 구분한다.
	 */
	@Test
	@DisplayName("§5 — 점이 없는 패키지는 major 가 null 인 빈 시리즈 하나다")
	void packageWithoutRowsGetsSingleNullMajorSeries() {
		PackageService service = new PackageService(
			new FakeRepository(SNAPSHOT, List.of("express", "consola"),
				List.of(new TrendRow("express", "4", SNAPSHOT, 700L))));

		var res = service.getDependentsTrend(PackageNames.of(List.of("express", "consola")), null, null);

		assertEquals(2, res.series().size());
		var consola = res.series().get(1);
		assertEquals("consola", consola.name());
		assertNull(consola.major(), "쪼갤 행이 없으면 major 를 지어내지 않는다");
		assertTrue(consola.points().isEmpty());
		assertTrue(res.notFound().isEmpty(), "존재하는 이름이 not_found 로 가면 안 된다");
	}

	@Test
	@DisplayName("§4 — downloads 는 버전으로 쪼갤 수 없어 major 가 없다")
	void downloadsHasNoMajor() {
		PackageService service = new PackageService(
			new FakeRepository(SNAPSHOT, List.of("express"), ONE_ROW));

		var res = service.getDownloadsTrend(PackageNames.of(List.of("express")), null, null);

		assertEquals(1, res.series().size());
		assertNull(res.series().getFirst().major());
		assertNull(res.sumOverVersions(), "downloads 에는 이 꼬리표가 붙지 않는다");
	}

	@Test
	@DisplayName("298 — 적재 전 개요의 snapshot_at 은 null 이다 (날짜를 지어내지 않는다)")
	void overviewSnapshotAtIsNullBeforeIngest() {
		PackageService service = new PackageService(new FakeRepository(null, List.of(), List.of()));

		var res = service.getOverview(PackageNames.of(List.of("express")));

		assertNull(res.snapshotAt());
		assertTrue(res.items().isEmpty());
	}
}
