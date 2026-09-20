package com.ssafy.pickage.domain.report;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.DataStatus;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.CommunityResultResponse;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.dto.CommunitySummaryResponse;
import com.ssafy.pickage.domain.community.dto.DataLimitsResponse;
import com.ssafy.pickage.domain.community.dto.Freshness;
import com.ssafy.pickage.domain.community.dto.LimitationResponse;
import com.ssafy.pickage.domain.community.dto.MessageResponse;
import com.ssafy.pickage.domain.community.dto.RepositoryInfoResponse;
import com.ssafy.pickage.domain.community.dto.SummaryMarkResponse;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.dto.TopicResponse;
import com.ssafy.pickage.domain.community.dto.ViewStatus;

/**
 * 보고서의 커뮤니티 분석 구역(S15P21A506-414).
 *
 * <p>화면(`result.tsx`·`thread.tsx`·`summary-marks.ts`)과 같은 규칙을 지키는지 본다 — 저장소 전체 수치와 핵심 논의 수치의
 * 배치, 수치가 없을 때 0 이 아니라 {@code —}, 요약이 실패한 Issue 의 자리, 강조 구간, 링크 없음.
 */
class ReportCommunityTest {

	private static final Instant COLLECTED = Instant.parse("2026-09-19T18:31:00Z");

	private static RepositoryInfoResponse repo(Integer total, Integer open) {
		return new RepositoryInfoResponse("axios", "axios", "axios/axios", "PACKAGE_SCOPED", false, total, open);
	}

	private static TopicResponse topic(int number, String state, String titleKo, String summaryKo,
		SummaryStatus summaryStatus, List<MessageResponse> messages, List<SummaryMarkResponse> marks) {
		return new TopicResponse(number, state, COLLECTED, COLLECTED, "Original title " + number, titleKo, 110, 907,
			CommentCollectionStatus.COMPLETE, summaryStatus, summaryKo, messages, marks);
	}

	private static MessageResponse message(String login, String role, String kind, String text) {
		return new MessageResponse(login, role, kind, Instant.parse("2026-04-03T16:00:00Z"), text);
	}

	private static CommunityResultResponse result(DataStatus status, RepositoryInfoResponse repository,
		List<TopicResponse> topics, List<LimitationResponse> limitations) {
		long comments = topics.stream().mapToLong(TopicResponse::commentsCount).sum();
		long reactions = topics.stream().mapToLong(TopicResponse::reactionsCount).sum();
		return new CommunityResultResponse(UUID.randomUUID(), COLLECTED, COLLECTED.plusSeconds(86_400),
			COLLECTED.plusSeconds(604_800), status, SummaryStatus.READY, null, repository,
			new CommunitySummaryResponse(topics.size(), comments, reactions, 0), topics, limitations,
			new DataLimitsResponse("github-active-v1", 180, 2, 100, 4, "검증된 저장소의 선택된 이슈 최대 2개 기준입니다."));
	}

	private static CommunityStatusResponse status(CommunityResultResponse result, Freshness freshness) {
		return new CommunityStatusResponse("axios", ViewStatus.RESULT, freshness, null, result);
	}

	private static String render(CommunityStatusResponse s) {
		StringBuilder b = new StringBuilder();
		ReportCommunity.render(b, s, "axios");
		return b.toString();
	}

	private static CommunityStatusResponse sample() {
		return status(result(DataStatus.AVAILABLE, repo(4320, 342), List.of(
			topic(10636, "CLOSED", "npm 공급망 침해 사후 보고", "악성 배포가 유통됐다. 원인은 계정 탈취였다.",
				SummaryStatus.READY,
				List.of(message("jasonsaayman", "ISSUE_AUTHOR", "DISCUSSION", "공격이 진행됐다고 설명했다."),
					message("DigitalBrainJS", "COLLABORATOR", "USER_SOLUTION", "방어책을 제안했다.")),
				List.of(new SummaryMarkResponse(0, 12, "KEY_SENTENCE"), new SummaryMarkResponse(0, 2, "KEY_TERM"))),
			topic(5366, "OPEN", null, null, SummaryStatus.FAILED, List.of(), List.of())),
			List.of(new LimitationResponse("ISSUE_FILTERED", "수집 범위에 포함되지 않는 이슈를 제외했습니다.", null))),
			Freshness.FRESH);
	}

	/* ------------------------------------------------------------------ *
	 * 수치 네 칸
	 * ------------------------------------------------------------------ */

	@Test
	void 왼쪽_두_칸은_저장소_전체_오른쪽_두_칸은_핵심_논의다() {
		String html = render(sample());

		// 화면과 같은 순서 — 두 범위가 섞이면 "4,320건" 과 "1,014개" 가 같은 범위처럼 읽힌다.
		int total = html.indexOf("전체 Issue");
		int open = html.indexOf("열린 Issue");
		int comments = html.indexOf("핵심 논의 누적 댓글");
		int reactions = html.indexOf("핵심 논의 사용자 반응");
		assertThat(total).isPositive();
		assertThat(total).isLessThan(open);
		assertThat(open).isLessThan(comments);
		assertThat(comments).isLessThan(reactions);

		assertThat(html).contains(">4,320건<").contains(">342건<");
		assertThat(html).contains("GitHub 저장소 전체").contains("현재 open 상태 전체");
		assertThat(html).contains(">220개<").contains("#10636 110개 · #5366 110개");
		assertThat(html).contains(">1,814개<");
	}

	@Test
	void 저장소_수치가_없으면_0이_아니라_대시와_사유다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(null, null), List.of(
			topic(1, "OPEN", "제목", "요약이다.", SummaryStatus.READY, List.of(), List.of())), List.of()),
			Freshness.FRESH));

		assertThat(html).contains(">—<").contains("이번 자료에는 집계되지 않았습니다");
		assertThat(html).doesNotContain(">0건<");
	}

	@Test
	void 한쪽만_구했으면_그_칸만_채운다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(9876, null), List.of(), List.of()),
			Freshness.FRESH));

		assertThat(html).contains(">9,876건<");
		assertThat(html).containsOnlyOnce("이번 자료에는 집계되지 않았습니다");
	}

	@Test
	void 열린_Issue가_0건이면_0건이라_적는다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(500, 0), List.of(), List.of()), Freshness.FRESH));

		assertThat(html).contains(">0건<").doesNotContain("이번 자료에는 집계되지 않았습니다");
	}

	/* ------------------------------------------------------------------ *
	 * 핵심 논의 · 실제 논의 흐름
	 * ------------------------------------------------------------------ */

	@Test
	void 핵심_논의는_번호_상태_수치_제목과_요약을_적는다() {
		String html = render(sample());

		assertThat(html).contains("#10636").contains("종료 · 댓글 110 · 반응 907");
		assertThat(html).contains("npm 공급망 침해 사후 보고").contains("원제목: Original title 10636");
		assertThat(html).contains("#5366").contains("열림 · 댓글");
	}

	@Test
	void 요약이_실패한_Issue는_요약을_지어내지_않고_원제목과_안내를_적는다() {
		String html = render(sample());

		assertThat(html).contains("Original title 5366")
			.contains("확인된 제목·수치만 있고 한국어 요약은 아직 없습니다");
		// 실패한 Issue 에는 "원제목:" 부제도 붙지 않는다(원제목이 곧 제목이다).
		assertThat(html).doesNotContain("원제목: Original title 5366");
	}

	@Test
	void 실제_논의_흐름은_작성자_역할_배지와_해결_방법_표시를_글자로_적는다() {
		String html = render(sample());

		assertThat(html).contains("실제 논의 흐름").contains("ISSUE #10636");
		assertThat(html).contains(">작성자<").contains(">협업자<").contains(">해결 방법 제시<");
		// 발화 날짜는 한국 시간 기준이다(UTC 16:00 → 다음 날).
		assertThat(html).contains("2026-04-04");
	}

	@Test
	void 대표_발화가_없는_Issue는_그렇다고_적는다() {
		String html = render(sample());

		assertThat(html).contains("ISSUE #5366").contains("보여 줄 대표 발화가 없습니다");
	}

	@Test
	void 발화가_하나도_없으면_실제_논의_흐름_구역을_그리지_않는다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(
			topic(1, "OPEN", "제목", "요약이다.", SummaryStatus.READY, List.of(), List.of())), List.of()),
			Freshness.FRESH));

		assertThat(html).doesNotContain("실제 논의 흐름");
	}

	/* ------------------------------------------------------------------ *
	 * 요약 강조
	 * ------------------------------------------------------------------ */

	@Test
	void 핵심어는_굵게_핵심_문장은_형광펜이고_겹치면_둘_다_입는다() {
		String html = ReportCommunity.marked("악성 배포가 유통됐다. 원인은 계정 탈취였다.", List.of(
			new SummaryMarkResponse(0, 12, "KEY_SENTENCE"), new SummaryMarkResponse(0, 2, "KEY_TERM")));

		assertThat(html).isEqualTo(
			"<span class=\"hl\"><strong>악성</strong></span><span class=\"hl\"> 배포가 유통됐다.</span>"
				+ " 원인은 계정 탈취였다.");
	}

	@Test
	void 어긋난_강조_구간은_버리고_평문으로_보인다() {
		String text = "짧은 요약이다.";

		assertThat(ReportCommunity.marked(text, List.of(new SummaryMarkResponse(3, 999, "KEY_TERM")))).isEqualTo(text);
		assertThat(ReportCommunity.marked(text, List.of(new SummaryMarkResponse(5, 5, "KEY_TERM")))).isEqualTo(text);
		assertThat(ReportCommunity.marked(text, List.of(new SummaryMarkResponse(-1, 3, "KEY_TERM")))).isEqualTo(text);
		assertThat(ReportCommunity.marked(text, List.of(new SummaryMarkResponse(0, 3, "OTHER")))).isEqualTo(text);
		// 공백뿐인 구간에는 강조를 그리지 않는다.
		assertThat(ReportCommunity.marked("가 나", List.of(new SummaryMarkResponse(1, 2, "KEY_TERM")))).isEqualTo("가 나");
		assertThat(ReportCommunity.marked(text, null)).isEqualTo(text);
		assertThat(ReportCommunity.marked("", List.of())).isEmpty();
	}

	@Test
	void 강조_안의_글자도_이스케이프한다() {
		String html = ReportCommunity.marked("a <b> & c", List.of(new SummaryMarkResponse(2, 5, "KEY_TERM")));

		assertThat(html).contains("<strong>&lt;b&gt;</strong>").doesNotContain("<b>");
	}

	/* ------------------------------------------------------------------ *
	 * 자료가 없거나 종료 상태일 때
	 * ------------------------------------------------------------------ */

	@Test
	void 자료가_없으면_왜_없는지를_상태별로_적는다() {
		assertThat(render(new CommunityStatusResponse("axios", ViewStatus.IDLE, null, null, null)))
			.contains("아직 수집되지 않았습니다").contains("GitHub 커뮤니티 탭");
		assertThat(render(new CommunityStatusResponse("axios", ViewStatus.PROCESSING, null, null, null)))
			.contains("수집하는 중입니다");
		assertThat(render(new CommunityStatusResponse("axios", ViewStatus.FAILED, null, null, null)))
			.contains("실패했습니다");
		assertThat(render(null)).contains("불러오지 못했습니다");
	}

	@Test
	void 자료가_없어도_구역_설명과_기준_패키지는_적는다() {
		String html = render(new CommunityStatusResponse("axios", ViewStatus.IDLE, null, null, null));

		assertThat(html).contains("기준 패키지 axios 하나만 대상입니다");
	}

	@Test
	void 종료_상태는_빈_목록을_논의_없음으로_보이지_않고_이유를_적는다() {
		String html = render(status(result(DataStatus.UNVERIFIED_REPOSITORY, null, List.of(), List.of()),
			Freshness.FRESH));

		assertThat(html).contains("공개 저장소 연결을 확인하지 못했습니다").contains("확인된 저장소 없음");
		// 수치 칸과 논의는 그리지 않는다 — 없는 수치를 0 으로 보이지 않는다.
		assertThat(html).doesNotContain("전체 Issue").doesNotContain("핵심 논의 누적 댓글")
			.doesNotContain("<h3>핵심 논의</h3>");
		assertThat(ReportCommunity.hasResult(status(result(DataStatus.UNVERIFIED_REPOSITORY, null, List.of(),
			List.of()), Freshness.FRESH))).isTrue();
	}

	@Test
	void 논의가_없으면_그_사유를_적는다() {
		String html = render(status(result(DataStatus.NO_DISCUSSION_DATA, repo(800, 12), List.of(), List.of()),
			Freshness.FRESH));

		assertThat(html).contains("조건에 맞는 논의를 찾지 못했습니다").contains("github.com/axios/axios");
	}

	/* ------------------------------------------------------------------ *
	 * 형식
	 * ------------------------------------------------------------------ */

	@Test
	void 이전_자료는_갱신이_필요하다고_적는다() {
		assertThat(render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(), List.of()), Freshness.STALE)))
			.contains("이전 자료(갱신 필요)");
		assertThat(render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(), List.of()), Freshness.FRESH)))
			.contains("· 최신");
	}

	@Test
	void 링크를_넣지_않는다() {
		String html = render(sample());

		// 저장소·작성자 식별자는 글자로만 쓴다(IA §1-14). 종이에서는 링크가 뜻이 없다.
		assertThat(html).doesNotContain("<a ").doesNotContain("href=").doesNotContain("http://").doesNotContain("https://");
	}

	@Test
	void 수집_기준과_한계는_같은_문구를_한_번만_적는다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(), List.of(
			new LimitationResponse("SUMMARY_INPUT_LIMITED", "입력 한도로 원문 일부만 요약에 사용했습니다.", 1),
			new LimitationResponse("SUMMARY_INPUT_LIMITED", "입력 한도로 원문 일부만 요약에 사용했습니다.", 2))),
			Freshness.FRESH));

		assertThat(html).contains("수집 기준과 한계").containsOnlyOnce("입력 한도로 원문 일부만 요약에 사용했습니다.");
		assertThat(html).contains("최근 180일에 갱신된 공개 Issue 중 최대 2건");
	}

	@Test
	void 남의_문자열은_이스케이프한다() {
		String nasty = "<script>alert(1)</script> & \"q\"";
		String html = render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(
			topic(1, "OPEN", nasty, nasty, SummaryStatus.READY,
				List.of(message(nasty, "CONTRIBUTOR", "DISCUSSION", nasty)), List.of())), List.of()), Freshness.FRESH));

		assertThat(html).doesNotContain("<script>");
		assertThat(html).contains("&lt;script&gt;");
	}

	@Test
	void 알_수_없는_작성자는_대신_적는다() {
		String html = render(status(result(DataStatus.AVAILABLE, repo(1, 1), List.of(
			topic(1, "OPEN", "제목", "요약이다.", SummaryStatus.READY,
				List.of(message(null, null, "DISCUSSION", "삭제된 계정의 발화다.")), List.of())), List.of()),
			Freshness.FRESH));

		assertThat(html).contains("(알 수 없음)").contains("삭제된 계정의 발화다.");
	}
}
