package com.ssafy.pickage.domain.report;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

import java.io.ByteArrayInputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import javax.xml.parsers.DocumentBuilderFactory;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.text.PDFTextStripper;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.DataStatus;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.CommunityResultResponse;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.dto.CommunitySummaryResponse;
import com.ssafy.pickage.domain.community.dto.DataLimitsResponse;
import com.ssafy.pickage.domain.community.dto.Freshness;
import com.ssafy.pickage.domain.community.dto.MessageResponse;
import com.ssafy.pickage.domain.community.dto.RepositoryInfoResponse;
import com.ssafy.pickage.domain.community.dto.SummaryMarkResponse;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.dto.TopicResponse;
import com.ssafy.pickage.domain.community.dto.ViewStatus;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.TransitionsResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;

/**
 * 문서 전체 — 그래프 위에 수치 표, 기본 조건, 구역 구성, 그리고 <b>실제 PDF 변환</b>(S15P21A506-414).
 *
 * <p>렌더러 시험은 HTML 이 XML 인지까지만 본다. 변환기가 SVG 를 그리고 한글 글꼴을 심고 쪽을 나누는 것은 <b>실제로 변환해
 * 보아야</b> 안다 — 이 파일 끝의 시험이 그것을 한다(운영 컨테이너에서도 같은 결과임은 이미지로 따로 확인했다).
 */
class ReportDocumentTest {

	private static final LocalDate DAY = LocalDate.parse("2026-08-31");
	private static final ReportHtmlRenderer RENDERER = new ReportHtmlRenderer();

	private static PackagesOverviewResponse.Item item(String name) {
		return new PackagesOverviewResponse.Item(name, "https://github.com/x/" + name, "5.0.0",
			Instant.parse("2026-07-14T09:02:11Z"), "desc", List.of("MIT"), false, 1_200_000L, 66_000, 12, 180, -3);
	}

	private static List<TrendResponse.Point> weekly(long start, long step, int weeks) {
		List<TrendResponse.Point> points = new ArrayList<>();
		for (int i = 0; i < weeks; i++) {
			points.add(new TrendResponse.Point(DAY.minusWeeks(weeks - 1L - i), start + step * i));
		}
		return points;
	}

	/** 패키지 둘, 의존 수는 major 별로 쪼개져 온다(같은 이름이 major 수만큼 반복). */
	private static ReportHtmlRenderer.Sources sources(Set<ReportSection> sections, CommunityStatusResponse community) {
		var overview = new PackagesOverviewResponse(DAY, List.of(item("axios"), item("got")), List.of());

		var downloads = TrendResponse.downloads(List.of(
			new TrendResponse.Series("axios", null, weekly(41_000_000, 100_000, 30)),
			new TrendResponse.Series("got", null, weekly(22_000_000, 40_000, 30))), List.of());

		// axios 는 major 둘의 합이 화면의 TOTAL 선이다(100_000 + 50_000 = 150_000 → 첫 점).
		var dependents = TrendResponse.dependents(List.of(
			new TrendResponse.Series("axios", "0", weekly(100_000, -1_000, 30)),
			new TrendResponse.Series("axios", "1", weekly(50_000, 4_000, 30)),
			new TrendResponse.Series("got", "14", weekly(8_000, 300, 30))), List.of());

		List<VersionShareResponse.Slice> many = new ArrayList<>();
		for (int i = 0; i < 8; i++) many.add(new VersionShareResponse.Slice(String.valueOf(i), 1000L - i * 100L,
			new BigDecimal("20.0").subtract(new BigDecimal(i))));
		var share = VersionShareResponse.of(DAY, List.of(
			new VersionShareResponse.Item("axios", many),
			new VersionShareResponse.Item("got", List.of(new VersionShareResponse.Slice("14", 900L, new BigDecimal("100.0"))))),
			List.of());

		var transitions = TransitionsResponse.of("3y", DAY.minusYears(3), DAY, List.of(
			TransitionsResponse.Series.counted("axios", "regular", 100, 150, 120, 10, 5),
			TransitionsResponse.Series.counted("axios", "peer", 20, 8, 2, 4, 1),
			TransitionsResponse.Series.unknown("got", "regular", TransitionsResponse.OUT_OF_SCOPE)), List.of());

		return new ReportHtmlRenderer.Sources(List.of("axios", "got"), null, null, overview, downloads, dependents,
			share, transitions, sections, community);
	}

	private static long count(String html, String needle) {
		return Pattern.compile(Pattern.quote(needle)).matcher(html).results().count();
	}

	private static void assertWellFormed(String html) {
		assertDoesNotThrow(() -> {
			var factory = DocumentBuilderFactory.newInstance();
			factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
			factory.newDocumentBuilder().parse(new ByteArrayInputStream(html.getBytes(StandardCharsets.UTF_8)));
		}, "XML 로 파싱되지 않는다 — PDF 변환이 실패한다");
	}

	private static CommunityStatusResponse community() {
		var topic = new TopicResponse(10636, "CLOSED", Instant.parse("2026-04-04T00:00:00Z"),
			Instant.parse("2026-04-03T00:00:00Z"), "Post Mortem", "npm 공급망 침해 사후 보고", 110, 907,
			CommentCollectionStatus.COMPLETE, SummaryStatus.READY, "악성 배포가 유통됐다. 원인은 계정 탈취였다.",
			List.of(new MessageResponse("jasonsaayman", "ISSUE_AUTHOR", "DISCUSSION",
				Instant.parse("2026-04-03T16:00:00Z"), "공격이 진행됐다고 설명했다.")),
			List.of(new SummaryMarkResponse(0, 12, "KEY_SENTENCE")));
		var result = new CommunityResultResponse(java.util.UUID.randomUUID(), Instant.parse("2026-09-19T18:31:00Z"),
			Instant.parse("2026-09-20T18:31:00Z"), Instant.parse("2026-09-26T18:31:00Z"), DataStatus.AVAILABLE,
			SummaryStatus.READY, null,
			new RepositoryInfoResponse("axios", "axios", "axios/axios", "PACKAGE_SCOPED", false, 4320, 342),
			new CommunitySummaryResponse(1, 110, 907, 0), List.of(topic), List.of(),
			new DataLimitsResponse("github-active-v1", 180, 2, 100, 4, "선택된 이슈 최대 2개 기준입니다."));
		return new CommunityStatusResponse("axios", ViewStatus.RESULT, Freshness.FRESH, null, result);
	}

	/* ------------------------------------------------------------------ *
	 * 구성
	 * ------------------------------------------------------------------ */

	@Test
	void 문서는_XML이고_그래프를_담아도_변환될_수_있는_형태다() {
		String html = RENDERER.render(sources(Set.of(ReportSection.COMMUNITY), community()));

		assertWellFormed(html);
	}

	@Test
	void 그래프가_위에_있고_수치_표가_그_아래에_있다() {
		String html = RENDERER.render(sources(Set.of(), null));

		for (String title : List.of("Downloads", "의존 수")) {
			int heading = html.indexOf("<h2>" + title + "</h2>");
			int chart = html.indexOf("class=\"figure\"", heading);
			int table = html.indexOf("<table>", heading);
			assertThat(heading).as(title).isPositive();
			assertThat(chart).as(title + " 그래프").isGreaterThan(heading);
			assertThat(table).as(title + " 표는 그래프 아래").isGreaterThan(chart);
		}
		// Version Share·유지·유입·이탈도 그림이 먼저다.
		assertThat(html.indexOf("class=\"donut\"")).isLessThan(html.indexOf("<th>major</th>"));
		assertThat(html.indexOf("class=\"tk\"")).isLessThan(html.indexOf("<th>종류</th>"));
	}

	@Test
	void 표는_그래프를_넣은_뒤에도_그대로_남는다() {
		String html = RENDERER.render(sources(Set.of(), null));

		// 그래프가 모양을, 표가 양 끝과 증감을 정확한 숫자로 말한다.
		assertThat(html).contains("41,000,000").contains("+2,900,000");
		assertThat(html).contains("<th class=\"n\">처음</th>").contains("<th class=\"n\">증감</th>");
	}

	@Test
	void 그래프는_패키지마다_한_줄이고_의존_수는_major를_날짜별로_더한다() {
		String html = RENDERER.render(sources(Set.of(), null));

		// 선그래프 둘(Downloads·의존 수) × 패키지 둘 = path 넷. major 별 세 시리즈가 세 줄이 되지 않는다.
		assertThat(count(html, "<path d=\"M")).as("선 넷 + 도넛 조각").isGreaterThanOrEqualTo(4);
		assertThat(count(html, "stroke-dasharray=\"7 3\"")).as("둘째 패키지는 파선 — 의존 수 실제값·변화율, Downloads").isEqualTo(3);
		// 첫 그래프는 실제값 축이다 — 눈금은 합계 범위에서 나오고 변화율(%)이 아니다.
		int dep = html.indexOf("<h2>의존 수</h2>");
		String depReal = html.substring(dep, html.indexOf("<p class=\"sub\">변화율</p>", dep));
		assertThat(depReal).doesNotContain("%</span>");
		assertThat(depReal).contains("class=\"tick\"");
	}

	@Test
	void 의존_수가_Downloads보다_먼저_나온다() {
		String html = RENDERER.render(sources(Set.of(), null));

		assertThat(html.indexOf("<h2>의존 수</h2>")).isPositive()
			.isLessThan(html.indexOf("<h2>Downloads</h2>"));
		assertThat(html.indexOf("<h2>Downloads</h2>")).isLessThan(html.indexOf("<h2>Version Share</h2>"));
	}

	@Test
	void 의존_수는_실제값_그래프_아래에_변화율_그래프가_있고_그_아래에_표가_있다() {
		String html = RENDERER.render(sources(Set.of(), null));

		int heading = html.indexOf("<h2>의존 수</h2>");
		int real = html.indexOf("<p class=\"sub\">실제값</p>", heading);
		int rate = html.indexOf("<p class=\"sub\">변화율</p>", heading);
		int table = html.indexOf("<table>", heading);
		assertThat(real).isGreaterThan(heading);
		assertThat(rate).isGreaterThan(real);
		assertThat(table).isGreaterThan(rate);

		String rateChart = html.substring(rate, table);
		assertThat(rateChart).contains(ReportCharts.BASELINE_LABEL).contains(ReportCharts.INDEX_NOTE);
		assertThat(rateChart).contains("%</span>");
		// 변화율 그래프의 선은 패키지마다 하나 — major 별로 갈라지지 않는다.
		assertThat(count(rateChart, "<path d=\"M")).isEqualTo(2);
	}

	@Test
	void Downloads에는_변화율_그래프를_붙이지_않는다() {
		String html = RENDERER.render(sources(Set.of(), null));

		int downloads = html.indexOf("<h2>Downloads</h2>");
		String section = html.substring(downloads, html.indexOf("<h2>Version Share</h2>", downloads));
		assertThat(section).doesNotContain(ReportCharts.BASELINE_LABEL).doesNotContain("class=\"sub\"");
		assertThat(count(html, ReportCharts.BASELINE_LABEL)).isEqualTo(1);
	}

	@Test
	void 조회_기간은_조건이_없으면_전체_기간과_실제_범위를_적는다() {
		String html = RENDERER.render(sources(Set.of(), null));

		// 예전에는 "자료 없음 ~ 자료 없음" 이라 자료가 있는데도 없는 것처럼 읽혔다.
		assertThat(html).doesNotContain("자료 없음 ~ 자료 없음");
		assertThat(html).contains("전체 기간 · " + DAY.minusWeeks(29) + " ~ " + DAY + " (주간)");
	}

	@Test
	void 조회_기간을_주었으면_그_기간을_적는다() {
		var base = sources(Set.of(), null);
		var given = new ReportHtmlRenderer.Sources(base.names(), DAY.minusYears(1), DAY, base.overview(),
			base.downloads(), base.dependents(), base.versionShare(), base.transitions(), Set.of(), null);

		assertThat(RENDERER.render(given)).contains(DAY.minusYears(1) + " ~ " + DAY).doesNotContain("전체 기간 ·");
	}

	@Test
	void Version_Share는_큰_몫_다섯과_기타로_접는다() {
		String html = RENDERER.render(sources(Set.of(), null));

		// axios 는 major 8개 → 5개 + 기타. 표에는 여덟이 모두 남는다.
		int share = html.indexOf("<h2>Version Share</h2>");
		int table = html.indexOf("<th>major</th>", share);
		String figure = html.substring(share, table);
		assertThat(figure).contains("기타").contains("4.x").doesNotContain(">5.x<");
		assertThat(html.substring(table)).contains("7.x");
	}

	@Test
	void 한_조각이_전부인_패키지도_그려진다() {
		String html = RENDERER.render(sources(Set.of(), null));

		assertThat(html).contains(">100%</span>");
	}

	@Test
	void 유지_유입_이탈은_패키지마다_종류별_막대를_그린다() {
		String html = RENDERER.render(sources(Set.of(), null));

		int from = html.indexOf("<h2>유지 · 유입 · 이탈</h2>");
		String section = html.substring(from, html.indexOf("<th>종류</th>", from));
		assertThat(section).contains("일반").contains("동반");
		// got 은 분석 대상 밖이라 값 대신 자리(ghost)와 사유다.
		assertThat(section).contains("class=\"fill ghost\"").contains("분석 대상 아님");
	}

	/* ------------------------------------------------------------------ *
	 * 구역
	 * ------------------------------------------------------------------ */

	@Test
	void 커뮤니티를_고르면_실제_내용이_실리고_자리_문구는_없다() {
		String html = RENDERER.render(sources(Set.of(ReportSection.COMMUNITY), community()));

		assertThat(html).contains("<h2>커뮤니티 분석</h2>").contains("npm 공급망 침해 사후 보고")
			.contains(">4,320건<").contains("핵심 논의 누적 댓글");
		assertThat(html).doesNotContain("이 구역은 아직 제공되지 않습니다");
	}

	@Test
	void 커뮤니티를_골랐는데_자료가_없으면_그_사실을_적는다() {
		String html = RENDERER.render(sources(Set.of(ReportSection.COMMUNITY),
			new CommunityStatusResponse("axios", ViewStatus.IDLE, null, null, null)));

		assertThat(html).contains("<h2>커뮤니티 분석</h2>").contains("아직 수집되지 않았습니다");
	}

	@Test
	void 고르지_않으면_커뮤니티_구역이_없다() {
		String html = RENDERER.render(sources(Set.of(), null));

		assertThat(html).doesNotContain("커뮤니티 분석");
	}

	@Test
	void 기능_심화_분석은_여전히_자리와_사유만_적는다() {
		String html = RENDERER.render(sources(Set.of(ReportSection.FEATURES), null));

		assertThat(html).contains("<h2>기능 심화 분석</h2>").contains("이 구역은 아직 제공되지 않습니다");
	}

	@Test
	void 구역_순서는_보낸_순서와_무관하게_고정이다() {
		var both = RENDERER.render(sources(new java.util.LinkedHashSet<>(
			List.of(ReportSection.FEATURES, ReportSection.COMMUNITY)), community()));

		assertThat(both.indexOf("<h2>커뮤니티 분석</h2>")).isLessThan(both.indexOf("<h2>기능 심화 분석</h2>"));
		assertThat(both.indexOf("<h2>기능 심화 분석</h2>")).isLessThan(both.indexOf("<h2>자료 상태와 해석 한계</h2>"));
	}

	/* ------------------------------------------------------------------ *
	 * 실제 PDF 변환
	 * ------------------------------------------------------------------ */

	private static byte[] convert(String html) {
		return new HtmlToPdf("fonts/Pretendard-Regular.ttf", "fonts/Pretendard-Bold.ttf").convert(html);
	}

	@Test
	void 실제로_변환하면_그래프가_벡터로_들어가고_글자가_살아_있다() throws Exception {
		byte[] pdf = convert(RENDERER.render(sources(Set.of(ReportSection.COMMUNITY), community())));

		assertThat(new String(pdf, 0, 5, StandardCharsets.ISO_8859_1)).isEqualTo("%PDF-");
		try (PDDocument doc = Loader.loadPDF(pdf)) {
			assertThat(doc.getNumberOfPages()).isGreaterThan(1);

			// 그래프 = SVG 하나당 Form XObject 하나. 선그래프 둘 + 도넛 둘.
			int forms = 0;
			for (var page : doc.getPages()) {
				PDResources resources = page.getResources();
				for (var name : resources.getXObjectNames()) {
					if (resources.getXObject(name) instanceof org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject) forms++;
				}
			}
			assertThat(forms).as("SVG 가 벡터로 들어갔다").isGreaterThanOrEqualTo(4);

			// 한글이 사라지지 않았다(글꼴이 심겼다) + 그래프 눈금·범례·커뮤니티 내용이 글자로 있다.
			String text = new PDFTextStripper().getText(doc);
			assertThat(text).contains("Pickage 생태계 보고서").contains("Downloads").contains("의존 수")
				.contains("Version Share").contains("커뮤니티 분석").contains("npm 공급망 침해 사후 보고")
				.contains("4,320건").contains("기준");
			// 로그 눈금 설명과 그래프 눈금(예: 값에서 나온 k/M 라벨)
			assertThat(text).contains("세로 눈금은 로그 간격입니다").containsPattern("\\d+(\\.\\d+)?[kM]");
		}
	}

	@Test
	void 그래프가_없는_자료여도_변환된다() throws Exception {
		var overview = new PackagesOverviewResponse(null, List.of(item("consola")), List.of());
		var emptyTrend = TrendResponse.dependents(List.of(new TrendResponse.Series("consola", null, List.of())),
			List.of());
		var emptyShare = VersionShareResponse.of(null, List.of(new VersionShareResponse.Item("consola", List.of())),
			List.of());
		var unknown = TransitionsResponse.of("3y", null, null,
			List.of(TransitionsResponse.Series.unknown("consola", "regular", TransitionsResponse.NOT_COMPUTED)),
			List.of());

		String html = RENDERER.render(new ReportHtmlRenderer.Sources(List.of("consola"), null, null, overview,
			emptyTrend, emptyTrend, emptyShare, unknown, Set.of(ReportSection.COMMUNITY), null));

		assertThat(html).contains("그래프로 그릴 자료가 없습니다").contains("자료 없음");
		byte[] pdf = convert(html);
		try (PDDocument doc = Loader.loadPDF(pdf)) {
			assertThat(doc.getNumberOfPages()).isGreaterThanOrEqualTo(1);
			assertThat(new PDFTextStripper().getText(doc)).contains("그래프로 그릴 자료가 없습니다");
		}
	}
}
