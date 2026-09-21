package com.ssafy.pickage.domain.features;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.features.dto.FeatureRunResponse;
import com.ssafy.pickage.domain.features.dto.FeatureVersionsResponse;
import com.ssafy.pickage.domain.features.dto.PackageEnvResponse;
import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * 확장 보고서 2페이지 — 기능 비교 API.
 *
 * <p><b>스펙 표와 AI 비교를 나눈다</b>(기능-10-R06). 스펙 표는 키 조회라 즉시 뜨고, AI 비교는
 * LLM 생성이 붙어 분 단위로 간다. 묶으면 확인된 사실까지 생성이 끝날 때까지 못 보여 준다.
 *
 * <p>대상은 {@code refs} 로 받는다 — {@code 이름@버전}. 이름만 받고 백엔드가 최신을 고르지
 * 않는 이유는, 화면이 이미 버전 드롭다운을 갖고 있고(기능-10-R02) 재분석이 <b>고른 버전</b>
 * 으로 도는 기능이기 때문이다. 백엔드가 따로 고르면 화면이 보여 준 버전과 분석한 버전이
 * 달라질 수 있다.
 */
@Tag(name = "features", description = "기능 비교 (확장 보고서 2페이지)")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class FeatureController {

	private final PackageEnvService envService;
	private final FeatureRunService runService;

	/**
	 * 기능-10-R02 — 버전 드롭다운.
	 *
	 * <p>이름만 받는다({@code names}). 규칙은 다른 화면과 같다 — 최대 3개, 소문자 이름(V001 ·
	 * V002 · V004).
	 *
	 * <p>돌려주는 버전은 전부 소비 조건이 있는 것이라, 어느 것을 골라도 아래 {@code /env} 가
	 * 채워진다. 목록과 표가 같은 표({@code package_env})에서 나와야 "고를 수는 있는데 표가
	 * 비는" 버전이 생기지 않는다.
	 */
	@Operation(summary = "기능 비교 버전 목록",
		description = "패키지마다 소비 조건이 있는 최근 정식 버전 3개를 최신순으로 돌려준다. "
			+ "패키지는 있는데 고를 버전이 없으면 versions 가 빈 배열이다.")
	@GetMapping("/packages/versions")
	public ApiResponseBody<FeatureVersionsResponse> getVersions(
		@RequestParam(name = "names", required = false) List<String> names
	) {
		return ApiResponseUtil.createSuccessResponse(envService.getVersions(PackageNames.of(names)));
	}

	/**
	 * 기능-11-R01 — 첫 결과 카드.
	 *
	 * <p>일부가 없어도 200 이고 {@code not_found} 에 담긴다. 완료 판단이 "확인된 정보만 표시"
	 * 라, 한 버전의 자료가 없다고 카드 전체를 막으면 안 된다.
	 *
	 * <p><b>실행 조건({@code engines})은 응답에 없다.</b> 항목에는 있지만 수집에 포함되지
	 * 않았다. 빈 값으로 채워 보내면 "조건이 없다" 로 읽히므로 아예 싣지 않는다.
	 */
	@Operation(summary = "버전별 소비 조건",
		description = "이름@버전 배열(최대 3개). 모듈 방식·타입 동봉·직접/peer 의존 수를 돌려준다. "
			+ "없는 것은 not_found 에 담기고 200 이다.")
	@GetMapping("/packages/env")
	public ApiResponseBody<PackageEnvResponse> getEnv(
		@RequestParam(name = "refs", required = false) List<String> refs
	) {
		return ApiResponseUtil.createSuccessResponse(envService.getEnv(PackageRefs.of(refs)));
	}

	/**
	 * 기능-12·13 — 비교를 시작한다. 결과를 기다리지 않는다.
	 *
	 * <p>여기서 기다리면 nginx 가 60초에 끊는다. {@code runId} 를 받아 아래 조회로 물어본다.
	 *
	 * <p>동시에 도는 run 수에 상한이 있다. 넘으면 V002 로 되돌려 준다 — 눌렀는데 아무 일도
	 * 안 일어나는 것보다 낫다.
	 */
	@Operation(summary = "기능 비교 시작",
		description = "runId 를 돌려준다. 결과는 상태 조회로 받는다. 동시 실행 수를 넘으면 V002.")
	@PostMapping("/packages/feature-comparison")
	public ApiResponseBody<FeatureRunResponse> startComparison(
		@RequestParam(name = "refs", required = false) List<String> refs
	) {
		FeatureRunStore.Run run = runService.start(PackageRefs.of(refs));
		return ApiResponseUtil.createSuccessResponse(toResponse(run));
	}

	/**
	 * 기능-12·13 — 상태와 결과.
	 *
	 * <p>{@code status} 가 {@code COMPLETED} 일 때만 {@code result} 가 찬다. 실패는 200 에
	 * {@code FAILED} 로 나간다 — HTTP 오류로 내보내면 "서버가 죽었다" 와 "그 버전의 문헌이
	 * 아직 없다" 가 화면에서 같아 보인다.
	 *
	 * <p>재시작하면 진행 중이던 run 이 사라진다. 판정 결과를 서버에 영속화하지 않기로 한
	 * 결정({@code DEC-FEATURE-CACHE-20260917-01})의 결과이고, 그때는 404 다.
	 */
	@Operation(summary = "기능 비교 상태",
		description = "COMPLETED 면 result 가 찬다. 실패도 200 이며 status=FAILED · error_code 로 구분한다.")
	@GetMapping("/packages/feature-comparison/{runId}")
	public ApiResponseBody<FeatureRunResponse> getComparison(@PathVariable String runId) {
		return ApiResponseUtil.createSuccessResponse(toResponse(runService.get(runId)));
	}

	private static FeatureRunResponse toResponse(FeatureRunStore.Run run) {
		return FeatureRunResponse.of(
			run.runId(), run.status(), run.phase(), run.refs(),
			run.startedAt(), run.finishedAt(),
			run.result(), run.errorCode(), run.errorDetail());
	}
}
