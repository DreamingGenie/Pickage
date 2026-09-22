package com.ssafy.pickage.domain.summary;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.domain.summary.dto.EcosystemSummaryResponse;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

@Tag(name = "packages", description = "npm 패키지 동향 조회")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class EcosystemSummaryController {

	private final EcosystemSummaryService service;

	@Operation(summary = "생태계 요약 (실험)",
		description = "고른 패키지(최대 3개)의 공통 기능과 사용 흐름을 두 문장으로 요약한다. "
			+ "조합·기준일마다 한 번만 모델을 부르고 이후엔 캐시로 답한다. "
			+ "status 가 READY 가 아니면 common·ecosystem 이 없다.")
	@GetMapping("/packages/summary")
	public ApiResponseBody<EcosystemSummaryResponse> getSummary(
		@RequestParam(name = "names", required = false) List<String> names
	) {
		return ApiResponseUtil.createSuccessResponse(service.summarize(PackageNames.of(names)));
	}
}
