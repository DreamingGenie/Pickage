package com.ssafy.pickage.domain.report;

import java.time.LocalDate;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Component;

import com.ssafy.pickage.domain.community.CommunityService;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.domain.packages.PackageService;
import com.ssafy.pickage.domain.packages.TransitionPeriod;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.report.dto.FeatureComparisonPayload;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 보고서 문서(PDF · HAND-OFF Markdown)가 <b>공통으로</b> 밟는 조회 단계.
 *
 * <h2>왜 뺐는가</h2>
 *
 * {@link ReportPdfService#generate}가 하던 "이름 검증 → 생태계 조회 → 커뮤니티/기능 비교
 * 고르기 → {@link ReportHtmlRenderer.Sources} 조립" 을 그대로 옮긴 것이다({@code S15P21A506-466}).
 * HTML(PDF)과 Markdown(HAND-OFF)은 <b>같은 재료</b>를 쓰고 그리는 방식만 다르다 — 조회 로직을
 * 두 번 쓰면 언젠가 한쪽만 고쳐져 두 문서가 다른 숫자를 말하게 된다(공통-R08). 동작은
 * {@code generate()} 안에 있던 것과 완전히 같다 — 자리만 옮겼다.
 *
 * <h2>구역 목록은 호출하는 쪽이 정한다</h2>
 *
 * PDF 는 사용자가 고른 구역(0개 이상)을, HAND-OFF 는 항상 {@code COMMUNITY}·{@code FEATURES}
 * 전부를 시도한다 — 그 차이는 여기 들어오기 전, {@code requested} 인자로 이미 결정돼 있다.
 * 이 클래스는 "고른 구역을 어떻게 채우는지" 만 안다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
class ReportSourcesAssembler {

	private final PackageService packages;
	private final CommunityService community;

	/**
	 * 채워진 재료 한 벌.
	 *
	 * @param sources           렌더러(HTML·Markdown 공용)가 받는 입력.
	 * @param communityStatus   {@code omitted} 계산에 쓴다({@link ReportPdfService#omitted}).
	 *                          {@code sources.community()} 와 같은 값이다 — 호출하는 쪽이
	 *                          매번 {@code sources} 에서 다시 꺼내지 않게 따로 둔다.
	 * @param features          {@code omitted} 계산에 쓴다. {@code sources.features()} 와 같다.
	 */
	record Assembled(
		ReportHtmlRenderer.Sources sources,
		CommunityStatusResponse communityStatus,
		FeatureComparisonPayload features
	) {
	}

	Assembled assemble(
		List<String> rawNames,
		LocalDate from,
		LocalDate to,
		LocalDate snapshotAt,
		String periodCode,
		Set<ReportSection> requested,
		FeatureComparisonPayload requestedFeatures
	) {
		// 이름 검증은 조회와 같은 규칙을 쓴다 — 상한·형식·중복 제거가 갈라지면
		// 화면에서는 되는 조합이 문서에서만 막힌다.
		PackageNames names = PackageNames.of(rawNames);

		PackagesOverviewResponse overview = packages.getOverview(names);

		// 이름이 하나도 살아남지 않으면 그릴 것이 없다. 빈 문서를 내보내면
		// 사용자는 "만들어졌다" 고 읽고 파일을 열어 보고서야 알게 된다.
		if (overview.items().isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING,
				"보고서를 만들 수 있는 패키지가 없습니다. 이름을 확인해 주세요.");
		}

		// period 검증은 조회(PackageController)와 같은 규칙을 쓴다. 유효하지 않은 값은
		// 여기서 400 으로 끝난다.
		TransitionPeriod period = TransitionPeriod.of(periodCode);

		// 커뮤니티 분석은 기준 패키지 하나만 대상이다(DEC-COMMUNITY-20260909-01). 저장된 스냅샷을 읽기만 한다 —
		// 문서를 만드는 요청이 GitHub·GMS 수집을 일으키지 않는다.
		CommunityStatusResponse communityStatus = requested.contains(ReportSection.COMMUNITY)
			? communityOf(overview.items().getFirst().name())
			: null;

		// 기능 비교는 서버가 조회하지 않는다 — 요청이 실어 보낸 세션 판정을 그대로 쓴다(구상안 §14.5).
		// FEATURES 를 고르지 않았으면 애초에 null 이라 문서는 그 구역을 그리지 않는다.
		FeatureComparisonPayload features = requested.contains(ReportSection.FEATURES)
			? requestedFeatures
			: null;

		ReportHtmlRenderer.Sources sources = new ReportHtmlRenderer.Sources(
			names.values(),
			from,
			to,
			overview,
			packages.getDownloadsTrend(names, from, to),
			packages.getDependentsTrend(names, from, to),
			packages.getVersionShare(names, snapshotAt),
			packages.getTransitions(names, period),
			packages.getRemovalReasons(names, period),
			requested,
			communityStatus,
			features);

		return new Assembled(sources, communityStatus, features);
	}

	/**
	 * 기준 패키지의 커뮤니티 상태. <b>어떤 실패도 문서 생성을 막지 않는다</b> — 커뮤니티는 고르는 구역이라 그 자료를 못
	 * 읽었다고 생태계 보고서까지 못 만들 이유가 없다. 못 읽었으면 {@code null} 이고 문서가 그 사실을 적는다.
	 */
	private CommunityStatusResponse communityOf(String baseName) {
		try {
			return community.getStatus(baseName);
		} catch (RuntimeException e) {
			log.warn("보고서 커뮤니티 구역: 저장된 자료를 읽지 못했습니다 ({})", e.getClass().getSimpleName());
			return null;
		}
	}
}
