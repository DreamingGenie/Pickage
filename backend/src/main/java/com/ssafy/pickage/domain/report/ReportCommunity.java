package com.ssafy.pickage.domain.report;

import static com.ssafy.pickage.domain.report.ReportHtmlRenderer.esc;

import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.TreeSet;

import com.ssafy.pickage.domain.community.DataStatus;
import com.ssafy.pickage.domain.community.dto.CommunityResultResponse;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.dto.Freshness;
import com.ssafy.pickage.domain.community.dto.MessageResponse;
import com.ssafy.pickage.domain.community.dto.SummaryMarkResponse;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.dto.TopicResponse;

/**
 * 보고서의 <b>커뮤니티 분석</b> 구역(확장-03 · S15P21A506-414).
 *
 * <p>화면의 커뮤니티 탭(`result.tsx`·`thread.tsx`·`summary-marks.ts`)이 보여주는 것을 문서에 옮긴다 — 저장소,
 * 수치 네 칸, 핵심 논의, 실제 논의 흐름, 수집 기준과 한계. 화면과 같은 규칙을 따른다.
 *
 * <h2>새로 수집하지 않는다</h2>
 *
 * 저장된 스냅샷을 읽기만 한다({@code CommunityService#getStatus}). PDF 를 만드는 요청이 GitHub·GMS 호출을
 * 일으키면 문서 생성이 수십 초 걸리고, 그 사이 외부 호출 한도를 문서가 쓴다. 자료가 아직 없으면 그 사실을
 * 문서에 적는다 — 구역을 조용히 빼면 체크한 것이 사라진 이유를 알 수 없다.
 *
 * <h2>지키는 규칙</h2>
 *
 * <ul>
 *   <li><b>기준 패키지 하나만 다룬다</b>(`DEC-COMMUNITY-20260909-01`).</li>
 *   <li><b>링크를 넣지 않는다.</b> 저장소·작성자 식별자는 글자로만 쓴다(IA §1-14). 화면의 Issue 원문 링크 버튼은
 *       종이에서는 뜻이 없어 옮기지 않는다.</li>
 *   <li><b>수치가 없으면 0 이 아니라 {@code —}.</b> 저장소 전체 Issue 수는 못 구했거나 이전 스냅샷이면 비어 있다.</li>
 *   <li><b>요약이 실패한 Issue 도 자리를 남긴다.</b> 제목·수치만 있다고 적고 요약을 지어내지 않는다.</li>
 *   <li><b>상태는 색이 아니라 글자</b>(`열림`·`종료`, 역할 배지)로 말한다.</li>
 * </ul>
 */
final class ReportCommunity {

	private ReportCommunity() {
	}

	private static final DateTimeFormatter STAMP =
		DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm").withZone(ZoneOffset.UTC);
	private static final DateTimeFormatter DAY =
		DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(ZoneOffset.of("+09:00"));

	/** 검증에 실패해 논의를 아예 못 가져온 terminal 상태. 빈 목록을 "논의 없음" 으로 보여주지 않는다. */
	private static final Map<DataStatus, String> TERMINAL_MESSAGE = Map.of(
		DataStatus.UNVERIFIED_REPOSITORY, "공개 저장소 연결을 확인하지 못했습니다.",
		DataStatus.AMBIGUOUS_SCOPE, "이 패키지와 저장소의 연결이 모호해 범위를 확정하지 못했습니다.",
		DataStatus.UNSUPPORTED_HOST, "저장소가 GitHub가 아니어서 지원하지 않습니다.",
		DataStatus.NO_DISCUSSION_DATA, "최근 조회 기간 안에서 조건에 맞는 논의를 찾지 못했습니다.");

	private static final Map<String, String> ROLE_LABEL = Map.of(
		"ISSUE_AUTHOR", "작성자",
		"REPOSITORY_OWNER", "저장소 소유자",
		"ORGANIZATION_MEMBER", "조직 구성원",
		"COLLABORATOR", "협업자",
		"CONTRIBUTOR", "기여자");

	/** 문서에 이 구역의 자료가 실릴 수 있는가 — 저장된 결과가 있을 때만이다. */
	static boolean hasResult(CommunityStatusResponse status) {
		return status != null && status.result() != null;
	}

	/**
	 * 구역 전체. 제목은 호출하는 쪽이 이미 그린 뒤 이 메서드가 본문을 그린다.
	 *
	 * @param packageName 기준 패키지 이름(화면 제목과 같은 값)
	 */
	static void render(StringBuilder b, CommunityStatusResponse status, String packageName) {
		b.append("<p class=\"unit\">GitHub 공개 Issue의 핵심 논의와 실제 댓글 흐름 · 기준 패키지 ")
			.append(esc(packageName)).append(" 하나만 대상입니다</p>");

		if (!hasResult(status)) {
			note(b, emptyMessage(status));
			return;
		}

		CommunityResultResponse r = status.result();
		repositoryLine(b, r, status.freshness());

		String terminal = TERMINAL_MESSAGE.get(r.dataStatus());
		if (terminal != null) {
			note(b, terminal);
			limitations(b, r);
			return;
		}

		stats(b, r);
		topics(b, r);
		threads(b, r);
		limitations(b, r);
	}

	/** 자료가 없을 때의 안내. 아직 수집 전인지, 수집 중인지, 실패했는지를 가른다. */
	static String emptyMessage(CommunityStatusResponse status) {
		if (status == null) return "커뮤니티 자료를 불러오지 못했습니다. 잠시 뒤 다시 만들어 주세요.";
		return switch (status.viewStatus()) {
			case PROCESSING -> "커뮤니티 자료를 수집하는 중입니다. 수집이 끝난 뒤 다시 만들면 채워집니다.";
			case FAILED -> "커뮤니티 자료 수집이 실패했습니다. 화면의 GitHub 커뮤니티 탭에서 다시 수집한 뒤 만들어 주세요.";
			default -> "이 패키지의 커뮤니티 자료가 아직 수집되지 않았습니다. "
				+ "GitHub 커뮤니티 탭을 한 번 연 뒤 다시 만들면 채워집니다.";
		};
	}

	/* ------------------------------------------------------------------ *
	 * 조각
	 * ------------------------------------------------------------------ */

	private static void repositoryLine(StringBuilder b, CommunityResultResponse r, Freshness freshness) {
		String repo = r.repository() == null
			? "확인된 저장소 없음"
			: "github.com/" + r.repository().fullName();
		String fresh = freshness == Freshness.FRESH ? "최신" : "이전 자료(갱신 필요)";
		b.append("<table class=\"meta\"><tbody>");
		metaRow(b, "저장소", repo, true);
		metaRow(b, "자료 기준", STAMP.format(r.collectedAt()) + " UTC · " + fresh, false);
		b.append("</tbody></table>");
		if (r.repository() != null && r.repository().archived()) {
			note(b, "보관(archived)된 저장소입니다. 더 이상 활발히 관리되지 않을 수 있습니다.");
		}
	}

	/**
	 * 수치 네 칸. <b>왼쪽 두 칸은 저장소 전체, 오른쪽 두 칸은 핵심 논의(요약한 Issue)</b>다 — 화면과 같은 배치다.
	 * 두 범위가 섞이면 "4,320건" 과 "57개" 가 같은 범위로 읽힌다.
	 */
	private static void stats(StringBuilder b, CommunityResultResponse r) {
		Integer total = r.repository() == null ? null : r.repository().issueCount();
		Integer open = r.repository() == null ? null : r.repository().openIssueCount();
		var s = r.summary();

		b.append("<table class=\"kpi\"><tbody><tr>");
		kpi(b, "전체 Issue", count(total, "건"),
			total == null ? "이번 자료에는 집계되지 않았습니다" : "GitHub 저장소 전체");
		kpi(b, "열린 Issue", count(open, "건"),
			open == null ? "이번 자료에는 집계되지 않았습니다" : "현재 open 상태 전체");
		kpi(b, "핵심 논의 누적 댓글", group(s.commentCount()) + "개", topicComments(r.topics()));
		kpi(b, "핵심 논의 사용자 반응", group(s.reactionCount()) + "개", "GitHub 반응 합계");
		b.append("</tr></tbody></table>");
	}

	private static void kpi(StringBuilder b, String label, String value, String sub) {
		b.append("<td><p class=\"kl\">").append(esc(label)).append("</p><p class=\"kv\">")
			.append(esc(value)).append("</p><p class=\"ks\">").append(esc(sub)).append("</p></td>");
	}

	private static String topicComments(List<TopicResponse> topics) {
		if (topics.isEmpty()) return "—";
		List<String> parts = new ArrayList<>();
		for (TopicResponse t : topics) parts.add("#" + t.issueNumber() + " " + group(t.commentsCount()) + "개");
		return String.join(" · ", parts);
	}

	private static void topics(StringBuilder b, CommunityResultResponse r) {
		b.append("<h3>핵심 논의</h3>");
		b.append("<p class=\"unit\">GitHub 공개 Issue · 핵심 논지 요약</p>");
		for (TopicResponse t : r.topics()) {
			b.append("<div class=\"topic\">");
			b.append("<p class=\"tmeta\"><span class=\"mono\">#").append(t.issueNumber()).append("</span> · ")
				.append("OPEN".equals(t.state()) ? "열림" : "종료")
				.append(" · 댓글 ").append(group(t.commentsCount()))
				.append(" · 반응 ").append(group(t.reactionsCount())).append("</p>");

			boolean summarized = t.titleKo() != null && t.summaryKo() != null
				&& t.summaryStatus() != SummaryStatus.FAILED;
			b.append("<p class=\"ttitle\">").append(esc(summarized ? t.titleKo() : t.titleOriginal())).append("</p>");
			if (summarized) {
				b.append("<p class=\"torig\">원제목: ").append(esc(t.titleOriginal())).append("</p>");
				b.append("<p class=\"tsum\">").append(marked(t.summaryKo(), t.summaryMarks())).append("</p>");
			} else {
				// 요약을 지어내지 않는다 — 있는 것(제목·수치)만 보이고 없는 것은 없다고 적는다.
				b.append("<p class=\"note\">이 Issue는 확인된 제목·수치만 있고 한국어 요약은 아직 없습니다.</p>");
			}
			b.append("</div>");
		}
	}

	private static void threads(StringBuilder b, CommunityResultResponse r) {
		boolean any = r.topics().stream().anyMatch(t -> !t.messages().isEmpty());
		if (!any) return;

		b.append("<h3>실제 논의 흐름</h3>");
		b.append("<p class=\"unit\">원문 댓글의 핵심 논지를 한국어로 요약했습니다.</p>");
		for (TopicResponse t : r.topics()) {
			b.append("<div class=\"thread\"><p class=\"tmeta\"><span class=\"mono\">ISSUE #")
				.append(t.issueNumber()).append("</span></p>");
			if (t.messages().isEmpty()) {
				b.append("<p class=\"note\">보여 줄 대표 발화가 없습니다.</p>");
			}
			for (MessageResponse m : t.messages()) message(b, m);
			b.append("</div>");
		}
	}

	private static void message(StringBuilder b, MessageResponse m) {
		String role = m.role() == null ? null : ROLE_LABEL.get(m.role());
		b.append("<div class=\"msg\"><p class=\"mhead\"><span class=\"mono\">")
			.append(esc(m.authorLogin() == null ? "(알 수 없음)" : m.authorLogin())).append("</span>");
		if (role != null) b.append(" <span class=\"tag\">").append(esc(role)).append("</span>");
		if ("USER_SOLUTION".equals(m.kind())) b.append(" <span class=\"tag\">해결 방법 제시</span>");
		b.append(" · ").append(DAY.format(m.createdAt())).append("</p>");
		b.append("<p class=\"mtext\">").append(esc(m.text())).append("</p></div>");
	}

	private static void limitations(StringBuilder b, CommunityResultResponse r) {
		b.append("<h3>수집 기준과 한계</h3>");
		var limits = r.dataLimits();
		if (limits != null && limits.sourceNote() != null) note(b, limits.sourceNote());
		if (limits != null) {
			note(b, "최근 " + limits.lookbackDays() + "일에 갱신된 공개 Issue 중 최대 " + limits.maxIssues()
				+ "건을 고르고, Issue마다 댓글은 최대 " + limits.maxCommentsPerIssue() + "개까지 읽어 대표 발화를 최대 "
				+ limits.maxMessagesPerIssue() + "개 보여 줍니다.");
		}
		// 같은 문구를 두 번 적지 않는다.
		for (String m : new LinkedHashSet<>(r.limitations().stream().map(l -> l.message()).toList())) note(b, m);
	}

	/* ------------------------------------------------------------------ *
	 * 요약 강조 — summary-marks.ts
	 * ------------------------------------------------------------------ */

	/**
	 * 요약문에 강조를 입힌다. 핵심어는 굵게, 핵심 문장은 형광펜(배경)이다. 위치는 UTF-16 오프셋 {@code [start, end)} 이며
	 * 자바 {@code String} 과 같은 단위다. <b>어긋난 구간은 버리고 평문으로 보인다</b> — 강조는 읽기 보조라 요약을 깨뜨리지
	 * 않는다. 핵심어가 핵심 문장 안에 들어 있으면 둘 다 입는다.
	 */
	static String marked(String text, List<SummaryMarkResponse> marks) {
		if (text == null || text.isEmpty()) return "";
		List<SummaryMarkResponse> valid = marks == null ? List.of() : marks.stream()
			.filter(m -> m.start() >= 0 && m.start() < m.end() && m.end() <= text.length()
				&& ("KEY_TERM".equals(m.kind()) || "KEY_SENTENCE".equals(m.kind()))
				&& !text.substring(m.start(), m.end()).isBlank())
			.toList();
		if (valid.isEmpty()) return esc(text);

		TreeSet<Integer> cuts = new TreeSet<>(List.of(0, text.length()));
		for (var m : valid) {
			cuts.add(m.start());
			cuts.add(m.end());
		}
		List<Integer> points = new ArrayList<>(cuts);

		StringBuilder out = new StringBuilder();
		for (int i = 0; i < points.size() - 1; i++) {
			int from = points.get(i);
			int to = points.get(i + 1);
			boolean term = valid.stream().anyMatch(m -> "KEY_TERM".equals(m.kind()) && m.start() <= from && to <= m.end());
			boolean sentence = valid.stream()
				.anyMatch(m -> "KEY_SENTENCE".equals(m.kind()) && m.start() <= from && to <= m.end());
			String piece = esc(text.substring(from, to));
			if (term) piece = "<strong>" + piece + "</strong>";
			if (sentence) piece = "<span class=\"hl\">" + piece + "</span>";
			out.append(piece);
		}
		return out.toString();
	}

	/* ------------------------------------------------------------------ *
	 * 조각
	 * ------------------------------------------------------------------ */

	private static void note(StringBuilder b, String text) {
		b.append("<p class=\"note\">").append(esc(text)).append("</p>");
	}

	private static void metaRow(StringBuilder b, String label, String value, boolean mono) {
		b.append("<tr><th>").append(esc(label)).append("</th><td")
			.append(mono ? " class=\"mono\"" : "").append('>').append(esc(value)).append("</td></tr>");
	}

	/** 저장소 전체 수치. 없으면 0 이 아니라 {@code —} 다. */
	private static String count(Integer v, String unit) {
		return v == null ? "—" : group(v) + unit;
	}

	private static String group(long v) {
		return String.format(Locale.ROOT, "%,d", v);
	}

	static String css() {
		return """
			h3 { font-size: 11.5pt; margin: 16px 0 4px; -fs-page-break-min-height: 30mm; }
			table.kpi { margin: 8px 0 6px; }
			table.kpi td { width: 25%; padding: 8px 10px; }
			.kl { font-size: 9pt; color: #6b7280; margin: 0; }
			.kv { font-size: 16pt; font-weight: bold; margin: 2px 0; line-height: 1.2; }
			.ks { font-size: 8.5pt; color: #6b7280; margin: 0; }
			.topic, .thread { margin: 8px 0 12px; page-break-inside: avoid; }
			.tmeta { font-size: 9pt; color: #4b5563; margin: 0 0 2px; }
			.ttitle { font-size: 11.5pt; font-weight: bold; margin: 0; }
			.torig { font-size: 8.5pt; color: #6b7280; margin: 0 0 4px; }
			.tsum { margin: 4px 0; }
			.hl { background: #fef3c7; }
			.msg { margin: 0 0 6px; padding: 4px 8px; border-left: 2px solid #d1d5db; page-break-inside: avoid; }
			.mhead { font-size: 9pt; color: #4b5563; margin: 0; }
			.mtext { margin: 1px 0 0; }
			""";
	}
}
