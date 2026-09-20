package com.ssafy.pickage.domain.report;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import javax.xml.parsers.DocumentBuilderFactory;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.report.ChartGeometry.Domain;
import com.ssafy.pickage.domain.report.ChartGeometry.Line;
import com.ssafy.pickage.domain.report.ChartGeometry.Pt;
import com.ssafy.pickage.domain.report.ReportCharts.ShareGroup;

/**
 * 보고서 그래프(S15P21A506-414).
 *
 * <p>모양은 사람이 눈으로 본다. 여기서 지키는 것은 <b>그려져야 하는 것이 그려지는지</b>, <b>PDF 변환기가 읽을 수 있는
 * 형태인지</b>(XML), 그리고 <b>SVG 안에 글자를 넣지 않는다는 약속</b>이다 — 글자가 SVG 에 들어가면 운영 컨테이너의 글꼴
 * 설정 부재로 PDF 에서 사라지거나 예외가 난다.
 */
class ReportChartsTest {

	private static final LocalDate START = LocalDate.of(2024, 1, 1);

	private static Line weekly(String label, int tone, double... values) {
		List<Pt> points = new ArrayList<>();
		for (int i = 0; i < values.length; i++) points.add(new Pt(START.plusDays(7L * i), values[i]));
		return new Line(label, tone, points);
	}

	private static long count(String html, String needle) {
		return Pattern.compile(Pattern.quote(needle)).matcher(html).results().count();
	}

	/** 조각도 XML 이어야 변환기가 읽는다. 부모 하나로 감싸 파싱한다. */
	private static void assertWellFormed(String fragment) {
		assertDoesNotThrow(() -> DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(
			new ByteArrayInputStream(("<root>" + fragment + "</root>").getBytes(StandardCharsets.UTF_8))),
			"XML 로 파싱되지 않는다 — PDF 변환이 실패한다");
	}

	/** SVG 요소 안쪽만 잘라 낸다. */
	private static String svgOf(String html) {
		int from = html.indexOf("<svg");
		return html.substring(from, html.indexOf("</svg>", from) + "</svg>".length());
	}

	/* ------------------------------------------------------------------ *
	 * 선그래프
	 * ------------------------------------------------------------------ */

	@Test
	void 선마다_경로와_마지막_점을_그리고_둘째_선은_파선이다() {
		String html = ReportCharts.lineChart(List.of(
			weekly("axios", 0, 41_000_000, 47_000_000, 52_000_000),
			weekly("got", 1, 22_000_000, 23_000_000, 23_500_000)), "Downloads 추이");

		assertWellFormed(html);
		assertThat(count(html, "<path ")).isEqualTo(2);
		assertThat(count(html, "<circle ")).as("선마다 마지막 점 하나").isEqualTo(2);
		// 색만으로 구분하지 않는다 — 기준 패키지는 실선, 다음은 파선이다.
		assertThat(count(html, "stroke-dasharray=\"7 3\"")).isEqualTo(1);
		assertThat(html).contains("stroke=\"#0F172A\"").contains("stroke=\"#0E7C6B\"");
	}

	@Test
	void SVG_안에_글자를_넣지_않는다() {
		String html = ReportCharts.lineChart(List.of(weekly("axios", 0, 10, 20, 40)), "차트");

		// 글자는 HTML 로 얹는다 — 운영 컨테이너에는 SVG 글자를 그릴 글꼴 설정이 없다.
		assertThat(svgOf(html)).doesNotContain("<text").doesNotContain("font-family");
		assertThat(html).contains("class=\"tick\"").contains("class=\"xlab\"");
	}

	@Test
	void 눈금_라벨은_화면과_같은_함수의_결과다() {
		List<Line> lines = List.of(
			weekly("a", 0, 5_652_558, 20_000_000, 100_724_471),
			weekly("b", 1, 7_794_785, 12_000_000, 15_395_986));
		String html = ReportCharts.lineChart(lines, "x");

		Domain d = ChartGeometry.extentY(lines);
		for (double t : ChartGeometry.ticksY(d, 3)) {
			assertThat(html).contains(">" + ChartGeometry.formatTick(t, d, 3) + "</span>");
		}
		// 위 geometry 시험이 정한 값 — 화면과 같다.
		assertThat(html).contains(">4.8M</span>").contains(">116M</span>");
	}

	@Test
	void 날짜_라벨은_처음과_끝을_포함한다() {
		String html = ReportCharts.lineChart(List.of(weekly("a", 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)), "x");

		assertThat(html).contains(">" + ChartGeometry.shortDate(START) + "</span>");
		assertThat(html).contains(">" + ChartGeometry.shortDate(START.plusDays(7 * 8)) + "</span>");
	}

	@Test
	void 관측_공백이_있으면_선을_끊어_두_조각으로_그린다() {
		var points = List.of(
			new Pt(LocalDate.of(2024, 1, 1), 10), new Pt(LocalDate.of(2024, 1, 8), 20),
			new Pt(LocalDate.of(2024, 2, 5), 80), new Pt(LocalDate.of(2024, 2, 12), 160));

		String html = ReportCharts.lineChart(List.of(new Line("a", 0, points)), "x");

		var d = Pattern.compile("<path d=\"([^\"]*)\"").matcher(html);
		assertThat(d.find()).isTrue();
		assertThat(d.group(1).chars().filter(c -> c == 'M').count()).as("공백에서 끊겨 M 이 둘").isEqualTo(2);
	}

	@Test
	void 점이_하나뿐인_선도_마지막_점으로_보인다() {
		String html = ReportCharts.lineChart(List.of(weekly("a", 0, 42)), "x");

		assertWellFormed(html);
		assertThat(count(html, "<circle ")).isEqualTo(1);
	}

	@Test
	void 그릴_점이_하나도_없으면_빈_문자열이다() {
		assertThat(ReportCharts.lineChart(List.of(), "x")).isEmpty();
		assertThat(ReportCharts.lineChart(List.of(new Line("a", 0, List.of())), "x")).isEmpty();
	}

	@Test
	void 점이_없는_선은_빼고_있는_선만_그린다() {
		String html = ReportCharts.lineChart(List.of(
			weekly("has", 0, 10, 20), new Line("empty", 1, List.of())), "x");

		assertThat(count(html, "<path ")).isEqualTo(1);
		assertThat(html).contains("has").doesNotContain("empty");
	}

	@Test
	void 남의_문자열은_이스케이프한다() {
		String nasty = "<b>a&\"'";
		String html = ReportCharts.lineChart(List.of(weekly(nasty, 0, 10, 20)), nasty);

		assertWellFormed(html);
		assertThat(html).doesNotContain("<b>a");
	}

	@Test
	void 로그_눈금이라는_설명을_그래프_아래에_붙인다() {
		String html = ReportCharts.lineChart(List.of(weekly("a", 0, 10, 20)), "x");

		assertThat(html).contains(ReportCharts.LOG_NOTE);
	}

	@Test
	void 범례는_기준_패키지에_기준_표시를_붙이고_선_모양을_테두리로_보인다() {
		String html = ReportCharts.lineChart(List.of(
			weekly("axios", 0, 10, 20), weekly("got", 1, 10, 20), weekly("ky", 2, 10, 20)), "x");

		assertThat(count(html, ">기준<")).isEqualTo(1);
		assertThat(html).contains("border-top:2px solid #0F172A").contains("border-top:2px dashed #0E7C6B")
			.contains("border-top:2px dotted #9A6A00");
	}

	/* ------------------------------------------------------------------ *
	 * 변화율 선그래프 (S15P21A506-416)
	 * ------------------------------------------------------------------ */

	@Test
	void 변화율_그래프는_선마다_경로와_100퍼센트_기준선을_그린다() {
		String html = ReportCharts.changeRateChart(List.of(
			weekly("axios", 0, 1000, 1200, 1500, 2100),
			weekly("got", 1, 300, 330, 360, 420)), "변화율");

		assertWellFormed(html);
		assertThat(count(html, "<path ")).isEqualTo(2);
		assertThat(count(html, "<circle ")).isEqualTo(2);
		assertThat(html).contains(ReportCharts.BASELINE_LABEL).contains(ReportCharts.INDEX_NOTE);
		assertThat(html).doesNotContain(ReportCharts.LOG_NOTE);
		// 눈금은 화면과 같은 함수의 결과다(값은 ChartGeometryTest).
		assertThat(html).contains(">87%</span>").contains(">132%</span>").contains(">178%</span>").contains(">223%</span>");
		assertThat(svgOf(html)).doesNotContain("<text");
	}

	@Test
	void 기준선은_눈금선과_다른_진한_선이다() {
		String html = ReportCharts.changeRateChart(List.of(weekly("a", 0, 100, 120, 150)), "x");

		assertThat(count(html, "stroke=\"#0F172A\" stroke-width=\"1\" stroke-opacity=\"0.55\"")).isEqualTo(1);
	}

	@Test
	void 같은_선이라도_변화율이면_실제값과_다른_그림이다() {
		var lines = List.of(weekly("a", 0, 1000, 1200, 1500), weekly("b", 1, 30000, 33000, 36000));

		assertThat(ReportCharts.changeRateChart(lines, "x")).isNotEqualTo(ReportCharts.lineChart(lines, "x"));
		// 둘 다 100 에서 출발한다 — 첫 점의 y 가 같다.
		var d = Pattern.compile("<path d=\"M[\\d.]+ ([\\d.]+)").matcher(ReportCharts.changeRateChart(lines, "x"))
			.results().map(m -> m.group(1)).toList();
		assertThat(d).hasSize(2).containsOnly(d.getFirst());
	}

	@Test
	void 첫_값이_0인_선은_변화율에서_빠지고_남는_선이_없으면_그래프가_없다() {
		String html = ReportCharts.changeRateChart(List.of(weekly("zero", 0, 0, 5, 9), weekly("ok", 1, 10, 20)), "x");

		assertThat(count(html, "<path ")).isEqualTo(1);
		assertThat(ReportCharts.changeRateChart(List.of(weekly("zero", 0, 0, 5, 9)), "x")).isEmpty();
		assertThat(ReportCharts.changeRateChart(List.of(), "x")).isEmpty();
	}

	@Test
	void 변화가_없는_선도_기준선과_함께_그려진다() {
		String html = ReportCharts.changeRateChart(List.of(weekly("flat", 0, 700, 700, 700)), "x");

		assertWellFormed(html);
		assertThat(html).contains(">98.0%</span>").contains(">102.0%</span>").contains(ReportCharts.BASELINE_LABEL);
	}

	/* ------------------------------------------------------------------ *
	 * Version Share
	 * ------------------------------------------------------------------ */

	@Test
	void 도넛은_조각마다_경로를_그리고_가운데에_가장_큰_몫을_적는다() {
		String html = ReportCharts.donut(List.of(
			new ShareGroup("13.x", 0.45), new ShareGroup("14.x", 0.19), new ShareGroup("11.x", 0.18),
			new ShareGroup("12.x", 0.18)), "got Version Share");

		assertWellFormed(html);
		assertThat(count(html, "<path ")).isEqualTo(4);
		assertThat(html).contains(">45%</span>").contains(">13.x</span>");
		assertThat(svgOf(html)).doesNotContain("<text");
	}

	@Test
	void 한_조각이_전부인_도넛은_고리로_그리고_가운데_글자를_덮지_않는다() {
		String html = ReportCharts.donut(List.of(new ShareGroup("1.x", 1.0)), "axios");

		assertWellFormed(html);
		// 시작과 끝이 같은 호는 아무것도 그려지지 않는다 — 굵은 테두리의 원 하나로 그린다.
		assertThat(count(html, "<path ")).isZero();
		assertThat(count(html, "<circle ")).isEqualTo(1);
		assertThat(html).contains("fill=\"none\"").contains(">100%</span>");
		// 흰 원으로 구멍을 내면 그 원이 가운데 글자를 덮었다(실측).
		assertThat(html).doesNotContain("#FFFFFF\"/>");
	}

	@Test
	void 몫이_0인_조각은_그리지_않는다() {
		String html = ReportCharts.donut(List.of(new ShareGroup("a", 0.6), new ShareGroup("b", 0.4),
			new ShareGroup("c", 0)), "x");

		assertThat(count(html, "<path ")).isEqualTo(2);
	}

	@Test
	void 조각이_없으면_도넛도_없다() {
		assertThat(ReportCharts.donut(List.of(), "x")).isEmpty();
		assertThat(ReportCharts.shareBars(List.of())).isEmpty();
	}

	@Test
	void 몫_막대는_가장_큰_몫을_100퍼센트_폭으로_잡는다() {
		String html = ReportCharts.shareBars(List.of(new ShareGroup("13.x", 0.45), new ShareGroup("14.x", 0.225)));

		assertWellFormed(html);
		assertThat(html).contains("width:100.0%").contains("width:50.0%");
		assertThat(html).contains(">45%<").contains(">23%<");
	}

	/* ------------------------------------------------------------------ *
	 * 유지 · 유입 · 이탈
	 * ------------------------------------------------------------------ */

	@Test
	void 네_범주를_항상_다_그리고_최댓값_대비_폭이다() {
		String html = ReportCharts.transitionBars(new Integer[] {200, 100, 50, 0}, "COMPLETE", 200);

		assertWellFormed(html);
		for (String label : List.of("유지", "유입", "이탈", "미관측")) assertThat(html).contains(">" + label + "<");
		assertThat(html).contains("width:100.0%").contains("width:50.0%").contains("width:25.0%");
		assertThat(html).contains(">200<").contains(">0<");
	}

	@Test
	void 값이_있으면_아주_작아도_2퍼센트는_보인다() {
		String html = ReportCharts.transitionBars(new Integer[] {1, 0, 0, 0}, "COMPLETE", 100_000);

		assertThat(html).contains("width:2.0%");
	}

	@Test
	void 분석_대상_아님은_0이_아니라_자리와_대시다() {
		String html = ReportCharts.transitionBars(new Integer[] {null, null, null, null}, "OUT_OF_SCOPE", 100);

		assertWellFormed(html);
		assertThat(count(html, "class=\"fill ghost\"")).isEqualTo(4);
		assertThat(count(html, ">—<")).isEqualTo(4);
		assertThat(html).doesNotContain(">0<");
	}

	@Test
	void 준비_중은_점선_빈_틀이다() {
		String html = ReportCharts.transitionBars(new Integer[] {null, null, null, null}, "NOT_COMPUTED", 100);

		assertThat(count(html, "track dashed")).isEqualTo(4);
		assertThat(html).doesNotContain("class=\"fill");
		assertThat(count(html, ">—<")).isEqualTo(4);
	}
}
