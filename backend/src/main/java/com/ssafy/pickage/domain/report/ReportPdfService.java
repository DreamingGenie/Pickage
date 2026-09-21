package com.ssafy.pickage.domain.report;

import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.community.CommunityService;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.domain.packages.PackageService;
import com.ssafy.pickage.domain.packages.TransitionPeriod;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.report.dto.PdfGenerateRequest;
import com.ssafy.pickage.domain.report.dto.PdfJobResponse;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * PDF 생성 (기능-14).
 *
 * <h2>화면이 준 숫자를 쓰지 않는다</h2>
 *
 * 요청은 <b>조건만</b> 받고 숫자는 여기서 다시 조회한다. 화면이 들고 있던 옛 응답이 문서에
 * 박히는 일을 막기 위해서다(공통-R08 — 화면과 PDF 결과가 일치해야 한다). 같은 조회 서비스를
 * 부르므로 {@code not_found} · 결측 처리도 화면과 같은 규칙을 탄다.
 *
 * <h2>지금은 동기다</h2>
 *
 * 구상안 v1 배포 결정은 생성 실행을 <b>#1 data worker</b> 에 두고 앱은 요청·상태·다운로드만
 * 맡긴다. 그 전달 방식이 {@code OPEN-SERVER-01} 로 열려 있어 여기서는 요청 안에서 만든다.
 * 대신 응답을 비동기 모양({@link PdfJobResponse})으로 두어, 워커로 옮길 때
 * <b>HTTP 계약과 화면이 그대로 남게</b> 했다.
 *
 * <h2>적격성 검사는 아직 없다</h2>
 *
 * 구상안 §13.2 의 {@code BLOCKED} 다섯 사유 중 셋은 기능 비교에 달려 있고, 그 기능이 아직
 * 없다. 지금 검사를 넣으면 <b>항상 BLOCKED 인 API</b> 가 되어 아무것도 확인할 수 없다.
 * 생태계 결과만으로 만들 수 있는 문서를 먼저 돌게 하고, 기능 비교가 붙을 때 적격성과
 * 문서 구역을 함께 더한다.
 *
 * <p>유지·유입·이탈도 같은 원칙이다 — {@code data_status}({@code NO_DATA}·{@code OUT_OF_SCOPE}·
 * {@code NOT_COMPUTED})는 §13.2 가 이미 "차단 사유가 아니다" 라고 못 박은 화면의 결측 상태들과
 * 같은 종류라 새 {@code BLOCKED} 사유를 추가하지 않는다. 문서에 상태를 그대로 적어 화면과
 * 같은 규칙을 따른다(S15P21A506-394).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ReportPdfService {

	private final PackageService packages;
	private final CommunityService community;
	private final ReportHtmlRenderer renderer;
	private final HtmlToPdf converter;
	private final PdfStore store;

	@Transactional(readOnly = true)
	public PdfJobResponse generate(PdfGenerateRequest request) {
		// 이름 검증은 조회와 같은 규칙을 쓴다 — 상한·형식·중복 제거가 갈라지면
		// 화면에서는 되는 조합이 PDF 에서만 막힌다.
		PackageNames names = PackageNames.of(request.names());

		PackagesOverviewResponse overview = packages.getOverview(names);

		// 이름이 하나도 살아남지 않으면 그릴 것이 없다. 빈 문서를 내보내면
		// 사용자는 "만들어졌다" 고 읽고 파일을 열어 보고서야 알게 된다.
		if (overview.items().isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING,
				"보고서를 만들 수 있는 패키지가 없습니다. 이름을 확인해 주세요.");
		}

		/*
		 * 고른 구역 중 지금 채울 수 있는 것이 하나도 없다.
		 *
		 * 그래도 요청을 거절하지 않는다 — 생태계는 언제나 들어가므로 문서는 성립한다.
		 * 대신 비운 구역을 응답과 문서 양쪽에 적어, 사용자가 체크한 것이 어디 갔는지 알게 한다.
		 */
		Set<ReportSection> requested = ReportSection.parse(request.sections());

		// period 검증은 조회(PackageController)와 같은 규칙을 쓴다 — 화면에서 되는 구간이
		// PDF 에서만 막히면 안 된다. 유효하지 않은 값은 여기서 400 으로 끝난다.
		TransitionPeriod period = TransitionPeriod.of(request.period());

		// 커뮤니티 분석은 기준 패키지 하나만 대상이다(DEC-COMMUNITY-20260909-01). 저장된 스냅샷을 읽기만 한다 —
		// 문서를 만드는 요청이 GitHub·GMS 수집을 일으키지 않는다.
		CommunityStatusResponse communityStatus = requested.contains(ReportSection.COMMUNITY)
			? communityOf(overview.items().getFirst().name())
			: null;

		ReportHtmlRenderer.Sources sources = new ReportHtmlRenderer.Sources(
			names.values(),
			request.from(),
			request.to(),
			overview,
			packages.getDownloadsTrend(names, request.from(), request.to()),
			packages.getDependentsTrend(names, request.from(), request.to()),
			packages.getVersionShare(names, request.snapshotAt()),
			packages.getTransitions(names, period),
			packages.getRemovalReasons(names, period),
			requested,
			communityStatus);

		// 한 번 그린 HTML 로 미리보기와 PDF 를 모두 만든다. 여기서 갈라지지 않는 것이
		// "본 것과 받은 것이 같다" 의 전부다.
		String html = renderer.render(sources);
		byte[] pdf = converter.convert(html);

		String id = UUID.randomUUID().toString().replace("-", "");
		PdfJobResponse meta = PdfStore.meta(id, fileName(names.values()), pdf.length,
			omitted(requested, communityStatus));
		store.save(id, html, pdf, meta);
		return meta;
	}

	/**
	 * 기준 패키지의 커뮤니티 상태. <b>어떤 실패도 문서 생성을 막지 않는다</b> — 커뮤니티는 고르는 구역이라 그 자료를 못
	 * 읽었다고 생태계 보고서까지 못 만들 이유가 없다. 못 읽었으면 {@code null} 이고 문서가 그 사실을 적는다.
	 */
	private CommunityStatusResponse communityOf(String baseName) {
		try {
			return community.getStatus(baseName);
		} catch (RuntimeException e) {
			log.warn("PDF 커뮤니티 구역: 저장된 자료를 읽지 못했습니다 ({})", e.getClass().getSimpleName());
			return null;
		}
	}

	/**
	 * <b>요청했지만 문서에 채우지 못한 구역.</b> 기능 심화 분석은 기능이 아직 없어서, 커뮤니티 분석은 저장된 자료가 아직
	 * 없어서 빈다. 커뮤니티 자료가 실렸으면 여기 넣지 않는다 — 화면이 "자리와 사유만 실렸다" 고 안내하는 대상이다.
	 */
	static List<String> omitted(Set<ReportSection> requested, CommunityStatusResponse communityStatus) {
		return requested.stream()
			.filter(section -> section != ReportSection.COMMUNITY || !ReportCommunity.hasResult(communityStatus))
			.map(Enum::name)
			.toList();
	}

	/** 미리보기 HTML. 다운로드할 PDF 와 같은 생성에서 나온 것이다. */
	public String html(String reportId) {
		return store.findHtml(reportId).orElseThrow(() ->
			new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "그런 보고서가 없습니다."));
	}

	public PdfJobResponse find(String reportId) {
		return store.findMeta(reportId).orElseThrow(() ->
			new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "그런 보고서가 없습니다."));
	}

	public byte[] file(String reportId) {
		return store.findFile(reportId).orElseThrow(() ->
			new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "그런 보고서가 없습니다."));
	}

	/**
	 * 구상안 §13.6 — {@code Pickage_winston-pino-bunyan_2026-09-04.pdf}
	 *
	 * <p>스코프 이름의 {@code @} 와 {@code /} 가 그대로 들어가면 일부 환경에서 저장이 막히거나
	 * 경로로 해석된다. 이름 규칙에 없는 문자는 {@code -} 로 바꾼다 — 파일명은 사람이 읽는
	 * 표시일 뿐이고, 원래 이름은 문서 안에 그대로 적혀 있다.
	 */
	static String fileName(List<String> names) {
		String joined = String.join("-", names).replaceAll("[^A-Za-z0-9._-]", "-");
		// 너무 길면 일부 파일 시스템에서 잘린다. 이름 부분만 자르고 날짜는 남긴다.
		if (joined.length() > 80) joined = joined.substring(0, 80);
		return "Pickage_" + joined + "_" + LocalDate.now() + ".pdf";
	}
}
