package com.ssafy.pickage.domain.report;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Component;

import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;

/**
 * 보고서를 HTML 로 그린다. <b>미리보기와 PDF 가 이 하나를 공유한다.</b>
 *
 * <p>모달은 이 HTML 을 그대로 띄우고, 다운로드는 {@link HtmlToPdf} 가 같은 HTML 을 변환한다.
 * 둘을 따로 그리면 언젠가 내용이 갈린다(공통-R08).
 *
 * <h2>⚠ 레이아웃은 임시다</h2>
 *
 * 구상안 §13.4 의 여덟 구역과 분할 규칙은 아직 반영하지 않았다. 기능 비교가 없고
 * {@code ReportSnapshot} 도 확정 전이라 지금 맞춰 그려도 다시 그리게 된다.
 * <b>그래서 이 한 파일에 가둔다</b> — 갈아끼울 때 다른 곳을 건드리지 않도록.
 *
 * <h2>XHTML 로 쓴다</h2>
 *
 * 변환기가 XML 파서를 쓰므로 태그를 반드시 닫아야 한다. {@code <br>} 하나가 열려 있으면
 * 미리보기는 멀쩡한데 <b>PDF 변환만 실패</b>한다 — 원인을 찾기 어려운 종류의 고장이다.
 *
 * <h2>값은 전부 이스케이프한다</h2>
 *
 * {@code description} 은 npm 에서 온 남의 문자열이다. 그대로 끼워 넣으면 {@code <script>} 가
 * 모달 안에서 실행되고, {@code &} 하나만 있어도 XML 파싱이 깨져 PDF 변환이 실패한다.
 * <b>동적 값은 예외 없이 {@link #esc}</b> 를 지난다.
 */
@Component
public class ReportHtmlRenderer {

	private static final DateTimeFormatter STAMP =
		DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm").withZone(ZoneOffset.UTC);

	public String render(Sources s) {
		StringBuilder b = new StringBuilder(8192);
		b.append("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"UTF-8\"/>")
			.append("<title>").append(esc(title(s))).append("</title>")
			.append("<style>").append(css()).append("</style></head><body>");

		cover(b, s);
		overview(b, s.overview());
		trend(b, "Downloads", "주간 다운로드 · npm 공식 자료", s.downloads());
		trend(b, "Dependents", "의존 수 · 버전별 합계", s.dependents());
		versionShare(b, s.versionShare());

		// 고른 구역은 아직 채울 내용이 없어도 자리를 그린다. 빼버리면 체크한 것이
		// 문서에서 사라져 사용자가 실패로 읽는다.
		for (ReportSection section : s.sections()) {
			pending(b, section);
		}

		limits(b, s);

		b.append("</body></html>");
		return b.toString();
	}

	private static String title(Sources s) {
		return "Pickage 생태계 보고서 — " + String.join(" · ", s.names());
	}

	/* ------------------------------------------------------------------ *
	 * 구역
	 * ------------------------------------------------------------------ */

	private void cover(StringBuilder b, Sources s) {
		b.append("<header><h1>Pickage 생태계 보고서</h1>")
			.append("<p class=\"subject\">").append(esc(String.join(" · ", s.names()))).append("</p>")
			.append("</header>");

		b.append("<table class=\"meta\"><tbody>");
		metaRow(b, "조회 기간", date(s.from()) + " ~ " + date(s.to()));
		metaRow(b, "버전 분포 기준일", date(s.versionShare().snapshotAt()));
		metaRow(b, "생성 시각", STAMP.format(Instant.now()) + " UTC");
		b.append("</tbody></table>");
	}

	private void overview(StringBuilder b, PackagesOverviewResponse overview) {
		heading(b, "비교 대상");
		b.append("<table><thead><tr>")
			.append("<th>패키지</th><th>최신 버전</th>")
			.append("<th class=\"n\">주간 다운로드</th><th class=\"n\">별</th><th class=\"n\">열린 이슈</th>")
			.append("</tr></thead><tbody>");

		for (var item : overview.items()) {
			b.append("<tr><td class=\"mono\">").append(esc(item.name())).append("</td>")
				.append("<td class=\"mono\">").append(esc(item.latestVersion())).append("</td>")
				.append("<td class=\"n\">").append(esc(number(item.downloads()))).append("</td>")
				.append("<td class=\"n\">").append(esc(number(item.stars()))).append("</td>")
				.append("<td class=\"n\">").append(esc(number(item.openIssues()))).append("</td></tr>");
		}
		b.append("</tbody></table>");

		if (!overview.notFound().isEmpty()) {
			note(b, "찾지 못한 패키지: " + String.join(", ", overview.notFound()));
		}
	}

	/**
	 * 추이는 표로 낸다. <b>그래프가 아니다.</b>
	 *
	 * <p>구상안 §13.4 는 그래프를 요구하지만, 화면과 같은 그림을 여기서 다시 그리면 두 곳의
	 * 렌더링이 갈린다. 차트를 어떻게 옮길지는 {@code ReportSnapshot} 확정과 함께 정할 일이라
	 * 지금은 <b>양 끝과 증감</b>만 적는다.
	 */
	private void trend(StringBuilder b, String title, String unit, TrendResponse trend) {
		heading(b, title);
		b.append("<p class=\"unit\">").append(esc(unit)).append("</p>");
		b.append("<table><thead><tr><th>패키지</th><th>버전</th>")
			.append("<th class=\"n\">처음</th><th class=\"n\">마지막</th><th class=\"n\">증감</th>")
			.append("</tr></thead><tbody>");

		for (var series : trend.series()) {
			var points = series.points();
			b.append("<tr><td class=\"mono\">").append(esc(series.name())).append("</td>")
				.append("<td class=\"mono\">")
				.append(series.major() == null ? "전체" : esc(series.major()) + ".x")
				.append("</td>");

			if (points.isEmpty()) {
				// 자료가 없는 것과 0 은 다르다. 빈칸으로 두면 0 으로 읽힌다.
				b.append("<td class=\"n muted\" colspan=\"3\">자료 없음</td></tr>");
				continue;
			}
			long first = points.getFirst().value();
			long last = points.getLast().value();
			b.append("<td class=\"n\">").append(group(first)).append("</td>")
				.append("<td class=\"n\">").append(group(last)).append("</td>")
				.append("<td class=\"n\">").append(signed(last - first)).append("</td></tr>");
		}
		b.append("</tbody></table>");
	}

	private void versionShare(StringBuilder b, VersionShareResponse share) {
		heading(b, "Version Share");
		b.append("<p class=\"unit\">기준일 ").append(esc(date(share.snapshotAt()))).append("</p>");
		b.append("<table><thead><tr><th>패키지</th><th>major</th>")
			.append("<th class=\"n\">의존 수</th><th class=\"n\">비율</th></tr></thead><tbody>");

		for (var item : share.items()) {
			if (item.slices().isEmpty()) {
				b.append("<tr><td class=\"mono\">").append(esc(item.name())).append("</td>")
					.append("<td class=\"muted\" colspan=\"3\">자료 없음</td></tr>");
				continue;
			}
			for (var slice : item.slices()) {
				b.append("<tr><td class=\"mono\">").append(esc(item.name())).append("</td>")
					.append("<td class=\"mono\">").append(esc(slice.major())).append(".x</td>")
					.append("<td class=\"n\">").append(group(slice.dependents())).append("</td>")
					.append("<td class=\"n\">").append(esc(String.valueOf(slice.pct()))).append("%</td></tr>");
			}
		}
		b.append("</tbody></table>");
	}

	/**
	 * 아직 만들 수 없는 구역.
	 *
	 * <p>제목을 적고 비어 있는 이유를 쓴다. <b>빈 자리를 남기지 않는다</b> — 제목만 있고
	 * 아래가 비면 자료가 없는 것인지 잘린 것인지 읽는 사람이 알 수 없다.
	 */
	private void pending(StringBuilder b, ReportSection section) {
		heading(b, section.label());
		note(b, "이 구역은 아직 제공되지 않습니다. 해당 분석 기능이 준비되면 "
			+ "같은 조건으로 다시 만들었을 때 채워집니다.");
	}

	private void limits(StringBuilder b, Sources s) {
		heading(b, "자료 상태와 해석 한계");
		note(b, "의존 수는 버전별 합계입니다. 한 프로젝트가 여러 버전에 걸릴 수 있어 실제 사용처 "
			+ "수보다 큽니다. 기울기와 비율은 유효하지만 절대수를 \"N개 프로젝트가 사용\" 으로 "
			+ "읽으면 안 됩니다.");
		note(b, "\"자료 없음\" 으로 적힌 칸은 관측이 없다는 뜻이며 0 이 아닙니다.");
		note(b, "다운로드는 직전 7일 합계입니다.");
		if (s.overview().snapshotAt() == null) {
			note(b, "아직 첫 스냅샷을 받지 못했습니다. 자료가 쌓이는 중입니다.");
		}
	}

	/* ------------------------------------------------------------------ *
	 * 조각
	 * ------------------------------------------------------------------ */

	private void heading(StringBuilder b, String text) {
		b.append("<h2>").append(esc(text)).append("</h2>");
	}

	private void note(StringBuilder b, String text) {
		b.append("<p class=\"note\">").append(esc(text)).append("</p>");
	}

	private void metaRow(StringBuilder b, String label, String value) {
		b.append("<tr><th>").append(esc(label)).append("</th><td>")
			.append(esc(value)).append("</td></tr>");
	}

	/**
	 * 폰트 이름이 {@link HtmlToPdf#FAMILY} 와 <b>같아야 한다.</b> 다르면 PDF 에서 한글이
	 * 통째로 빠진다. 그래서 상수에서 끌어다 쓴다.
	 *
	 * <p>뒤에 시스템 폰트를 함께 적는 이유는 <b>미리보기 때문</b>이다. 브라우저에는 그 이름의
	 * 폰트가 없으므로, 없으면 다음 것으로 넘어가게 해 둬야 모달에서 글자가 깨지지 않는다.
	 */
	private static String css() {
		return """
			@page { size: A4; margin: 18mm 16mm; }
			body { font-family: '%s', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
			       font-size: 11pt; line-height: 1.6; color: #111827; }
			h1 { font-size: 20pt; margin: 0 0 4px; }
			h2 { font-size: 13pt; margin: 22px 0 8px; padding-bottom: 4px;
			     border-bottom: 1px solid #d1d5db; }
			.subject { font-size: 12pt; color: #374151; margin: 0 0 16px; }
			.unit { font-size: 9pt; color: #6b7280; margin: 0 0 6px; }
			.note { font-size: 9pt; color: #4b5563; margin: 4px 0; }
			table { width: 100%%; border-collapse: collapse; margin: 6px 0 12px; }
			th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left;
			         vertical-align: top; }
			thead th { background: #f3f4f6; font-size: 9pt; }
			table.meta { width: auto; }
			table.meta th { background: #f9fafb; font-weight: normal; color: #6b7280; }
			.n { text-align: right; }
			.mono { font-variant-numeric: tabular-nums; }
			.muted { color: #6b7280; }
			""".formatted(HtmlToPdf.FAMILY);
	}

	private static String date(LocalDate date) {
		return date == null ? "자료 없음" : date.toString();
	}

	/** {@code null} 은 0 이 아니다. 화면과 같은 규칙으로 "집계 대기" 로 적는다. */
	private static String number(Number value) {
		return value == null ? "집계 대기" : group(value.longValue());
	}

	private static String group(long value) {
		return String.format("%,d", value);
	}

	private static String signed(long delta) {
		if (delta == 0) return "0";
		return (delta > 0 ? "+" : "−") + group(Math.abs(delta));
	}

	/**
	 * <b>동적 값은 예외 없이 여기를 지난다.</b>
	 *
	 * <p>{@code &} 를 먼저 바꿔야 한다. 나중에 바꾸면 {@code <} 를 {@code &lt;} 로 만들며 넣은
	 * {@code &} 까지 다시 이스케이프해 {@code &amp;lt;} 가 된다.
	 */
	static String esc(String raw) {
		if (raw == null) return "";
		return raw.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
			.replace("\"", "&quot;")
			.replace("'", "&#39;");
	}

	/**
	 * 렌더러가 받는 재료.
	 *
	 * <p>조회 응답을 그대로 받는다. 중간 모델을 하나 더 두면 화면과 문서가 서로 다른 모양을
	 * 보게 되고, 그 사이에서 값이 갈릴 여지가 생긴다.
	 */
	public record Sources(
		List<String> names,
		LocalDate from,
		LocalDate to,
		PackagesOverviewResponse overview,
		TrendResponse downloads,
		TrendResponse dependents,
		VersionShareResponse versionShare,
		/** 더하기로 고른 구역. 생태계는 여기 없다 — 언제나 들어가므로 고를 것이 아니다. */
		Set<ReportSection> sections
	) {
	}
}
