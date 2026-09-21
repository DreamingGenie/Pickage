package com.ssafy.pickage.domain.report;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.report.ChartGeometry.Box;
import com.ssafy.pickage.domain.report.ChartGeometry.Domain;
import com.ssafy.pickage.domain.report.ChartGeometry.Line;
import com.ssafy.pickage.domain.report.ChartGeometry.Pt;

/**
 * 화면의 {@code geometry.ts} 와 같은 값이 나오는지 확인한다(공통-R08).
 *
 * <p>기대값은 손으로 만든 것이 아니라 <b>같은 입력으로 화면 코드(TypeScript)를 실행해 얻은 값</b>이다
 * (S15P21A506-414). 화면 식을 고치면 이 값도 다시 뽑아 맞춘다.
 */
class ChartGeometryTest {

	private static final LocalDate START = LocalDate.of(2024, 1, 1);

	private static Line weekly(double... values) {
		List<Pt> points = new ArrayList<>();
		for (int i = 0; i < values.length; i++) points.add(new Pt(START.plusDays(7L * i), values[i]));
		return new Line("x", 0, points);
	}

	private static void assertMatches(List<Line> lines, double lo, double hi, double[] ticks, String[] labels) {
		Domain d = ChartGeometry.extentY(lines);
		assertThat(d.lo()).isCloseTo(lo, within(1e-6 * Math.max(1, Math.abs(lo))));
		assertThat(d.hi()).isCloseTo(hi, within(1e-6 * Math.max(1, Math.abs(hi))));

		List<Double> t = ChartGeometry.ticksY(d, 3);
		assertThat(t).hasSize(ticks.length);
		for (int i = 0; i < ticks.length; i++) {
			assertThat(t.get(i)).isCloseTo(ticks[i], within(1e-6 * Math.max(1, Math.abs(ticks[i]))));
		}
		assertThat(t.stream().map(v -> ChartGeometry.formatTick(v, d, 3)).toList()).containsExactly(labels);
	}

	@Test
	void 자릿수가_다른_두_선의_도메인과_눈금은_화면과_같다() {
		assertMatches(
			List.of(weekly(5652558, 20000000, 100724471), weekly(7794785, 12000000, 15395986)),
			4804674.3, 115833141.65,
			new double[] {4804674.3, 13879919.395216089, 40096816.81774847, 115833141.65},
			new String[] {"4.8M", "14M", "40M", "116M"});
	}

	@Test
	void 도메인이_좁으면_눈금_단위를_축_전체로_고정한다() {
		// 98만~102만 — compact 만 쓰면 눈금 넷이 모두 "1.0M" 이 되어 읽을 수 없다.
		assertMatches(
			List.of(weekly(980000, 1000000, 1020000)),
			976868.5952866753, 1023269.6646045768,
			new double[] {976868.5952866753, 992096.9897690436, 1007562.779293317, 1023269.6646045768},
			new String[] {"0.98M", "0.99M", "1.01M", "1.02M"});
	}

	@Test
	void 작은_값은_정수로_반올림하고_큰_눈금은_compact다() {
		assertMatches(
			List.of(weekly(5, 40, 900)),
			4.25, 1035,
			new double[] {4.25, 29.56512109453588, 176.94792905212225, 1035},
			new String[] {"4", "30", "177", "1.0k"});
	}

	@Test
	void 값이_모두_같으면_평평한_선을_가운데_두고_위아래로_벌린다() {
		assertMatches(
			List.of(weekly(100, 100, 100)),
			90, 110,
			new double[] {90, 96, 103, 110},
			new String[] {"90", "96", "103", "110"});
	}

	@Test
	void 값이_0에_닿으면_하한도_0이다() {
		assertMatches(
			List.of(weekly(0, 20, 500)),
			0, 575,
			new double[] {0, 7, 68, 575},
			new String[] {"0", "7", "68", "575"});
	}

	@Test
	void 점이_하나뿐이어도_구간을_만든다() {
		assertMatches(
			List.of(weekly(42)),
			37.8, 46.2,
			new double[] {38, 40, 43, 46},
			new String[] {"38", "40", "43", "46"});
	}

	@Test
	void 몇_자릿수를_오가는_축은_눈금마다_단위가_다르다() {
		assertMatches(
			List.of(weekly(1, 10, 100000, 90000000)),
			0.85, 103500000,
			new double[] {0.85, 706.5567366903523, 270613.3435869732, 103500000},
			new String[] {"1", "707", "271k", "104M"});
	}

	@Test
	void 자료가_없으면_0에서_1이다() {
		Domain d = ChartGeometry.extentY(List.of(new Line("x", 0, List.of())));
		assertThat(d).isEqualTo(new Domain(0, 1));
	}

	@Test
	void compact는_화면과_같은_자릿수로_줄인다() {
		double[] inputs = {0, 999, 1000, 1499, 9999, 10000, 123456, 1000000, 9999999, 10000000, 101234567};
		String[] expected = {"0", "999", "1.0k", "1.5k", "10.0k", "10k", "123k", "1.0M", "10.0M", "10M", "101M"};
		for (int i = 0; i < inputs.length; i++) {
			assertThat(ChartGeometry.compact(inputs[i])).as("compact(%s)", inputs[i]).isEqualTo(expected[i]);
		}
	}

	@Test
	void 짧은_날짜는_연도_두_자리와_월이다() {
		assertThat(ChartGeometry.shortDate(LocalDate.of(2026, 8, 31))).isEqualTo("26.08");
		assertThat(ChartGeometry.shortDate(LocalDate.of(2009, 1, 5))).isEqualTo("09.01");
	}

	@Test
	void 선은_간격이_벌어진_곳에서_끊는다() {
		List<Pt> points = List.of(
			new Pt(LocalDate.of(2024, 1, 1), 10), new Pt(LocalDate.of(2024, 1, 8), 20),
			new Pt(LocalDate.of(2024, 1, 15), 40),
			// 3주 공백 — 이 주들은 관측하지 못했다. 양옆을 직선으로 이으면 연속 관측처럼 보인다.
			new Pt(LocalDate.of(2024, 2, 5), 80), new Pt(LocalDate.of(2024, 2, 12), 160));
		Line line = new Line("g", 0, points);
		Domain y = ChartGeometry.extentY(List.of(line));
		Domain x = ChartGeometry.extentX(List.of(line));
		Box box = new Box(46, 10, 582, 178);

		assertThat(y.lo()).isCloseTo(8.5, within(1e-9));
		assertThat(y.hi()).isCloseTo(184, within(1e-9));
		assertThat(ChartGeometry.buildLine(points, x, y, box))
			.isEqualTo("M46.00 179.21L143.00 140.44L240.00 100.33M531.00 59.51L628.00 18.33");
	}

	@Test
	void 도넛_조각은_화면과_같은_경로다() {
		assertThat(ChartGeometry.donutArc(58, 58, 56, 34.72, 0, 0.262))
			.isEqualTo("M58.00 2.00A56 56 0 0 1 113.84 62.22L92.62 60.62A34.72 34.72 0 0 0 58.00 23.28Z");
		// 절반을 넘는 조각은 large-arc 플래그가 1 이다.
		assertThat(ChartGeometry.donutArc(58, 58, 56, 34.72, 0.262, 0.9))
			.isEqualTo("M113.84 62.22A56 56 0 1 1 25.08 12.70L37.59 29.91A34.72 34.72 0 1 0 92.62 60.62Z");
	}

	@Test
	void 좌표_변환은_화면과_같다() {
		Box box = new Box(46, 10, 582, 178);
		assertThat(ChartGeometry.scaleX(20000, new Domain(19000, 21000), box)).isCloseTo(337, within(1e-9));
		assertThat(ChartGeometry.scaleY(500, new Domain(8.5, 184), box)).isCloseTo(-49.726751443582145, within(1e-9));
	}

	/* ------------------------------------------------------------------ *
	 * 변화율 (S15P21A506-416) — 기대값은 같은 입력으로 화면의 indexSeriesTo100·indexedExtentY 등을 실행해 얻었다.
	 * ------------------------------------------------------------------ */

	private static void assertIndex(List<Line> lines, double[][] values, double lo, double hi, double[] ticks,
		String[] labels) {
		List<Line> idx = ChartGeometry.indexLines(lines);
		assertThat(idx).hasSize(values.length);
		for (int i = 0; i < values.length; i++) {
			assertThat(idx.get(i).points()).hasSize(values[i].length);
			for (int j = 0; j < values[i].length; j++) {
				assertThat(idx.get(i).points().get(j).value()).isCloseTo(values[i][j], within(1e-9));
			}
		}
		Domain d = ChartGeometry.extentIndex(idx);
		assertThat(d.lo()).isCloseTo(lo, within(1e-9));
		assertThat(d.hi()).isCloseTo(hi, within(1e-9));
		List<Double> t = ChartGeometry.ticksLinear(d, 3);
		for (int i = 0; i < ticks.length; i++) assertThat(t.get(i)).isCloseTo(ticks[i], within(1e-9));
		assertThat(t.stream().map(v -> ChartGeometry.formatIndexTick(v, d, 3)).toList()).containsExactly(labels);
	}

	@Test
	void 변화율은_선마다_첫_점을_100으로_둔다() {
		assertIndex(List.of(weekly(1000, 1200, 1500, 2100), weekly(300, 330, 360, 420)),
			new double[][] {{100, 120, 150, 210}, {100, 110, 120, 140}},
			86.8, 223.2,
			new double[] {86.8, 132.26666666666665, 177.73333333333332, 223.2},
			new String[] {"87%", "132%", "178%", "223%"});
	}

	@Test
	void 변화율_눈금의_소수_자리는_눈금_간격을_따른다() {
		// 100 근처에 몰린 값 — 정수 눈금이면 네 눈금이 모두 "100%" 가 된다.
		assertIndex(List.of(weekly(1000, 1004, 1010, 1012)),
			new double[][] {{100, 100.4, 101, 101.2}},
			98, 103.2,
			new double[] {98, 99.73333333333333, 101.46666666666667, 103.2},
			new String[] {"98.0%", "99.7%", "101.5%", "103.2%"});
	}

	@Test
	void 줄어드는_선도_100이_도메인_안에_있다() {
		assertIndex(List.of(weekly(50000, 48000, 47000, 41000)),
			new double[][] {{100, 96, 94, 82}},
			79.84, 102.16,
			new double[] {79.84, 87.28, 94.72, 102.16},
			new String[] {"80%", "87%", "95%", "102%"});
	}

	@Test
	void 변화가_없으면_위아래_2퍼센트_포인트를_벌린다() {
		assertIndex(List.of(weekly(700, 700, 700)),
			new double[][] {{100, 100, 100}},
			98, 102,
			new double[] {98, 99.33333333333333, 100.66666666666667, 102},
			new String[] {"98.0%", "99.3%", "100.7%", "102.0%"});
	}

	@Test
	void 첫_값이_0이면_비율을_지어내지_않고_그_선을_뺀다() {
		List<Line> idx = ChartGeometry.indexLines(List.of(weekly(0, 5, 9), weekly(10, 20, 30)));

		assertThat(idx).hasSize(1);
		assertThat(idx.getFirst().points().getLast().value()).isCloseTo(300, within(1e-9));
	}

	@Test
	void 그릴_선이_없으면_변화율_도메인은_90에서_110이다() {
		assertThat(ChartGeometry.extentIndex(List.of())).isEqualTo(new Domain(90, 110));
	}

	@Test
	void 선형_좌표와_선형_선은_화면과_같다() {
		Box box = new Box(46, 10, 582, 178);
		Domain d = new Domain(86.8, 223.2);
		assertThat(ChartGeometry.scaleYLinear(150, d, box)).isCloseTo(105.52492668621699, within(1e-9));
		assertThat(ChartGeometry.scaleYLinear(100, d, box)).isCloseTo(170.77419354838707, within(1e-9));

		// 2024-01-08 → 02-05 는 간격이 넘어 끊긴다.
		var points = List.of(new Pt(LocalDate.of(2024, 1, 1), 100), new Pt(LocalDate.of(2024, 1, 8), 120),
			new Pt(LocalDate.of(2024, 2, 5), 150));
		Domain xd = new Domain(LocalDate.of(2024, 1, 1).toEpochDay(), LocalDate.of(2024, 2, 5).toEpochDay());
		assertThat(ChartGeometry.buildLine(points, xd, d, box, true))
			.isEqualTo("M46.00 170.77L162.40 144.67M628.00 105.52");
	}

	@Test
	void 선_모양은_세_가지를_돌려_쓰고_색만으로_구분하지_않는다() {
		assertThat(ChartGeometry.style(0).dash()).isNull();
		assertThat(ChartGeometry.style(1).dash()).isEqualTo("7 3");
		assertThat(ChartGeometry.style(2).dash()).isEqualTo("2 3");
		assertThat(ChartGeometry.style(3)).isEqualTo(ChartGeometry.style(0));
		assertThat(ChartGeometry.style(-1)).isEqualTo(ChartGeometry.style(2));
	}
}
