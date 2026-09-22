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
import com.ssafy.pickage.domain.packages.dto.RemovalReasonsResponse;
import com.ssafy.pickage.domain.packages.dto.TransitionsResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;
import com.ssafy.pickage.domain.report.dto.FeatureComparisonPayload;

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

		var transitions = TransitionsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(TransitionsResponse.Series.counted("express", "regular", 100, 150, 120, 10, 5, 2, 1, 2)),
			List.of());

		return new ReportHtmlRenderer.Sources(List.of("express"), DAY.minusWeeks(4), DAY,
			overview, downloads, dependents, share, transitions, Set.of());
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
	@DisplayName("의존 수 제목은 화면과 같은 한국어 용어다 (영어 Dependents 를 쓰지 않는다)")
	void usesTheScreensKoreanTermForDependents() {
		String html = new ReportHtmlRenderer().render(
			sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of())));

		assertTrue(html.contains("의존 수"));
		assertFalse(html.contains("Dependents"), "PDF 제목이 화면과 다른 영어 용어로 돌아갔다");
	}

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
			base.downloads(), base.dependents(), base.versionShare(), base.transitions(),
			Set.of(ReportSection.COMMUNITY, ReportSection.FEATURES));

		String html = new ReportHtmlRenderer().render(withSections);

		assertWellFormed(html);
		assertTrue(html.contains("커뮤니티 분석"));
		assertTrue(html.contains("기능 심화 분석"));
		assertTrue(html.contains("아직 제공되지 않습니다"));
	}

	private static FeatureComparisonPayload featuresPayload() {
		return new FeatureComparisonPayload(
			List.of(new FeatureComparisonPayload.PackageRef("winston", "3.19.0"),
				new FeatureComparisonPayload.PackageRef("pino", "10.3.1")),
			List.of(new FeatureComparisonPayload.FeatureRow("구조화 로깅", List.of(
				new FeatureComparisonPayload.Cell("winston", "3.19.0", "SUPPORTED",
					List.of("ev-1"), "EVIDENCE", null),
				new FeatureComparisonPayload.Cell("pino", "10.3.1", "UNCONFIRMED",
					List.of(), "GENERAL_KNOWLEDGE", "README 에 명시 없음")))),
			List.of(new FeatureComparisonPayload.NarrativeSection("요약", "두 패키지 모두 구조화 로깅을 지원합니다.")),
			null, false);
	}

	/**
	 * 세션이 판정 payload 를 실어 보내면 "아직 제공되지 않습니다" 대신 실제 내용이 실린다
	 * (S15P21A506-463). 라벨은 화면과 같은 한글이어야 한다(구상안 §7.2).
	 */
	@Test
	@DisplayName("기능 비교 payload 를 실으면 실제 판정이 채워진다")
	void rendersFeatureComparisonWhenPayloadPresent() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("winston", "desc")), List.of()));
		var withFeatures = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(), base.downloads(), base.dependents(),
			base.versionShare(), base.transitions(), base.removalReasons(), Set.of(ReportSection.FEATURES), null,
			featuresPayload());

		String html = new ReportHtmlRenderer().render(withFeatures);

		assertWellFormed(html);
		assertTrue(html.contains("기능 심화 분석"));
		assertFalse(html.contains("아직 제공되지 않습니다"), "payload 가 있는데도 자리표시만 그렸다");
		assertTrue(html.contains("구조화 로깅"));
		assertTrue(html.contains(">지원<"), "SUPPORTED 가 화면과 같은 한글로 안 나왔다");
		// pino 칸은 뒤에 "(AI 일반 지식)" 표시가 이어 붙으므로 닫는 태그(<)가 바로 오지 않는다.
		assertTrue(html.contains(">미확인 <"), "UNCONFIRMED 가 화면과 같은 한글로 안 나왔다");
		assertTrue(html.contains("AI 일반 지식"), "일반 지식으로만 답한 칸의 표시가 없다");
		assertTrue(html.contains("두 패키지 모두 구조화 로깅을 지원합니다"));
	}

	/** 문서 순서는 생태계 → 기능 비교 → 커뮤니티다 — 화면 탭 순서와 같다(S15P21A506-463). */
	@Test
	@DisplayName("기능 비교가 커뮤니티보다 먼저 나온다")
	void featuresComeBeforeCommunity() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("winston", "desc")), List.of()));
		var withBoth = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(), base.downloads(), base.dependents(),
			base.versionShare(), base.transitions(), base.removalReasons(),
			Set.of(ReportSection.FEATURES, ReportSection.COMMUNITY), null, featuresPayload());

		String html = new ReportHtmlRenderer().render(withBoth);

		assertWellFormed(html);
		int featuresAt = html.indexOf("기능 심화 분석");
		int communityAt = html.indexOf("커뮤니티 분석");
		assertTrue(featuresAt >= 0 && communityAt >= 0 && featuresAt < communityAt,
			"기능 심화 분석이 커뮤니티 분석보다 뒤에 나왔다");
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
		var unknownTransitions = TransitionsResponse.of("3y", null, null,
			List.of(TransitionsResponse.Series.unknown("consola", "regular",
				TransitionsResponse.NOT_COMPUTED)),
			List.of("nope-pkg"));

		String html = new ReportHtmlRenderer().render(new ReportHtmlRenderer.Sources(
			List.of("consola"), null, null, overview, emptyTrend, emptyTrend, emptyShare,
			unknownTransitions, Set.of()));

		assertWellFormed(html);
		assertTrue(html.contains("집계 대기"), "null 지표를 0 처럼 비워 두었다");
		assertTrue(html.contains("자료 없음"));
		assertTrue(html.contains("nope-pkg"), "못 찾은 이름이 문서에 없다");
		assertTrue(html.contains("준비 중"), "NOT_COMPUTED 를 0 처럼 비워 두었다");
	}

	/* ------------------------------------------------------------------ *
	 * 유지·유입·이탈 (S15P21A506-394)
	 * ------------------------------------------------------------------ */

	@Test
	@DisplayName("유입은 원시 inflow 가 아니라 inflow_adopted 를 메인으로 쓴다")
	void transitionsUseAdoptedInflow() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		// inflow=150, inflowNew=120 → inflowAdopted=30. 표에는 150 이 아니라 30 이 메인으로 보여야 한다.
		var transitions = TransitionsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(TransitionsResponse.Series.counted("express", "regular", 100, 150, 120, 10, 5, 2, 1, 2)),
			List.of());
		var sources = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(),
			base.downloads(), base.dependents(), base.versionShare(), transitions, Set.of());

		String html = new ReportHtmlRenderer().render(sources);

		assertWellFormed(html);
		assertTrue(html.contains("유지 · 유입 · 이탈"));
		assertTrue(html.contains(">30<"), "메인 유입 칸에 inflow_adopted(30) 이 없다");
		assertTrue(html.contains("원시 유입 150"), "원시 유입을 보조 설명으로 적지 않았다");
	}

	/**
	 * {@code OUT_OF_SCOPE} 를 0 으로 그리면 "아무도 안 쓴다" 는 거짓말이 된다 — 화면과 같은
	 * 규칙으로 {@code —} 와 사유 문구가 함께 있어야 한다.
	 */
	@Test
	@DisplayName("OUT_OF_SCOPE 는 0 이 아니라 대시와 사유로 적힌다")
	void transitionsMarkOutOfScope() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		var transitions = TransitionsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(TransitionsResponse.Series.unknown("express", "regular",
				TransitionsResponse.OUT_OF_SCOPE)),
			List.of());
		var sources = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(),
			base.downloads(), base.dependents(), base.versionShare(), transitions, Set.of());

		String html = new ReportHtmlRenderer().render(sources);

		assertWellFormed(html);
		assertTrue(html.contains("분석 대상 아님"));
		// 네 범주(유지·유입·이탈·릴리스 없음) 전부 "—" 여야 한다 — 0 으로 그리면 거짓말이 된다.
		assertEquals(4, html.split("<td class=\"n\">—</td>", -1).length - 1,
			"OUT_OF_SCOPE 인 네 칸이 전부 — 로 그려지지 않았다");
	}

	/* ------------------------------------------------------------------ *
	 * 이탈 사유 (S15P21A506-396·410)
	 * ------------------------------------------------------------------ */

	@Test
	@DisplayName("이탈 사유는 전이 건수와 대체 없이/함께 제거 비율을 함께 적는다")
	void removalReasonsRendersCountsAndPercent() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		var removalReasons = RemovalReasonsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(RemovalReasonsResponse.Series.counted("express", 1840, 1290, 550, 1622)),
			List.of());
		var sources = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(), base.downloads(), base.dependents(),
			base.versionShare(), base.transitions(), removalReasons, Set.of(), null, null);

		String html = new ReportHtmlRenderer().render(sources);

		assertWellFormed(html);
		assertTrue(html.contains("이탈 사유"));
		assertTrue(html.contains(">1,840<"), "이탈 전이 수가 없다");
		assertTrue(html.contains(">1,290<") && html.contains(">550<"), "대체 없이/함께 제거 수가 없다");
		assertTrue(html.contains("대체 없이 제거 70% · 다른 것과 함께 제거 30%"),
			"각자 반올림해 합이 100 이 아닌 비율이 나왔거나 비율 자체가 없다");
	}

	/**
	 * 운영 대상의 58.5%가 {@code NO_DATA} 다. {@code OUT_OF_SCOPE} 처럼 "분석 대상 아님" 으로
	 * 적으면 대부분의 패키지에 잘못된 문구가 붙는다 — 실제 값 0 으로, 좋은 소식으로 적어야 한다.
	 */
	@Test
	@DisplayName("이탈 사유의 NO_DATA 는 OUT_OF_SCOPE 처럼 적지 않고 실제 값 0 으로 적는다")
	void removalReasonsNoDataIsZeroNotOutOfScope() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		var removalReasons = RemovalReasonsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(RemovalReasonsResponse.Series.none("express")),
			List.of());
		var sources = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(), base.downloads(), base.dependents(),
			base.versionShare(), base.transitions(), removalReasons, Set.of(), null, null);

		String html = new ReportHtmlRenderer().render(sources);

		assertWellFormed(html);
		assertTrue(html.contains("이 기간에 뺀 프로젝트가 없습니다"));
		assertFalse(html.contains("분석 대상 아님"), "NO_DATA 를 OUT_OF_SCOPE 문구로 적었다");
	}

	@Test
	@DisplayName("이탈 사유의 OUT_OF_SCOPE 는 0 이 아니라 대시와 사유로 적힌다")
	void removalReasonsMarkOutOfScope() {
		var base = sources(new PackagesOverviewResponse(DAY, List.of(item("express", "desc")), List.of()));
		var removalReasons = RemovalReasonsResponse.of("3y", DAY.minusYears(3), DAY,
			List.of(RemovalReasonsResponse.Series.unknown("express", RemovalReasonsResponse.OUT_OF_SCOPE)),
			List.of("gone-pkg"));
		var sources = new ReportHtmlRenderer.Sources(
			base.names(), base.from(), base.to(), base.overview(), base.downloads(), base.dependents(),
			base.versionShare(), base.transitions(), removalReasons, Set.of(), null, null);

		String html = new ReportHtmlRenderer().render(sources);

		assertWellFormed(html);
		assertTrue(html.contains("분석 대상 아님"));
		assertTrue(html.contains("gone-pkg"), "못 찾은 이름이 문서에 없다");
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
