package com.ssafy.pickage.domain.packages;

import java.time.LocalDate;
import java.util.List;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.packages.dto.PackageSearchResponse;
import com.ssafy.pickage.domain.packages.dto.PackagesOverviewResponse;
import com.ssafy.pickage.domain.packages.dto.SimilarPackagesResponse;
import com.ssafy.pickage.domain.packages.dto.TrendResponse;
import com.ssafy.pickage.domain.packages.dto.VersionShareResponse;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * 패키지 조회 API.
 *
 * <p>경로는 {@code /api/**} 다. 프론트가 {@code VITE_API_BASE_URL=/api} 로 고정돼 있고,
 * dev 에서는 Vite proxy 가 {@code /api} 만 8080 으로 넘긴다.
 *
 * <p><b>지표별로 엔드포인트를 나눈 이유</b>(명세 §1) — 개요는 즉시 떠야 하고 차트는 늦어도
 * 된다. 묶으면 가장 느린 것에 전체가 묶이고, 차트 쿼리 하나가 실패하면 카드까지 안 뜬다.
 *
 * <p>모든 파라미터를 {@code required = false} 로 받는다. 누락 판정을 값 객체
 * ({@link PackageNames} · {@link SearchQuery})에 맡기기 위해서다. 스프링이 먼저 던지게 두면
 * V001 은 맞게 나가지만 문구가 엔드포인트마다 제각각이 된다.
 *
 * <p>날짜는 {@code LocalDate} 로 받는다. 형식이 틀리면 스프링이
 * {@code MethodArgumentTypeMismatchException} 을 던지고 전역 핸들러가 V003 으로 옮긴다 —
 * 그래서 서비스는 파싱된 날짜만 다루면 된다.
 */
@Tag(name = "packages", description = "npm 패키지 동향 조회")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class PackageController {

	private final PackageService service;

	/**
	 * 명세 §3 — 카드 헤더 + 현재값·증감.
	 *
	 * <p><b>이름을 경로가 아니라 쿼리 파라미터로 받는다</b>(0.1). 스코프 패키지가 이유다 —
	 * 경로 방식({@code /packages/@types/node})은 슬래시 때문에 {@code %2F} 인코딩이 필요하고
	 * Spring 은 인코딩된 슬래시를 기본으로 차단한다. 쿼리로 내리면
	 * {@code ?names=@types/node} 가 그대로 안전하다.
	 *
	 * <p>Spring 은 {@code ?names=a,b,c} 와 {@code ?names=a&names=b} 를 둘 다
	 * {@code List<String>} 으로 받는다. 클라이언트가 어느 형태로 보내도 이 코드는 같다.
	 */
	@Operation(summary = "패키지 개요",
		description = "이름 배열(최대 3개)로 조회한다. 일부가 없어도 200 이며 not_found 에 담긴다. "
			+ "패키지는 있으나 스냅샷이 없으면 items 에 포함되고 지표 필드만 null 이다.")
	@GetMapping("/packages")
	public ApiResponseBody<PackagesOverviewResponse> getOverview(
		@RequestParam(name = "names", required = false) List<String> names
	) {
		return ApiResponseUtil.createSuccessResponse(service.getOverview(PackageNames.of(names)));
	}

	/**
	 * 명세 §4 — 다운로드 추이.
	 *
	 * <p>값은 <b>주간</b>이다({@code unit: "weekly"}). 시리즈마다 길이가 다를 수 있으니
	 * 클라이언트는 x축을 인덱스가 아니라 {@code snapshot_at} 으로 잡아야 한다.
	 */
	@Operation(summary = "다운로드 추이",
		description = "from 생략 시 최신 스냅샷 기준 26주, to 생략 시 최신 스냅샷. 최대 104주.")
	@GetMapping("/packages/downloads")
	public ApiResponseBody<TrendResponse> getDownloadsTrend(
		@RequestParam(name = "names", required = false) List<String> names,
		@RequestParam(name = "from", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
		@RequestParam(name = "to", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to
	) {
		return ApiResponseUtil.createSuccessResponse(
			service.getDownloadsTrend(PackageNames.of(names), from, to));
	}

	/**
	 * 명세 §5 — 의존 수 추이.
	 *
	 * <p>{@code sum_over_versions: true} 가 붙는다. <b>버전별 합계라 실제 사용처 수보다 크다</b> —
	 * 기울기는 유효하지만 절대수는 부풀려져 있고, 패키지 간 절대수 비교도 왜곡될 수 있다
	 * (버전이 많은 패키지일수록 부풀림이 크다).
	 */
	@Operation(summary = "의존 수 추이",
		description = "스냅샷별로 전 버전의 dependents_count 를 합산한다. 절대수는 부풀려진 값이다.")
	@GetMapping("/packages/dependents")
	public ApiResponseBody<TrendResponse> getDependentsTrend(
		@RequestParam(name = "names", required = false) List<String> names,
		@RequestParam(name = "from", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
		@RequestParam(name = "to", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to
	) {
		return ApiResponseUtil.createSuccessResponse(
			service.getDependentsTrend(PackageNames.of(names), from, to));
	}

	/**
	 * 명세 §6 — major 별 의존 분포.
	 *
	 * <p>{@code pct} 는 <b>해당 패키지 안에서의</b> 비율이라 패키지별로 각각 100% 가 된다.
	 * 형식은 맞지만 데이터가 없는 {@code snapshot_at} 은 <b>에러가 아니라</b> 빈
	 * {@code slices} 다 — 형식 오류(V003)와 구분해야 한다.
	 */
	@Operation(summary = "버전 분포",
		description = "특정 시점의 major 별 의존 지분. snapshot_at 생략 시 최신 스냅샷. "
			+ "데이터가 없는 날짜는 200 에 빈 slices 로 나간다.")
	@GetMapping("/packages/version")
	public ApiResponseBody<VersionShareResponse> getVersionShare(
		@RequestParam(name = "names", required = false) List<String> names,
		@RequestParam(name = "snapshot_at", required = false)
		@DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate snapshotAt
	) {
		return ApiResponseUtil.createSuccessResponse(
			service.getVersionShare(PackageNames.of(names), snapshotAt));
	}

	/**
	 * 기능-03 · UC4 — 유사 패키지.
	 *
	 * <p><b>기준 패키지가 하나라 {@code names} 배열이 아니다.</b> "무엇의 대체재인가" 를 묻는
	 * 조회이므로 기준이 둘일 수 없다. 최대 3개 상한은 비교 화면의 규칙이라 여기와 무관하다.
	 *
	 * <p>요청 경로에 모델이 없다. 주간 배치가 미리 계산해 둔 것을 키 조회로 읽을 뿐이다.
	 *
	 * <p>후보가 없는 것과 이름이 없는 것을 구분한다 — 앞은 200 에 빈 배열과
	 * {@code data_status: NO_DATA}, 뒤는 {@code not_found} 다.
	 */
	@Operation(summary = "유사 패키지",
		description = "기준 패키지 하나의 대체 후보를 순위 순으로 반환한다. limit 기본 20, 최대 50. "
			+ "아직 계산되지 않았으면 200 에 빈 candidates 와 data_status=NO_DATA 로 나간다.")
	@GetMapping("/packages/similar")
	public ApiResponseBody<SimilarPackagesResponse> getSimilar(
		@RequestParam(name = "name", required = false) String name,
		@RequestParam(name = "limit", required = false) Integer limit
	) {
		return ApiResponseUtil.createSuccessResponse(service.getSimilar(SimilarQuery.of(name, limit)));
	}

	/**
	 * 명세 §2.4 — 사전에 없는 이름을 위한 서버 폴백.
	 *
	 * <p><b>접두사 검색만 한다.</b> 중간 일치는 v1 범위 밖이다 — {@code LIKE '%q%'} 로 바꾸면
	 * {@code idx_package_name_prefix} 가 죽고, 사전 배포도 접두사 전제로 설계돼 있다.
	 *
	 * <p>이름만 반환한다. 다운로드 순 정렬이라 배열 순서가 곧 인기순이고, 사전 파일과 형태가
	 * 같아 클라이언트가 두 결과를 그대로 합칠 수 있다.
	 */
	@Operation(summary = "패키지명 검색 (접두사)",
		description = "이름만 반환하며 순서가 곧 인기순이다. limit 기본 20, 최대 50.")
	@GetMapping("/packages/search")
	public ApiResponseBody<PackageSearchResponse> search(
		@RequestParam(name = "q", required = false) String q,
		@RequestParam(name = "limit", required = false) Integer limit
	) {
		return ApiResponseUtil.createSuccessResponse(service.search(q, limit));
	}
}
