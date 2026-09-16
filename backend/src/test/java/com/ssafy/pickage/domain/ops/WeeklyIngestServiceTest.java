package com.ssafy.pickage.domain.ops;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 운영 API 의 규칙 시험. MinIO 없이 돈다.
 *
 * <p>여기서 덮는 것은 <b>저장소가 아니라 판단</b>이다 — 어느 주차를 거부하는가, 객체가 없는
 * 주를 어떻게 보여 주는가, 우편함만 있을 때 무엇으로 치는가. 저장소 왕복 자체는
 * 통합 시험이 본다.
 */
class WeeklyIngestServiceTest {

	/** 2026-09-15 화요일. 이 주의 회차는 2026-09-14 월요일이다. */
	static final Instant TODAY = Instant.parse("2026-09-15T01:00:00Z");
	static final LocalDate THIS_WEEK = LocalDate.parse("2026-09-14");

	/** 저장소를 흉내 낸다. 읽은 것과 쓴 것을 그대로 들고 있는다. */
	static class FakeStore extends WeeklyStateStore {
		final List<LocalDate> written = new ArrayList<>();
		WeeklyRunDocument run;
		OffsetDateTime manualRequest;

		FakeStore() {
			super("pickage-raw", "http://fake:9000", "key", "secret");
		}

		@Override
		public Optional<WeeklyRunDocument> readRun(LocalDate weekOf) {
			return Optional.ofNullable(run);
		}

		@Override
		public Optional<OffsetDateTime> readManualRequest(LocalDate weekOf) {
			return Optional.ofNullable(manualRequest);
		}

		@Override
		public void writeManualRequest(LocalDate weekOf, OffsetDateTime requestedAt) {
			written.add(weekOf);
			manualRequest = requestedAt;
		}
	}

	static WeeklyIngestService service(FakeStore store) {
		return new WeeklyIngestService(store, Clock.fixed(TODAY, ZoneOffset.UTC));
	}

	static WeeklyRunDocument document(LocalDate weekOf, String status, OffsetDateTime claimedAt) {
		return new WeeklyRunDocument(weekOf, status,
			new WeeklyRunDocument.Coverage(weekOf, weekOf.minusDays(1),
				List.of(weekOf.minusDays(14), weekOf.minusDays(1))),
			null, null, 0, null, claimedAt, null, List.of());
	}

	static ExceptionType typeOf(Executable call) {
		return assertThrows(BusinessException.class, call).getExceptionType();
	}

	interface Executable extends org.junit.jupiter.api.function.Executable {
	}

	/* ── 주차 검증 ────────────────────────────────────────────── */

	@Test
	void 월요일이_아닌_회차는_거부한다() {
		// 깨지면 조회가 늘 빈 결과가 되는데, 화면에는 "그 주에 아무것도 없다" 로만 보인다.
		var service = service(new FakeStore());
		assertEquals(ExceptionType.INVALID_VALUE_FORMAT,
			typeOf(() -> service.run(LocalDate.parse("2026-09-15"))));
	}

	@Test
	void 아직_오지_않은_주는_수동_실행을_거부한다() {
		var service = service(new FakeStore());
		assertEquals(ExceptionType.LIMIT_EXCEEDED,
			typeOf(() -> service.requestManualRun(THIS_WEEK.plusWeeks(1))));
	}

	@Test
	void 이번_주는_수동_실행을_받는다() {
		var store = new FakeStore();
		service(store).requestManualRun(THIS_WEEK);
		assertEquals(List.of(THIS_WEEK), store.written);
	}

	/* ── 18개월 한계 ──────────────────────────────────────────── */

	@Test
	void 다시_받을_수_있는_한계를_넘긴_주차는_거부한다() {
		// 가장 값비싼 실패를 막는 규칙이다. npm 은 상한을 넘긴 요청에 400 이 아니라
		// 시작일이 조용히 잘린 200 을 준다 — 받았다고 믿은 채 구간이 빈다.
		var service = service(new FakeStore());
		// 창 시작이 2025-03-10 이라 한계(2025-03-15)보다 이르다.
		assertEquals(ExceptionType.LIMIT_EXCEEDED,
			typeOf(() -> service.requestManualRun(LocalDate.parse("2025-03-24"))));
	}

	@Test
	void 한계_안쪽_주차는_받는다() {
		// 창 시작이 2025-03-17 이라 한계(2025-03-15)보다 늦다. 경계 바로 안쪽이다.
		var store = new FakeStore();
		service(store).requestManualRun(LocalDate.parse("2025-03-31"));
		assertEquals(List.of(LocalDate.parse("2025-03-31")), store.written);
	}

	/* ── 없는 주 ──────────────────────────────────────────────── */

	@Test
	void 객체가_없는_주도_목록에_남는다() {
		// 저장된 것만 보여 주면 타이머가 멈춰 있던 주가 화면에서 사라진다.
		// 그게 가장 알아야 할 주다.
		var runs = service(new FakeStore()).recentRuns(3);
		assertEquals(3, runs.size());
		assertEquals(THIS_WEEK, runs.get(0).weekOf());
		assertEquals(THIS_WEEK.minusWeeks(2), runs.get(2).weekOf());
		assertTrue(runs.stream().allMatch(run -> WeeklyIngestService.MISSING.equals(run.status())));
	}

	@Test
	void 객체가_없어도_수집_구간은_회차에서_유도한다() {
		var run = service(new FakeStore()).run(THIS_WEEK);
		assertEquals(LocalDate.parse("2026-08-31"), run.coverage().windowStart());
		assertEquals(LocalDate.parse("2026-09-13"), run.coverage().windowEnd());
	}

	@Test
	void weeks_범위를_벗어나면_거부한다() {
		var service = service(new FakeStore());
		assertEquals(ExceptionType.LIMIT_EXCEEDED, typeOf(() -> service.recentRuns(0)));
		assertEquals(ExceptionType.LIMIT_EXCEEDED,
			typeOf(() -> service.recentRuns(WeeklyIngestService.MAX_WEEKS + 1)));
	}

	/* ── 우편함 ───────────────────────────────────────────────── */

	@Test
	void 회차가_없어도_우편함이_있으면_드러난다() {
		// S15P21A506-345 가 정한 전제다. 러너는 우편함만 있어도 회차로 친다.
		var store = new FakeStore();
		store.manualRequest = OffsetDateTime.parse("2026-09-15T00:30:00Z");

		var run = service(store).run(THIS_WEEK);
		assertEquals(WeeklyIngestService.MISSING, run.status());
		assertNotNull(run.manualRequestAt());
		assertTrue(run.manualPending());
	}

	@Test
	void 집혀_간_요청은_대기중이_아니다() {
		var store = new FakeStore();
		store.manualRequest = OffsetDateTime.parse("2026-09-15T00:30:00Z");
		store.run = document(THIS_WEEK, "RUNNING", OffsetDateTime.parse("2026-09-15T00:40:00Z"));

		assertFalse(service(store).run(THIS_WEEK).manualPending());
	}

	@Test
	void 집힌_뒤_다시_넣은_요청은_대기중이다() {
		var store = new FakeStore();
		store.manualRequest = OffsetDateTime.parse("2026-09-15T00:50:00Z");
		store.run = document(THIS_WEEK, "BLOCKED", OffsetDateTime.parse("2026-09-15T00:40:00Z"));

		assertTrue(service(store).run(THIS_WEEK).manualPending());
	}

	@Test
	void 수동_요청은_회차_객체를_만들지_않는다() {
		// run.json 의 필자는 러너 하나뿐이어야 한다. 여기서 같이 쓰기 시작하면
		// 러너가 잠금 없이 읽고-고쳐-쓰기를 하는 전제가 무너진다.
		var store = new FakeStore() {
			@Override
			public Optional<WeeklyRunDocument> readRun(LocalDate weekOf) {
				return Optional.empty();
			}
		};
		var run = service(store).requestManualRun(THIS_WEEK);

		assertEquals(WeeklyIngestService.MISSING, run.status());
		assertTrue(run.manualPending());
	}

	/* ── 손상된 상태 객체 ─────────────────────────────────── */

	@Test
	void week_of_가_없는_문서도_500_이_되지_않는다() {
		// mc 로 우편함을 넣다가 경로를 run.json 으로 잘못 치면 이 모양이 된다.
		// 손상된 객체 하나가 조회 API 를 통째로 막으면 안 된다.
		var store = new FakeStore();
		store.run = new WeeklyRunDocument(null, "RUNNING", null,
			null, null, 0, null, null, null, null);

		var run = service(store).run(THIS_WEEK);

		assertEquals(THIS_WEEK, run.weekOf(), "읽어 온 주가 권위 있다");
		assertEquals(LocalDate.parse("2026-08-31"), run.coverage().windowStart());
		assertTrue(run.steps().isEmpty());
	}
}
