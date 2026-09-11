package com.ssafy.pickage.domain.report;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;

import javax.xml.parsers.DocumentBuilderFactory;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;

/**
 * HTML 렌더러.
 *
 * <p>여기서 보는 것은 모양이 아니라 <b>PDF 로 변환될 수 있는 HTML 인지</b>다. 변환기가 XML
 * 파서를 쓰므로 태그 하나만 안 닫혀도 <b>미리보기는 멀쩡한데 다운로드만 실패</b>한다.
 * 그 고장은 원인을 찾기 어려워서, 사람이 아니라 시험이 잡아야 한다.
 */
class ReportHtmlRendererTest {

	private static final LocalDate DAY = LocalDate.parse("2026-08-31");

	private static PackagesOverviewResponse.Item item(String name, String description) {
		return new PackagesOverviewResponse.Item(name, "https://github.com/x/" + name, "5.0.0",
			Instant.parse("2026-07-14T09:02:11Z"), description, List.of("MIT"),
			false, 1_200_000L, 66_000, 12, 180, -3);
	}

	private static ReportHtmlRenderer.Sources sources(PackagesOverviewResponse overview) {
		var downloads = TrendResponse.downloads(
			List.of(new TrendResponse.Series("express", null, List.of(
				new TrendResponse.Point(DAY.minusWeeks(1), 1_100_000L),
				new TrendResponse.Point(DAY, 1_200_000L)))),
			List.of());

		var dependents = TrendResponse.dependents(
			List.of(new TrendResponse.Series("express", "5", List.of(
				new TrendResponse.Point(DAY, 900L)))),
			List.of());

		var share = VersionShareResponse.of(DAY,
			List.of(new VersionShareResponse.Item("express",
				List.of(new VersionShareResponse.Slice("5", 900L, new BigDecimal("100.0"))))),
			List.of());

		return new ReportHtmlRenderer.Sources(List.of("express"), DAY.minusWeeks(4), DAY,
			overview, downloads, dependents, share, Set.of());
	}

	/** XML 로 파싱되면 변환기도 읽을 수 있다. */
	private static void assertWellFormed(String html) {
		assertDoesNotThrow(() -> {
			var factory = DocumentBuilderFactory.newInstance();
			// DTD 를 가지러 네트워크로 나가지 않게 막는다. 시험이 인터넷에 기대면 안 된다.
			factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
			factory.newDocumentBuilder().parse(
				new java.io.ByteArrayInputStream(html.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
		}, "XML 로 파싱되지 않는다 — PDF 변환이 실패한다");
	}

	@Test
	@DisplayName("PDF 로 변환될 수 있는 형태다 (태그가 모두 닫힌다)")
	void producesWellFormedXhtml() {
		String html = new ReportHtmlRenderer().render(
			sources(new PackagesOverviewResponse(DAY, List.of(item("express", "Fast web framework")), List.of())));

		assertWellFormed(html);
		assertTrue(html.contains("Pickage 생태계 보고서"));
	}

	/**
	 * <b>이 시험이 제일 중요하다.</b> {@code description} 은 npm 에서 온 남의 문자열이다.
	 * 이스케이프하지 않으면 두 가지가 동시에 터진다 — 모달에서 스크립트가 돌고,
	 * {@code &} 하나에 XML 파싱이 깨져 PDF 변환이 실패한다.
	 */
	@Test
	@DisplayName("남의 문자열이 태그로 해석되지 않는다")
	void escapesForeignText() {
		String nasty = "<script>alert(1)</script> & \"quoted\" 'single'";
		String html = new ReportHtmlRenderer().render(
			sources(new PackagesOverviewResponse(DAY, List.of(item("express", nasty)), List.of())));

		assertWellFormed(html);
		assertFalse(html.contains("<script>"), "스크립트 태그가 그대로 들어갔다");
	}

	@Test
	@DisplayName("고른 구역은 비어 있어도 제목과 사유를 적는다")
	void drawsPendingSections() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		var withSections = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(),
			base.downloads(), base.dependents(), base.versionShare(),
			Set.of(ReportSection.COMMUNITY, ReportSection.FEATURES));

		String html = new ReportHtmlRenderer().render(withSections);

		assertWellFormed(html);
		assertTrue(html.contains("커뮤니티 분석"));
		assertTrue(html.contains("기능 심화 분석"));
		assertTrue(html.contains("아직 제공되지 않습니다"));
	}

	/**
	 * 자료가 없는 칸을 빈칸으로 두면 0 으로 읽힌다. 화면이 "집계 대기" 로 구분하는 것과
	 * 같은 규칙을 문서도 따라야 한다 — 두 곳이 다르게 적으면 그게 곧 구현 차이다.
	 */
	@Test
	@DisplayName("결측을 빈칸이 아니라 글자로 적는다")
	void writesMissingAsWords() {
		var pending = new PackagesOverviewResponse.Item(
			"consola", null, "3.4.2", null, null, List.of(), false,
			null, null, null, null, null);
		var overview = new PackagesOverviewResponse(null, List.of(pending), List.of("nope-pkg"));
		var emptyTrend = TrendResponse.dependents(
			List.of(new TrendResponse.Series("consola", null, List.of())), List.of());
		var emptyShare = VersionShareResponse.of(null,
			List.of(new VersionShareResponse.Item("consola", List.of())), List.of());

		String html = new ReportHtmlRenderer().render(new ReportHtmlRenderer.Sources(
			List.of("consola"), null, null, overview, emptyTrend, emptyTrend, emptyShare, Set.of()));

		assertWellFormed(html);
		assertTrue(html.contains("집계 대기"), "null 지표를 0 처럼 비워 두었다");
		assertTrue(html.contains("자료 없음"));
		assertTrue(html.contains("nope-pkg"), "못 찾은 이름이 문서에 없다");
	}

	@Test
	@DisplayName("폰트 이름이 변환기와 같다 (다르면 PDF 에서 한글이 빠진다)")
	void fontFamilyMatchesConverter() {
		String html = new ReportHtmlRenderer().render(
			sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of())));

		assertTrue(html.contains(HtmlToPdf.FAMILY),
			"HTML 의 font-family 가 변환기가 등록하는 이름과 다르다");
	}
}
