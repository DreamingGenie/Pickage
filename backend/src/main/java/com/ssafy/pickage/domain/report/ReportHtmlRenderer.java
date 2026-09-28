package com.ssafy.pickage.domain.report;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.springframework.stereotype.Component;

import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.packages.TransitionPeriod;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.RemovalReasonsResponse;
import com.ssafy.pickage.domain.packages.dto.TransitionsResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;
import com.ssafy.pickage.domain.report.ChartGeometry.Line;
import com.ssafy.pickage.domain.report.ChartGeometry.Pt;
import com.ssafy.pickage.domain.report.ReportCharts.ShareGroup;
import com.ssafy.pickage.domain.report.dto.FeatureComparisonPayload;

/**
 * 보고서를 HTML 로 그린다. <b>미리보기와 PDF 가 이 하나를 공유한다.</b>
 *
 * <p>모달은 이 HTML 을 그대로 띄우고, 다운로드는 {@link HtmlToPdf} 가 같은 HTML 을 변환한다.
 * 둘을 따로 그리면 언젠가 내용이 갈린다(공통-R08).
 *
 * <h2>그래프 위, 수치 표 아래</h2>
 *
 * 생태계 구역은 서비스 화면의 그래프를 먼저 놓고 그 아래에 구체적인 수치 표를 둔다(S15P21A506-414). 그래프는
 * {@link ReportCharts}, 커뮤니티 구역은 {@link ReportCommunity} 가 그린다. 조회 조건은 <b>화면의 기본값</b>이다 —
 * 전체 기간·매주. 의존 수는 Downloads 보다 먼저 나오고 실제값 그래프 아래에 변화율 그래프가 붙는다(S15P21A506-416).
 *
 * <h2>⚠ 레이아웃은 아직 임시다</h2>
 *
 * 구상안 §13.4 의 아홉 구역과 분할 규칙은 아직 반영하지 않았다. {@code ReportSnapshot} 도
 * 확정 전이라 지금 맞춰 그려도 다시 그리게 된다.
 *
 * <h2>구역 순서는 생태계 → 기능 비교 → 커뮤니티다</h2>
 *
 * 생태계(항상 포함)는 여기서 끝나고, "더할 구역"은 이 순서로 고정한다(S15P21A506-463). 화면
 * 탭 순서(생태계·기능 비교·커뮤니티)와 같게 둔 것 — 문서만 다른 순서면 같은 보고서를 두 번
 * 배우는 셈이 된다.
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
		// 의존 수가 Downloads 보다 먼저다 — 서비스가 가장 앞세우는 지표다(S15P21A506-416). 화면도 같은 순서다.
		// 제목은 화면과 같은 말이다 — 영어 "Dependents" 는 처음 보는 사람에게 무엇을 세는 값인지 전해지지
		// 않는다(S15P21A506-405). 단위 줄은 제목과 겹치지 않게 뜻을 풀어 쓰고, 버전별 합계라는 한계를 남긴다.
		// 그래프는 실제값 아래에 변화율을 함께 둔다 — 실제값은 절대 규모를, 변화율은 규모가 다른 패키지의 성장
		// 속도를 보여준다(S15P21A506-414·416).
		trend(b, "의존 수", "다른 패키지가 의존 목록에 적어 둔 횟수 · 버전별 합계", s.dependents(), s, true);
		trend(b, "Downloads", "주간 다운로드 · npm 공식 자료", s.downloads(), s, false);
		versionShare(b, s.versionShare());
		transitions(b, s.transitions());
		removalReasons(b, s.removalReasons());

		// 순서는 서버가 정한다 — 보내는 순서와 무관하게 문서 구성이 같다. 생태계 다음 기능 비교,
		// 그다음 커뮤니티다(화면 탭 순서와 같다, S15P21A506-463) — enum 선언 순서(COMMUNITY가 먼저)와
		// 다르므로 목록을 따로 둔다. 고른 구역은 채울 내용이 없어도 자리를 그린다. 빼버리면 체크한
		// 것이 문서에서 사라져 사용자가 실패로 읽는다.
		if (s.sections().contains(ReportSection.FEATURES)) {
			if (s.features() != null) features(b, s.features());
			else pending(b, ReportSection.FEATURES);
		}
		if (s.sections().contains(ReportSection.COMMUNITY)) community(b, s);

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
		metaRow(b, "조회 기간", period(s));
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
	 * 추이. <b>그래프를 위에, 구체적인 수치 표를 아래에</b> 둔다(S15P21A506-414).
	 *
	 * <p>그래프는 화면과 같은 규칙으로 그린다({@link ChartGeometry}) — 패키지별 한 줄이고, 의존 수는 버전별
	 * 시리즈를 날짜마다 더한 합계다(화면의 {@code TOTAL} 과 같다). 표는 그대로 남긴다: 그래프가 모양을, 표가 양 끝과 증감을
	 * 정확한 숫자로 말한다. 그릴 점이 없으면 그래프 자리에 그렇다고 적고 표도 "자료 없음" 을 그대로 낸다.
	 */
	private void trend(StringBuilder b, String title, String unit, TrendResponse trend, Sources s,
		boolean withChangeRate) {
		List<Line> lines = lines(trend, s);

		// 제목·단위·그래프를 한 덩어리로 묶는다 — 묶지 않으면 제목만 쪽 끝에 남고 그래프가 다음 쪽으로 넘어간다.
		b.append("<div class=\"keep\">");
		heading(b, title);
		b.append("<p class=\"unit\">").append(esc(unit)).append("</p>");

		String chart = ReportCharts.lineChart(lines, title + " 추이");
		if (chart.isEmpty()) {
			note(b, "그래프로 그릴 자료가 없습니다.");
		} else {
			if (withChangeRate) b.append("<p class=\"sub\">실제값</p>");
			b.append(chart);
		}
		b.append("</div>");

		// 변화율은 실제값 아래, 수치 표 위. 따로 묶어 쪽 경계에서 두 그래프가 서로를 끌고 넘어가지 않게 한다.
		if (withChangeRate) {
			String rate = ReportCharts.changeRateChart(lines, title + " 변화율");
			if (!rate.isEmpty()) {
				b.append("<div class=\"keep\"><p class=\"sub\">변화율</p>").append(rate).append("</div>");
			}
		}

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

		// 패키지마다 도넛과 막대. 화면은 카드 하나에 한 패키지씩이라 문서도 패키지별로 나눈다.
		for (var item : share.items()) {
			List<ShareGroup> groups = foldSlices(item.slices());
			if (groups.isEmpty()) continue;
			b.append("<div class=\"vsblock\"><p class=\"vsname mono\">").append(esc(item.name())).append("</p>")
				.append("<table class=\"vs\"><tbody><tr><td class=\"vd\">")
				.append(ReportCharts.donut(groups, item.name() + " Version Share"))
				.append("</td><td>").append(ReportCharts.shareBars(groups)).append("</td></tr></tbody></table></div>");
		}

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
	 * 유지·유입·이탈 (기능-08 · S15P21A506-361·391·394).
	 *
	 * <p>화면(`transitions-panel.tsx`)이 지킨 세 원칙을 문서에도 그대로 적용한다.
	 *
	 * <ul>
	 *   <li><b>네 범주를 모두 표에 낸다.</b> {@code unobserved} 를 빼거나 {@code retained} 에
	 *       합치면 유지율이 거짓으로 높게 보인다(1년 구간 기준 최대 75%p 차이).</li>
	 *   <li><b>유입은 {@code inflowAdopted} 를 쓴다.</b> 원시 {@code inflow} 를 그대로 적으면
	 *       신생 프로젝트(실측 93.8~97.5%)까지 "채택" 으로 읽혀 모든 패키지가 잘나가는
	 *       지표가 된다. 둘이 다를 때만 원시 값을 보조로 적는다.</li>
	 *   <li><b>{@code data_status} 로 0 과 "모름" 을 가른다.</b> {@code OUT_OF_SCOPE}·
	 *       {@code NOT_COMPUTED} 는 수를 {@code —} 로 적고 그 밑에 사유를 쓴다 — 0 으로 적으면
	 *       "아무도 안 쓴다" 는 거짓말이 된다.</li>
	 * </ul>
	 */
	private void transitions(StringBuilder b, TransitionsResponse t) {
		heading(b, "유지 · 유입 · 이탈");
		b.append("<p class=\"unit\">").append(esc(transitionsCaption(t))).append("</p>");
		transitionBars(b, t);

		b.append("<table><thead><tr><th>패키지</th><th>종류</th>")
			.append("<th class=\"n\">유지</th><th class=\"n\">유입</th>")
			.append("<th class=\"n\">이탈</th><th class=\"n\">릴리스 없음</th>")
			.append("</tr></thead><tbody>");

		if (t.series().isEmpty()) {
			b.append("<tr><td class=\"muted\" colspan=\"6\">자료 없음</td></tr>");
		}
		for (var series : t.series()) {
			b.append("<tr><td class=\"mono\">").append(esc(series.name())).append("</td>")
				.append("<td class=\"mono\">").append(esc(transitionKindLabel(series.kind())))
				.append("</td>");
			transitionCount(b, series.retained());
			transitionCount(b, series.inflowAdopted());
			transitionCount(b, series.outflow());
			transitionCount(b, series.unobserved());
			b.append("</tr>");

			String rowNote = transitionRowNote(series);
			if (rowNote != null) {
				b.append("<tr><td></td><td class=\"note\" colspan=\"5\">")
					.append(esc(rowNote)).append("</td></tr>");
			}
		}
		b.append("</tbody></table>");

		if (!t.notFound().isEmpty()) {
			note(b, "전환 자료를 찾지 못한 이름: " + String.join(", ", t.notFound()));
		}
		note(b, "devDependencies 는 포함하지 않습니다.");
	}

	private static String transitionsCaption(TransitionsResponse t) {
		String range = (t.t1() == null || t.t2() == null)
			? "적재 전 — 아직 이 구간이 계산되지 않았습니다"
			: t.t1() + " ~ " + t.t2();
		String population = t.series().isEmpty() ? null : t.series().getFirst().population();
		String caption = transitionPeriodLabel(t.period()) + " · " + range;
		return population == null ? caption : caption + " · " + transitionPopulationLabel(population);
	}

	private static String transitionPeriodLabel(String code) {
		return switch (code) {
			case "1y" -> "1년";
			case "3y" -> "3년";
			case "5y" -> "5년";
			default -> code;
		};
	}

	private static String transitionKindLabel(String kind) {
		return switch (kind) {
			case "regular" -> "일반";
			case "peer" -> "동반";
			case "optional" -> "선택";
			default -> kind;
		};
	}

	private static String transitionPopulationLabel(String population) {
		return TransitionsResponse.NPM_ALL.equals(population) ? "npm 전체 패키지" : population;
	}

	private void transitionCount(StringBuilder b, Integer value) {
		b.append("<td class=\"n\">").append(value == null ? "—" : group(value)).append("</td>");
	}

	/**
	 * {@code data_status} 별 사유, 또는 {@code COMPLETE} 인데 원시 유입과 채택 유입이 다를 때의
	 * 보조 설명. 둘 다 아니면 {@code null} — 그때는 수치 행만으로 충분하다.
	 */
	private static String transitionRowNote(TransitionsResponse.Series series) {
		return switch (series.dataStatus()) {
			case TransitionsResponse.NO_DATA -> "의존자 없음";
			case TransitionsResponse.OUT_OF_SCOPE -> "분석 대상 아님 · 다운로드 상위 10만 밖";
			case TransitionsResponse.NOT_COMPUTED -> "준비 중 — 아직 이 구간이 적재되지 않았습니다";
			default -> (series.inflow() != null && !series.inflow().equals(series.inflowAdopted()))
				? "원시 유입 " + group(series.inflow()) + " · 신규 " + group(series.inflowNew()) + "건 포함"
				: null;
		};
	}

	/**
	 * 이탈 사유 (기능-08 · S15P21A506-396·410).
	 *
	 * <p>{@link #transitions} 와 <b>단위가 다르다</b> — 여기는 패키지 수가 아니라 전이 건수다.
	 * 합치거나 나누지 않는다. 화면(`removal-reasons-panel.tsx`)과 같은 원칙을 문서에도 적용한다.
	 *
	 * <ul>
	 *   <li><b>네 막대가 아니라 누적 막대 하나다.</b> {@code noReplacement + withReplacement =
	 *       removals}(DB CHECK)이므로 비율이 이 지표의 결론이다.</li>
	 *   <li><b>{@code NO_DATA} 를 {@code OUT_OF_SCOPE} 처럼 그리지 않는다.</b> 운영 대상의
	 *       58.5%가 {@code NO_DATA} 라, 실제 값 0 으로 그리고 {@code OUT_OF_SCOPE} 만 회색
	 *       자리로 그린다.</li>
	 *   <li><b>구간 선택기를 두지 않는다.</b> 위 유지·유입·이탈과 같은 구간을 쓴다 — 캡션으로
	 *       그 사실을 밝힌다.</li>
	 * </ul>
	 */
	private void removalReasons(StringBuilder b, RemovalReasonsResponse r) {
		heading(b, "이탈 사유");
		b.append("<p class=\"unit\">").append(esc(removalReasonsCaption(r))).append("</p>");
		removalBars(b, r);

		b.append("<table><thead><tr><th>패키지</th>")
			.append("<th class=\"n\">이탈 전이</th><th class=\"n\">")
			.append(RemovalReasonsResponse.NO_REPLACEMENT_LABEL).append("</th><th class=\"n\">")
			.append(RemovalReasonsResponse.WITH_REPLACEMENT_LABEL)
			.append("</th><th class=\"n\">뺀 프로젝트</th>")
			.append("</tr></thead><tbody>");

		if (r.series().isEmpty()) {
			b.append("<tr><td class=\"muted\" colspan=\"5\">자료 없음</td></tr>");
		}
		for (var series : r.series()) {
			b.append("<tr><td class=\"mono\">").append(esc(series.name())).append("</td>");
			transitionCount(b, series.removals());
			transitionCount(b, series.noReplacement());
			transitionCount(b, series.withReplacement());
			transitionCount(b, series.dependents());
			b.append("</tr>");

			String rowNote = removalRowNote(series);
			if (rowNote != null) {
				b.append("<tr><td></td><td class=\"note\" colspan=\"4\">")
					.append(esc(rowNote)).append("</td></tr>");
			}
		}
		b.append("</tbody></table>");

		if (!r.notFound().isEmpty()) {
			note(b, "이탈 사유를 찾지 못한 이름: " + String.join(", ", r.notFound()));
		}
		note(b, "전이 건수 기준입니다 — 위 유지·유입·이탈의 패키지 수와 더하거나 나누면 안 됩니다.");
	}

	private static String removalReasonsCaption(RemovalReasonsResponse r) {
		String range = (r.t1() == null || r.t2() == null)
			? "적재 전 — 아직 이 구간이 계산되지 않았습니다"
			: r.t1() + " ~ " + r.t2();
		String population = r.series().isEmpty() ? null : r.series().getFirst().population();
		String caption = transitionPeriodLabel(r.period()) + " · " + range;
		return population == null ? caption : caption + " · " + transitionPopulationLabel(population);
	}

	/**
	 * {@code data_status} 별 사유, 또는 {@code COMPLETE} 일 때 두 칸의 비율.
	 * <b>각자 반올림하지 않는다</b> — 한쪽만 반올림하고 다른 쪽은 100 에서 빼야 합이 100 이 된다
	 * (화면 {@code RemovalBars} 와 같은 규칙).
	 */
	private static String removalRowNote(RemovalReasonsResponse.Series series) {
		return switch (series.dataStatus()) {
			case RemovalReasonsResponse.NO_DATA -> "이 기간에 뺀 프로젝트가 없습니다";
			case RemovalReasonsResponse.OUT_OF_SCOPE -> "분석 대상 아님 · 다운로드 상위 10만 밖";
			case RemovalReasonsResponse.NOT_COMPUTED -> "준비 중 — 아직 이 구간이 적재되지 않았습니다";
			default -> removalPercentNote(series);
		};
	}

	private static String removalPercentNote(RemovalReasonsResponse.Series series) {
		Integer total = series.removals();
		Integer no = series.noReplacement();
		if (total == null || no == null || total <= 0) return null;
		int noPercent = Math.round(no * 100f / total);
		return RemovalReasonsResponse.NO_REPLACEMENT_LABEL + " " + noPercent + "% · "
			+ RemovalReasonsResponse.WITH_REPLACEMENT_LABEL + " " + (100 - noPercent) + "%";
	}

	/**
	 * 이탈 사유 누적 막대. 패키지마다 한 칸이다 — {@link #transitionBars} 처럼 종류(일반·동반·선택)로
	 * 나뉘지 않는다. 원천이 {@code kind} 차원을 두지 않는다.
	 */
	private void removalBars(StringBuilder b, RemovalReasonsResponse r) {
		if (r.series().isEmpty()) return;

		double max = 0;
		for (var series : r.series()) {
			if (series.removals() != null) max = Math.max(max, series.removals());
		}

		for (var series : r.series()) {
			b.append("<div class=\"vsblock\"><p class=\"vsname mono\">").append(esc(series.name())).append("</p>")
				.append(ReportCharts.removalBar(series, max))
				.append("</div>");
		}
	}

	/**
	 * 커뮤니티 분석. 기준 패키지의 저장된 스냅샷을 그린다({@link ReportCommunity}). 자료가 아직 없으면 그 사실을 적는다.
	 */
	private void community(StringBuilder b, Sources s) {
		heading(b, ReportSection.COMMUNITY.label());
		String name = s.community() != null && s.community().packageName() != null
			? s.community().packageName()
			: s.names().isEmpty() ? "" : s.names().getFirst();
		ReportCommunity.render(b, s.community(), name);
	}

	/**
	 * 기능 심화 분석 (기능-10~13, S15P21A506-463).
	 *
	 * <p>세션이 보낸 완료 결과를 그대로 옮긴다 — 서버가 다시 분석하지 않는다(구상안 §14.5).
	 * 2026-09-22 판정표 대신 공통점 한 덩어리 + 패키지별 차이점 문단이다(화면과 같은 구성).
	 */
	private void features(StringBuilder b, FeatureComparisonPayload f) {
		heading(b, ReportSection.FEATURES.label());
		if (f.limited()) {
			note(b, "자료가 부족해 일부만 설명했어요.");
		}

		b.append("<div class=\"keep\"><p class=\"sub\">공통점</p><p>")
			.append(esc(blankToDash(f.common()))).append("</p></div>");

		b.append("<p class=\"sub\">차이점</p>");
		if (f.differences() == null || f.differences().isEmpty()) {
			note(b, "자료 없음");
			return;
		}
		for (var d : f.differences()) {
			b.append("<div class=\"keep\"><p><strong>").append(esc(d.packageName())).append("</strong> ")
				.append("<span class=\"muted\">").append(esc(d.version())).append("</span></p>")
				.append("<p>").append(esc(blankToDash(d.body()))).append("</p></div>");
		}
	}

	private static String blankToDash(String s) {
		return s == null || s.isBlank() ? "-" : s;
	}

	/**
	 * 유지·유입·이탈 막대. 패키지마다 일반·동반·선택 세 칸이다. <b>막대 길이는 비교 중인 모든 행에서 한 번 잡은 최댓값</b>을
	 * 기준으로 한다 — 행마다 따로 잡으면 패키지끼리 길이를 비교할 수 없다(화면과 같다).
	 */
	private void transitionBars(StringBuilder b, TransitionsResponse t) {
		if (t.series().isEmpty()) return;

		double max = 0;
		for (var series : t.series()) {
			if (isPlaceholder(series)) continue;
			for (Integer v : counts(series)) if (v != null) max = Math.max(max, v);
		}

		// 패키지 순서는 응답 순서 그대로, 종류는 일반 → 동반 → 선택.
		Map<String, Map<String, TransitionsResponse.Series>> byPackage = new LinkedHashMap<>();
		for (var series : t.series()) {
			byPackage.computeIfAbsent(series.name(), k -> new TreeMap<>(Comparator.comparingInt(ReportHtmlRenderer::kindOrder)))
				.put(series.kind(), series);
		}

		for (var entry : byPackage.entrySet()) {
			b.append("<div class=\"vsblock\"><p class=\"vsname mono\">").append(esc(entry.getKey())).append("</p>")
				.append("<table class=\"tk\"><tbody><tr>");
			for (var kind : entry.getValue().entrySet()) {
				var series = kind.getValue();
				b.append("<td><p class=\"kindname\">").append(esc(transitionKindLabel(series.kind()))).append("</p>")
					.append(ReportCharts.transitionBars(counts(series), series.dataStatus(), max));
				String rowNote = transitionRowNote(series);
				if (rowNote != null) b.append("<p class=\"note\">").append(esc(rowNote)).append("</p>");
				b.append("</td>");
			}
			b.append("</tr></tbody></table></div>");
		}
	}

	private static int kindOrder(String kind) {
		return switch (kind) {
			case "regular" -> 0;
			case "peer" -> 1;
			case "optional" -> 2;
			default -> 3;
		};
	}

	private static boolean isPlaceholder(TransitionsResponse.Series series) {
		return TransitionsResponse.OUT_OF_SCOPE.equals(series.dataStatus())
			|| TransitionsResponse.NOT_COMPUTED.equals(series.dataStatus());
	}

	/** 유지·유입(채택)·이탈·릴리스 없음 순. 유입은 원시가 아니라 채택 수다 — 표와 같은 기준이다. */
	private static Integer[] counts(TransitionsResponse.Series series) {
		return new Integer[] {series.retained(), series.inflowAdopted(), series.outflow(), series.unobserved()};
	}

	/**
	 * 화면이 그리는 선을 문서용으로 만든다. 패키지 하나가 한 줄이고, 같은 이름의 시리즈(의존 수는 major 별로 나뉘어 온다)는
	 * 날짜마다 더한다 — 화면의 {@code totalOf} 와 같다. 점이 없는 시리즈는 뺀다(0 으로 채우지 않는다).
	 *
	 * <p>선 모양은 <b>비교 순서</b>를 따른다. 0 번이 기준 패키지(실선)다 — 카드·범례·차트가 같은 순서를 쓴다.
	 */
	private static List<Line> lines(TrendResponse trend, Sources s) {
		Map<String, TreeMap<LocalDate, Long>> sums = new LinkedHashMap<>();
		for (var series : trend.series()) {
			if (series.points().isEmpty()) continue;
			var byDate = sums.computeIfAbsent(series.name(), k -> new TreeMap<>());
			for (var p : series.points()) byDate.merge(p.snapshotAt(), p.value(), Long::sum);
		}

		List<String> order = new ArrayList<>();
		for (var item : s.overview().items()) order.add(item.name());
		for (String name : s.names()) if (!order.contains(name)) order.add(name);

		List<Line> out = new ArrayList<>();
		for (var entry : sums.entrySet()) {
			int idx = order.indexOf(entry.getKey());
			List<Pt> points = new ArrayList<>();
			for (var p : entry.getValue().entrySet()) points.add(new Pt(p.getKey(), p.getValue()));
			out.add(new Line(entry.getKey(), idx < 0 ? out.size() : idx, points));
		}
		out.sort(Comparator.comparingInt(Line::tone));
		return out;
	}

	/**
	 * 큰 몫 다섯 개만 나누고 나머지는 "기타" 로 접는다(화면의 {@code foldSlices}). {@code pct} 는 서버가 준 값을 그대로
	 * 더한다 — 같은 비율을 두 곳에서 구하면 언젠가 다른 숫자가 나온다.
	 */
	private static List<ShareGroup> foldSlices(List<VersionShareResponse.Slice> slices) {
		if (slices.isEmpty()) return List.of();
		var sorted = new ArrayList<>(slices);
		sorted.sort((a, b) -> Long.compare(b.dependents(), a.dependents()));

		List<ShareGroup> groups = new ArrayList<>();
		double other = 0;
		for (int i = 0; i < sorted.size(); i++) {
			var sl = sorted.get(i);
			if (i < MAX_SLICES) groups.add(new ShareGroup(sl.major() + ".x", sl.pct().doubleValue() / 100));
			else other += sl.pct().doubleValue() / 100;
		}
		if (sorted.size() > MAX_SLICES) groups.add(new ShareGroup("기타", other));
		return groups;
	}

	private static final int MAX_SLICES = 5;

	/**
	 * 조회 기간. <b>조건을 주지 않았으면 서버가 가진 전 기간이다</b> — 화면의 기본값(전체 기간)과 같다. 예전에는 조건이
	 * 없을 때 "자료 없음 ~ 자료 없음" 으로 적혀, 자료가 있는데도 없는 것처럼 읽혔다. 실제 범위는 응답의 점에서 읽는다.
	 */
	private static String period(Sources s) {
		if (s.from() != null && s.to() != null) return s.from() + " ~ " + s.to();
		LocalDate lo = null;
		LocalDate hi = null;
		for (TrendResponse trend : List.of(s.downloads(), s.dependents())) {
			for (var series : trend.series()) {
				for (var p : series.points()) {
					if (lo == null || p.snapshotAt().isBefore(lo)) lo = p.snapshotAt();
					if (hi == null || p.snapshotAt().isAfter(hi)) hi = p.snapshotAt();
				}
			}
		}
		if (lo == null) return "자료 없음";
		return "전체 기간 · " + lo + " ~ " + hi + " (주간)";
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
	 * 첫 이름이 {@link HtmlToPdf#FAMILY} 와 <b>같아야 한다.</b> 다르면 PDF 에서 한글이
	 * 통째로 빠진다. 그래서 상수에서 끌어다 쓴다.
	 *
	 * <h2>같은 문서가 두 곳에서 같은 글꼴로 보여야 한다</h2>
	 *
	 * {@code ReportKorean} 은 <b>변환기에만 등록한 이름</b>이라 브라우저에는 없다. 그대로
	 * 두면 미리보기는 다음 차례인 시스템 폰트로 떨어져, 문서 내용은 같은데 <b>글꼴만 달라
	 * 보인다.</b>
	 *
	 * <p>그래서 화면용 웹폰트를 {@code @media screen} 안에 둔다. 변환기는 {@code print}
	 * 매체로 그리므로 이 블록을 아예 보지 않는다 — 있지도 않은 주소를 받으러 가지 않고,
	 * 브라우저만 내려받는다. 매체로 가르지 않으면 변환 때마다 실패하는 요청이 하나 생긴다.
	 *
	 * <p>주소가 상대 경로인 것이 중요하다. {@code srcDoc} 은 부모 문서를 기준으로 해석하므로
	 * 앱이 어느 주소에 있든 같은 오리진에서 받아 온다.
	 */
	private static String css() {
		return """
			@media screen {
			  @font-face {
			    font-family: 'PretendardScreen';
			    src: url('/fonts/Pretendard-Regular.woff2') format('woff2');
			    font-weight: 400;
			    font-display: swap;
			  }
			  @font-face {
			    font-family: 'PretendardScreen';
			    src: url('/fonts/Pretendard-Bold.woff2') format('woff2');
			    font-weight: 700;
			    font-display: swap;
			  }
			}
			@page { size: A4; margin: 18mm 16mm; }
			body { font-family: '%s', 'PretendardScreen', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
			       font-size: 11pt; line-height: 1.6; color: #111827; }
			h1 { font-size: 20pt; margin: 0 0 4px; }
			h2 { font-size: 13pt; margin: 22px 0 8px; padding-bottom: 4px;
			     border-bottom: 1px solid #d1d5db; -fs-page-break-min-height: 45mm; }
			.subject { font-size: 12pt; color: #374151; margin: 0 0 16px; }
			.unit { font-size: 9pt; color: #6b7280; margin: 0 0 6px; }
			.sub { font-size: 10pt; font-weight: bold; color: #374151; margin: 8px 0 0; }
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
			.vsblock { margin: 6px 0 10px; page-break-inside: avoid; }
			.vsname { font-size: 10pt; font-weight: bold; margin: 0 0 3px; }
			table.vs, table.tk { border: none; margin: 0; }
			table.vs td, table.tk td { border: none; padding: 0 12px 0 0; vertical-align: middle; }
			td.vd { width: 128px; }
			table.tk td { width: 33%%; vertical-align: top; }
			.kindname { font-size: 9pt; font-weight: bold; margin: 0 0 2px; }
			""".formatted(HtmlToPdf.FAMILY) + ReportCharts.css() + ReportCommunity.css();
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
		/** 유지·유입·이탈. 생태계와 같은 취급 — 고를 수 있는 구역이 아니라 항상 들어간다. */
		TransitionsResponse transitions,
		/**
		 * 이탈 사유(S15P21A506-396·410). {@code transitions} 와 짝이라 같은 취급이다 — 고를 수 있는
		 * 구역이 아니라 항상 들어간다. 단위가 다르니(전이 건수 vs 패키지 수) 응답도 따로 받는다.
		 */
		RemovalReasonsResponse removalReasons,
		/** 더하기로 고른 구역. 생태계는 여기 없다 — 언제나 들어가므로 고를 것이 아니다. */
		Set<ReportSection> sections,
		/**
		 * 기준 패키지의 커뮤니티 결과(저장된 스냅샷). {@code COMMUNITY} 를 고르지 않았으면 {@code null}. 고르고도 자료가
		 * 없으면 상태만 담긴 응답이다 — 구역은 그 사실을 적는다(S15P21A506-414).
		 */
		CommunityStatusResponse community,
		/**
		 * 세션이 들고 있던 완료 기능 비교 판정(요청 payload). {@code FEATURES} 를 고르지 않았거나
		 * 고르고도 아직 분석을 실행하지 않았으면 {@code null} — 그 구역은 {@code pending()} 자리로
		 * 그린다(S15P21A506-463, 구상안 §13.1·§14.5).
		 */
		FeatureComparisonPayload features
	) {

		/** 읽을 행이 하나도 없을 때. period 는 캡션이 null 스위치로 죽지 않도록 기본값을 채운다. */
		private static final RemovalReasonsResponse EMPTY_REMOVAL_REASONS = new RemovalReasonsResponse(
			RemovalReasonsResponse.METRIC, TransitionPeriod.DEFAULT.code(), null, null, List.of(), List.of());

		/** 이탈 사유·커뮤니티·기능 비교 자료 없이 만든다(그 구역들을 고르지 않았거나 아직 안 받은 문서). */
		public Sources(List<String> names, LocalDate from, LocalDate to, PackagesOverviewResponse overview,
			TrendResponse downloads, TrendResponse dependents, VersionShareResponse versionShare,
			TransitionsResponse transitions, Set<ReportSection> sections) {
			this(names, from, to, overview, downloads, dependents, versionShare, transitions,
				EMPTY_REMOVAL_REASONS, sections, null, null);
		}
	}
}
