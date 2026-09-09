package com.ssafy.pickage.domain.packages;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.OverviewRow;
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
}
