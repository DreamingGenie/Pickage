package com.ssafy.pickage.domain.report;

import static com.ssafy.pickage.domain.report.ChartGeometry.SHARE_FILLS;
import static com.ssafy.pickage.domain.report.ReportHtmlRenderer.esc;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import com.ssafy.pickage.domain.report.ChartGeometry.Box;
import com.ssafy.pickage.domain.report.ChartGeometry.Domain;
import com.ssafy.pickage.domain.report.ChartGeometry.Line;
import com.ssafy.pickage.domain.report.ChartGeometry.Style;

/**
 * 보고서에 넣는 그래프. <b>서비스 화면과 같은 그림</b>을 문서에 옮긴다(공통-R08).
 *
 * <h2>왜 SVG 이고 글자는 HTML 인가</h2>
 *
 * 같은 HTML 을 브라우저(미리보기)와 PDF 변환기가 함께 그린다. 선·도넛은 SVG 로 그리면 둘 다 같은 도형을
 * 그린다. 그런데 <b>글자는 SVG 안에 넣지 않는다.</b> PDF 변환기가 SVG 의 글자를 그리려면 AWT 글꼴 시스템을
 * 타는데, 운영 컨테이너(JRE 만 든 이미지)에는 글꼴 설정이 없어 글자가 사라지거나 예외가 난다. 눈금·범례·
 * 도넛 가운데 숫자는 <b>HTML 을 절대 좌표로 얹어</b> 그린다 — 한글 글꼴은 이미 문서 전체가 쓰는 하나다.
 *
 * <p>막대(Version Share · 유지·유입·이탈)는 화면도 HTML/CSS 라서 그대로 옮겼다.
 *
 * <h2>XHTML 로 쓴다</h2>
 *
 * 변환기가 XML 파서를 쓴다({@link ReportHtmlRenderer} 참고). 태그는 반드시 닫고, 동적 값(이름·라벨)은
 * 예외 없이 {@code esc} 를 지난다.
 */
final class ReportCharts {

	private ReportCharts() {
	}

	/** 선그래프 크기(px). A4 본문 폭(178mm ≈ 672px)보다 조금 작다. */
	static final int WIDTH = 640;
	static final int HEIGHT = 208;

	/** 왼쪽은 눈금 라벨, 아래는 날짜 라벨 자리다. */
	private static final Box PLOT = new Box(48, 10, WIDTH - 48 - 12, HEIGHT - 10 - 22);

	private static final int Y_TICKS = 3;
	private static final int X_TICKS = 5;

	/* ------------------------------------------------------------------ *
	 * 선그래프
	 * ------------------------------------------------------------------ */

	/**
	 * 여러 패키지의 시계열을 한 그래프에 겹쳐 그린다. 그릴 점이 하나도 없으면 빈 문자열이다 — 호출하는 쪽이
	 * "자료 없음" 을 적는다.
	 *
	 * <p>세로축은 로그 눈금이다(화면과 같다). 자릿수가 다른 패키지를 한 그래프에서 비교하려는 것이라, 눈금 간격이
	 * 균등하지 않다는 것을 아래 주석 문장으로 문서에 남긴다({@link #LOG_NOTE}).
	 *
	 * @param lines 이미 시계열이 정렬된 선. 점이 없는 선은 그리지 않는다.
	 */
	static String lineChart(List<Line> lines, String ariaLabel) {
		List<Line> drawable = lines.stream().filter(l -> !l.points().isEmpty()).toList();
		if (drawable.isEmpty()) return "";

		Domain xd = ChartGeometry.extentX(drawable);
		Domain yd = ChartGeometry.extentY(drawable);

		StringBuilder b = new StringBuilder(4096);
		b.append("<div class=\"figure\">");
		legend(b, drawable);
		b.append("<div class=\"chart\" style=\"width:").append(WIDTH).append("px;height:").append(HEIGHT)
			.append("px\">");

		b.append("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"").append(WIDTH)
			.append("\" height=\"").append(HEIGHT).append("\" viewBox=\"0 0 ").append(WIDTH).append(' ')
			.append(HEIGHT).append("\" role=\"img\" aria-label=\"").append(esc(ariaLabel)).append("\">");

		List<Double> ticks = ChartGeometry.ticksY(yd, Y_TICKS);
		for (double t : ticks) {
			double y = ChartGeometry.scaleY(t, yd, PLOT);
			b.append("<line x1=\"").append(ChartGeometry.f2(PLOT.x())).append("\" y1=\"")
				.append(ChartGeometry.f2(y)).append("\" x2=\"").append(ChartGeometry.f2(PLOT.x() + PLOT.w()))
				.append("\" y2=\"").append(ChartGeometry.f2(y))
				.append("\" stroke=\"#E5E7EB\" stroke-width=\"1\"/>");
		}

		for (Line line : drawable) {
			Style st = ChartGeometry.style(line.tone());
			b.append("<path d=\"").append(ChartGeometry.buildLine(line.points(), xd, yd, PLOT))
				.append("\" fill=\"none\" stroke=\"").append(st.color()).append("\" stroke-width=\"1.6\"");
			if (st.dash() != null) b.append(" stroke-dasharray=\"").append(st.dash()).append('"');
			b.append(" stroke-linejoin=\"round\"/>");

			// 마지막 점 — 가장 최근 값이 어디인지. 점이 하나뿐인 선은 이것만 보인다.
			var last = line.points().getLast();
			b.append("<circle cx=\"").append(ChartGeometry.f2(ChartGeometry.scaleX(last.date().toEpochDay(), xd, PLOT)))
				.append("\" cy=\"").append(ChartGeometry.f2(ChartGeometry.scaleY(last.value(), yd, PLOT)))
				.append("\" r=\"2.4\" fill=\"").append(st.color()).append("\"/>");
		}
		b.append("</svg>");

		// 눈금·날짜는 HTML 로 얹는다 — 위 "왜 SVG 이고 글자는 HTML 인가" 참고.
		for (double t : ticks) {
			double y = ChartGeometry.scaleY(t, yd, PLOT);
			b.append("<span class=\"tick\" style=\"top:").append(ChartGeometry.f2(y - 5)).append("px\">")
				.append(esc(ChartGeometry.formatTick(t, yd, Y_TICKS))).append("</span>");
		}
		for (double[] tick : xTicks(xd)) {
			double x = ChartGeometry.scaleX(tick[0], xd, PLOT);
			b.append("<span class=\"xlab\" style=\"left:").append(ChartGeometry.f2(x - 20)).append("px\">")
				.append(esc(ChartGeometry.shortDate(LocalDate.ofEpochDay((long) tick[0]))))
				.append("</span>");
		}
		b.append("</div>");
		b.append("<p class=\"note\">").append(esc(LOG_NOTE)).append("</p>");
		b.append("</div>");
		return b.toString();
	}

	/** 그래프 아래에 붙이는 설명. 눈금 간격이 균등하지 않다는 것을 숨기지 않는다. */
	static final String LOG_NOTE =
		"세로 눈금은 로그 간격입니다 — 규모가 다른 패키지를 한 그래프에서 비교하기 위한 것이며, 눈금 사이가 같은 값 차이는 아닙니다.";

	/** 날짜 눈금. 시간축을 고르게 나누고 같은 라벨이 겹치면 뺀다. */
	private static List<double[]> xTicks(Domain xd) {
		List<double[]> out = new ArrayList<>();
		String prev = null;
		for (int i = 0; i < X_TICKS; i++) {
			double day = xd.lo() + (xd.hi() - xd.lo()) * i / (X_TICKS - 1);
			String label = ChartGeometry.shortDate(LocalDate.ofEpochDay(Math.round(day)));
			if (label.equals(prev)) continue;
			out.add(new double[] {Math.round(day)});
			prev = label;
		}
		return out;
	}

	/** 범례. 선 모양을 테두리로 그린다 — SVG 를 또 넣지 않고도 실선·파선·점선이 문서와 미리보기에서 같다. */
	private static void legend(StringBuilder b, List<Line> lines) {
		b.append("<p class=\"legend\">");
		for (Line line : lines) {
			Style st = ChartGeometry.style(line.tone());
			b.append("<span class=\"lg\"><span class=\"sw\" style=\"border-top:2px ")
				.append(st.cssBorder()).append(' ').append(st.color()).append("\"></span> ")
				.append("<span class=\"mono\">").append(esc(line.label())).append("</span>");
			if (line.tone() == 0) b.append(" <span class=\"tag\">기준</span>");
			b.append("</span>");
		}
		b.append("</p>");
	}

	/* ------------------------------------------------------------------ *
	 * Version Share
	 * ------------------------------------------------------------------ */

	/** 도넛 한 조각 = major 하나(또는 접힌 "기타"). {@code share} 는 0~1. */
	record ShareGroup(String label, double share) {
	}

	private static final int DONUT = 116;

	/** Version Share 도넛. 가운데에 가장 큰 몫과 그 라벨을 적는다. */
	static String donut(List<ShareGroup> groups, String ariaLabel) {
		if (groups.isEmpty()) return "";
		double c = DONUT / 2.0;
		double rOuter = DONUT / 2.0 - 2;
		double rInner = rOuter * 0.62;

		StringBuilder b = new StringBuilder(1024);
		b.append("<div class=\"donut\" style=\"width:").append(DONUT).append("px;height:").append(DONUT).append("px\">");
		b.append("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"").append(DONUT).append("\" height=\"")
			.append(DONUT).append("\" viewBox=\"0 0 ").append(DONUT).append(' ').append(DONUT)
			.append("\" role=\"img\" aria-label=\"").append(esc(ariaLabel)).append("\">");

		double start = 0;
		ShareGroup top = groups.getFirst();
		for (int i = 0; i < groups.size(); i++) {
			ShareGroup g = groups.get(i);
			String fill = SHARE_FILLS[i % SHARE_FILLS.length];
			if (g.share() > top.share()) top = g;
			if (g.share() >= 0.9999) {
				// 한 조각이 전부면 호의 시작과 끝이 같아 아무것도 그려지지 않는다 — 굵은 테두리의 고리로 그린다.
				// 흰 원을 얹어 구멍을 내지 않는다: 그 원이 가운데 글자(HTML)를 덮는다.
				b.append("<circle cx=\"").append(ChartGeometry.f2(c)).append("\" cy=\"").append(ChartGeometry.f2(c))
					.append("\" r=\"").append(ChartGeometry.f2((rOuter + rInner) / 2))
					.append("\" fill=\"none\" stroke=\"").append(fill).append("\" stroke-width=\"")
					.append(ChartGeometry.f2(rOuter - rInner)).append("\"/>");
			} else if (g.share() > 0) {
				b.append("<path d=\"")
					.append(ChartGeometry.donutArc(c, c, rOuter, rInner, start, start + g.share()))
					.append("\" fill=\"").append(fill).append("\" stroke=\"#FFFFFF\" stroke-width=\"1.5\"/>");
			}
			start += g.share();
		}
		b.append("</svg>");
		b.append("<span class=\"dpct\" style=\"top:").append(ChartGeometry.f2(c - 12)).append("px\">")
			.append(Math.round(top.share() * 100)).append("%</span>");
		b.append("<span class=\"dlab\" style=\"top:").append(ChartGeometry.f2(c + 4)).append("px\">")
			.append(esc(top.label())).append("</span>");
		b.append("</div>");
		return b.toString();
	}

	/** 몫 막대. 가장 큰 몫을 100% 로 잡는다(화면과 같다). */
	static String shareBars(List<ShareGroup> groups) {
		if (groups.isEmpty()) return "";
		double max = groups.stream().mapToDouble(ShareGroup::share).max().orElse(1);
		StringBuilder b = new StringBuilder(1024);
		b.append("<table class=\"bars\"><tbody>");
		for (int i = 0; i < groups.size(); i++) {
			ShareGroup g = groups.get(i);
			double width = max > 0 ? g.share() / max * 100 : 0;
			b.append("<tr><td class=\"bl mono\">").append(esc(g.label())).append("</td>")
				.append("<td class=\"bb\"><div class=\"track\"><div class=\"fill\" style=\"width:")
				.append(pct(width)).append("%;background:").append(SHARE_FILLS[i % SHARE_FILLS.length])
				.append("\"></div></div></td>")
				.append("<td class=\"bp mono\">").append(Math.round(g.share() * 100)).append("%</td></tr>");
		}
		b.append("</tbody></table>");
		return b.toString();
	}

	/* ------------------------------------------------------------------ *
	 * 유지 · 유입 · 이탈
	 * ------------------------------------------------------------------ */

	/** 네 범주. 항상 이 순서로 항상 넷 다 그린다 — 미관측을 빼면 유지율이 실제보다 높아 보인다. */
	private static final String[] CATEGORY_LABELS = {"유지", "유입", "이탈", "미관측"};

	/** 값 없는 행의 자리 폭(%). 0 폭으로 그리면 "아무도 안 쓴다" 는 거짓말이 된다. */
	private static final double PLACEHOLDER_WIDTH = 40;

	/**
	 * 네 범주 막대. {@code values} 는 유지·유입(채택)·이탈·미관측 순이며 {@code placeholder} 이면 값이 없는 것이다.
	 * {@code max} 는 비교 중인 전체 행에서 한 번 계산한 값이다 — 여기서 따로 잡으면 패키지끼리 길이를 비교할 수 없다.
	 *
	 * @param mode {@code COMPLETE}·{@code NO_DATA} 는 값으로, {@code OUT_OF_SCOPE} 는 옅은 자리로,
	 *             {@code NOT_COMPUTED} 는 점선 빈 틀로 그린다.
	 */
	static String transitionBars(Integer[] values, String mode, double max) {
		boolean outOfScope = "OUT_OF_SCOPE".equals(mode);
		boolean notComputed = "NOT_COMPUTED".equals(mode);
		boolean placeholder = outOfScope || notComputed;

		StringBuilder b = new StringBuilder(1024);
		b.append("<table class=\"bars\"><tbody>");
		for (int i = 0; i < CATEGORY_LABELS.length; i++) {
			Integer v = values[i];
			double width = placeholder
				? PLACEHOLDER_WIDTH
				: v != null && max > 0 ? Math.max(v / max * 100, v > 0 ? 2 : 0) : 0;
			b.append("<tr><td class=\"bl\">").append(CATEGORY_LABELS[i]).append("</td>")
				.append("<td class=\"bb\"><div class=\"track").append(notComputed ? " dashed" : "").append("\">");
			if (outOfScope) {
				b.append("<div class=\"fill ghost\" style=\"width:").append(pct(width)).append("%\"></div>");
			} else if (!notComputed) {
				b.append("<div class=\"fill\" style=\"width:").append(pct(width)).append("%;background:")
					.append(SHARE_FILLS[i]).append("\"></div>");
			}
			b.append("</div></td><td class=\"bp mono\">")
				.append(placeholder ? "—" : String.format(Locale.ROOT, "%,d", v == null ? 0 : v))
				.append("</td></tr>");
		}
		b.append("</tbody></table>");
		return b.toString();
	}

	private static String pct(double v) {
		return String.format(Locale.ROOT, "%.1f", v);
	}

	/** 그래프·막대에 쓰는 CSS. 문서 전체 CSS 에 이어 붙는다. */
	static String css() {
		return """
			.figure { margin: 6px 0 10px; page-break-inside: avoid; }
			.keep { page-break-inside: avoid; }
			.legend { margin: 0 0 4px; font-size: 9pt; color: #374151; }
			.lg { margin-right: 14px; white-space: nowrap; }
			.sw { display: inline-block; width: 24px; height: 0; vertical-align: middle; margin-right: 3px; }
			.tag { font-size: 7.5pt; background: #f3f4f6; color: #4b5563; padding: 0 4px; }
			.chart { position: relative; }
			.chart svg { position: absolute; left: 0; top: 0; }
			.tick { position: absolute; left: 0; width: 42px; text-align: right;
			        font-size: 7.5pt; line-height: 10px; color: #6b7280; }
			.xlab { position: absolute; top: 190px; width: 40px; text-align: center;
			        font-size: 7.5pt; line-height: 10px; color: #6b7280; }
			.donut { position: relative; }
			.donut svg { position: absolute; left: 0; top: 0; }
			.dpct { position: absolute; left: 0; width: 116px; text-align: center; font-size: 12pt;
			        font-weight: bold; line-height: 16px; }
			.dlab { position: absolute; left: 0; width: 116px; text-align: center; font-size: 7.5pt;
			        line-height: 10px; color: #6b7280; }
			table.bars { width: 100%; margin: 0; border-collapse: collapse; }
			table.bars td { border: none; padding: 2px 4px 2px 0; vertical-align: middle; }
			td.bl { width: 46px; font-size: 9pt; color: #4b5563; }
			td.bp { width: 54px; text-align: right; font-size: 9pt; color: #4b5563; }
			.track { height: 9px; background: #f1f5f9; }
			.track.dashed { background: transparent; border: 1px dashed #94a3b8; height: 7px; }
			.fill { height: 9px; }
			.fill.ghost { background: #cbd5e1; }
			""";
	}
}
