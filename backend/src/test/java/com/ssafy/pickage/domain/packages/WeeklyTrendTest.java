package com.ssafy.pickage.domain.packages;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.IntervalRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;

/**
 * 불규칙한 기준일 달력을 월요일 주간 격자로 맞추는 규칙 (S15P21A506-403).
 *
 * <p>DB 없이 도는 순수 계산 시험이다. 수치는 2026-09-20 에 공개 API 로 확인한 cheerio 의 실제
 * 값이다 — 02-13(금)은 직전 01-26 과 18일 떨어져 있고, 03-10(화)은 직전 03-09 와 하루 차이다.
 * 이 두 모양이 화면에서 선을 끊고 Downloads 를 급락시켰다.
 */
class WeeklyTrendTest {

	private static LocalDate d(String s) {
		return LocalDate.parse(s);
	}

	private static IntervalRow iv(String prev, String at, long value) {
		return new IntervalRow("cheerio", d(at), d(prev), value);
	}

	private static TrendRow obs(String at, long value) {
		return new TrendRow("cheerio", "1", d(at), value);
	}

	private static Map<LocalDate, Long> byDate(List<TrendRow> rows) {
		Map<LocalDate, Long> m = new LinkedHashMap<>();
		for (TrendRow r : rows) m.put(r.snapshotAt(), r.value());
		return m;
	}

	/* ------------------------------------------------------------------ *
	 * Downloads
	 * ------------------------------------------------------------------ */

	@Test
	@DisplayName("월요일 주간 구간은 값이 한 자리도 바뀌지 않는다")
	void regularWeeklyIntervalsAreUntouched() {
		var out = WeeklyTrend.downloads(List.of(
			iv("2026-01-05", "2026-01-12", 12_843_962),
			iv("2026-01-12", "2026-01-19", 13_962_516)),
			new SnapshotWindow(d("2026-01-12"), d("2026-01-19")));

		assertEquals(Map.of(d("2026-01-12"), 12_843_962L, d("2026-01-19"), 13_962_516L), byDate(out));
	}

	/**
	 * 18일 구간(42.1M)과 3일 구간(4.7M)이 <b>하루 평균이 같은 수준의 주간 값</b>으로 펴진다. 그리고
	 * <b>총량이 보존된다</b> — 환산이 다운로드를 만들거나 없애면 안 된다.
	 */
	@Test
	@DisplayName("18일·3일 구간을 일평균으로 펼쳐 주간 합계로 만들고, 총량은 보존한다")
	void irregularIntervalsSpreadIntoWeeks() {
		var rows = List.of(
			iv("2026-01-19", "2026-01-26", 14_381_510),
			iv("2026-01-26", "2026-02-13", 42_094_836), // 18일, 하루 2,338,602
			iv("2026-02-13", "2026-02-16", 4_728_330),  // 3일, 하루 1,576,110
			iv("2026-02-16", "2026-02-23", 15_860_988));

		var out = WeeklyTrend.downloads(rows, new SnapshotWindow(d("2026-01-26"), d("2026-02-23")));

		Map<LocalDate, Long> expected = new LinkedHashMap<>();
		expected.put(d("2026-01-26"), 14_381_510L);
		expected.put(d("2026-02-02"), 16_370_214L);                 // 7 x 2,338,602
		expected.put(d("2026-02-09"), 16_370_214L);
		expected.put(d("2026-02-16"), 14_082_738L);                 // 4 x 2,338,602 + 3 x 1,576,110
		expected.put(d("2026-02-23"), 15_860_988L);
		assertEquals(expected, byDate(out));

		long original = rows.stream().mapToLong(IntervalRow::value).sum();
		long weekly = out.stream().mapToLong(TrendRow::value).sum();
		assertEquals(original, weekly, "주간 합계를 다 더하면 원래 구간 합계와 같아야 한다");
	}

	@Test
	@DisplayName("하루짜리 구간이 끼어 있어도 급락 없이 그 주의 값이 된다 (03-10 화요일 기준일)")
	void oneDayIntervalDoesNotCauseDip() {
		var out = WeeklyTrend.downloads(List.of(
			iv("2026-03-02", "2026-03-09", 19_125_045),
			iv("2026-03-09", "2026-03-10", 3_489_606),   // 하루치 — 예전에는 이것이 한 점이 됐다
			iv("2026-03-10", "2026-03-16", 15_790_342)),
			new SnapshotWindow(d("2026-03-09"), d("2026-03-16")));

		// 03-16 주 = 하루 3,489,606 + 6일 15,790,342 = 19,279,948. 03-10 에는 점이 없다.
		assertEquals(Map.of(d("2026-03-09"), 19_125_045L, d("2026-03-16"), 19_279_948L), byDate(out));
	}

	@Test
	@DisplayName("그 패키지의 행이 없는 기준일이 끼면 7일이 덮이지 않은 주는 지어내지 않고 뺀다")
	void weekWithoutFullCoverageIsOmitted() {
		var out = WeeklyTrend.downloads(List.of(
			iv("2026-01-19", "2026-01-26", 700),
			// 01-26 → 02-02 구간의 행이 없다.
			iv("2026-02-02", "2026-02-09", 1_400)),
			new SnapshotWindow(d("2026-01-26"), d("2026-02-09")));

		// 02-02 주 [01-26, 02-02) 는 관측이 없다. 0 이나 부분합으로 채우지 않는다.
		assertEquals(Map.of(d("2026-01-26"), 700L, d("2026-02-09"), 1_400L), byDate(out));
	}

	@Test
	@DisplayName("조회 구간 밖 기준일의 구간이 가장자리 주에 걸쳐도 쓰고, 격자는 조회 구간으로 자른다")
	void windowClipsGridButUsesNeighborIntervals() {
		var rows = List.of(
			iv("2026-01-26", "2026-02-13", 42_094_836),
			iv("2026-02-13", "2026-02-16", 4_728_330));

		var out = WeeklyTrend.downloads(rows, new SnapshotWindow(d("2026-02-16"), d("2026-02-16")));

		// 02-16 한 점만 나온다. 그 주의 4일은 조회 구간 밖(02-13 이전)에서 시작한 구간이 채운다.
		assertEquals(Map.of(d("2026-02-16"), 14_082_738L), byDate(out));
	}

	@Test
	@DisplayName("패키지마다 독립이다 — 관측 시작이 달라도 서로의 격자를 건드리지 않는다")
	void packagesAreIndependent() {
		var out = WeeklyTrend.downloads(List.of(
			new IntervalRow("a", d("2026-03-09"), d("2026-03-02"), 70),
			new IntervalRow("a", d("2026-03-16"), d("2026-03-09"), 140),
			new IntervalRow("b", d("2026-03-16"), d("2026-03-09"), 210)),
			new SnapshotWindow(d("2026-03-02"), d("2026-03-16")));

		assertEquals(List.of("a", "a", "b"), out.stream().map(TrendRow::name).toList());
		assertEquals(List.of(70L, 140L, 210L), out.stream().map(TrendRow::value).toList());
	}

	@Test
	@DisplayName("행이 없으면 빈 결과다")
	void noRowsNoPoints() {
		assertTrue(WeeklyTrend.downloads(List.of(), new SnapshotWindow(d("2026-01-01"), d("2026-02-01"))).isEmpty());
		assertTrue(WeeklyTrend.dependents(List.of(), new SnapshotWindow(d("2026-01-01"), d("2026-02-01"))).isEmpty());
	}

	/* ------------------------------------------------------------------ *
	 * Dependents
	 * ------------------------------------------------------------------ */

	@Test
	@DisplayName("기준일이 전부 월요일이면 관측값 그대로다")
	void mondayObservationsAreUntouched() {
		var out = WeeklyTrend.dependents(List.of(
			obs("2026-01-12", 50_400), obs("2026-01-19", 50_420), obs("2026-01-26", 50_435)),
			new SnapshotWindow(d("2026-01-12"), d("2026-01-26")));

		assertEquals(Map.of(d("2026-01-12"), 50_400L, d("2026-01-19"), 50_420L, d("2026-01-26"), 50_435L),
			byDate(out));
	}

	@Test
	@DisplayName("빈 주는 양옆 관측치를 날짜 비율로 이어 채우고, 금요일 기준일은 점이 되지 않는다")
	void gapWeeksAreInterpolated() {
		var out = WeeklyTrend.dependents(List.of(
			obs("2026-01-26", 50_435),
			obs("2026-02-13", 50_472),   // 금요일, 18일 뒤
			obs("2026-02-16", 50_477)),
			new SnapshotWindow(d("2026-01-26"), d("2026-02-16")));

		Map<LocalDate, Long> expected = new LinkedHashMap<>();
		expected.put(d("2026-01-26"), 50_435L);
		expected.put(d("2026-02-02"), 50_449L);   // 50,435 + 37 x 7/18 = 50,449.39
		expected.put(d("2026-02-09"), 50_464L);   // 50,435 + 37 x 14/18 = 50,463.78
		expected.put(d("2026-02-16"), 50_477L);
		assertEquals(expected, byDate(out));
	}

	@Test
	@DisplayName("자기 관측 범위 밖으로는 내보내지 않는다 — 첫 관측 이전과 마지막 관측 이후를 지어내지 않는다")
	void noExtrapolationOutsideObservedRange() {
		var out = WeeklyTrend.dependents(List.of(
			obs("2026-03-04", 100),   // 수요일 시작
			obs("2026-03-16", 112),
			obs("2026-03-18", 113)),  // 수요일 끝
			new SnapshotWindow(d("2026-03-01"), d("2026-03-31")));

		// 첫 월요일은 03-09, 마지막 월요일은 03-16. 03-02 와 03-23 은 관측 범위 밖이다.
		assertEquals(List.of(d("2026-03-09"), d("2026-03-16")),
			out.stream().map(TrendRow::snapshotAt).toList());
	}

	@Test
	@DisplayName("major 마다 독립으로 이어 주고, 받은 (이름, major) 순서를 지킨다")
	void seriesAreInterpolatedIndependentlyAndOrderKept() {
		var out = WeeklyTrend.dependents(List.of(
			new TrendRow("express", "4", d("2026-01-26"), 700),
			new TrendRow("express", "4", d("2026-02-09"), 714),
			new TrendRow("express", "5", d("2026-02-02"), 100),   // 나중에 시작한 major
			new TrendRow("express", "5", d("2026-02-09"), 110)),
			new SnapshotWindow(d("2026-01-26"), d("2026-02-09")));

		assertEquals(List.of("4", "4", "4", "5", "5"), out.stream().map(TrendRow::major).toList());
		assertEquals(List.of(700L, 707L, 714L, 100L, 110L), out.stream().map(TrendRow::value).toList());
	}
}
