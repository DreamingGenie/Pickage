package com.ssafy.pickage.domain.ops;

import java.time.LocalDate;
import java.util.List;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.ops.dto.WeeklyRunResponse;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * 주간 수집 운영 API. <b>사용자용이 아니다.</b>
 *
 * <p><b>이 경로는 nginx 에서 막는다</b> — {@code deploy/prod/app/nginx/app.conf} 의
 * {@code location /api/v1/ops/} 가 외부를 거부하고, 운영자는 SSH 터널로 붙는다.
 * 백엔드에 Spring Security 가 없어서 자바 쪽에 인증 코드를 새로 들이는 대신 문 앞에서
 * 끊는다. 막지 않으면 <b>아무나 23시간짜리 수집 잡을 켤 수 있다.</b>
 *
 * <p>경로가 {@code /api} 로 시작하는 것은 nginx 가 경로를 고치지 않고 그대로 넘기기
 * 때문이다({@code deploy/prod/README.md}). {@code /v1/ops} 를 붙인 것은 이 API 가
 * 화면 명세의 계약 밖이라는 표시다 — 여기 응답 형태가 바뀌어도 프론트 계약은 영향받지
 * 않는다.
 *
 * <p><b>{@code @Hidden} 으로 OpenAPI 문서에서도 뺀다.</b> nginx 가 경로를 404 로 막아도
 * {@code /v3/api-docs} 와 {@code /swagger-ui/} 는 프록시되므로, 빼지 않으면 23시간짜리 잡을
 * 트리거하는 POST 의 경로와 메서드가 외부에 그대로 공개된다. 그러면 남는 방어가 nginx 규칙
 * 하나뿐이 되는데, 그 규칙은 재배포나 설정 병합으로 빠질 수 있다. 운영자는 Swagger 대신 이
 * 주석과 {@code pipeline/weekly/README.md} 를 본다.
 */
@Hidden
@Tag(name = "ops-weekly", description = "주간 수집 현황 조회와 수동 실행 요청 (운영자용)")
@RestController
@RequestMapping("/api/v1/ops/weekly")
@RequiredArgsConstructor
public class OpsWeeklyController {

	private final WeeklyIngestService service;

	@Operation(summary = "최근 회차 목록",
		description = "최신 주부터 거슬러 올라간다. 타이머가 한 번도 돌지 않아 상태 객체가 "
			+ "없는 주도 status=MISSING 으로 포함한다 — 저장된 것만 보여 주면 그 주가 "
			+ "화면에서 사라지는데, 그게 가장 알아야 할 주다.")
	@GetMapping("/runs")
	public ApiResponseBody<List<WeeklyRunResponse>> listRuns(
		@RequestParam(name = "weeks", required = false) Integer weeks
	) {
		return ApiResponseUtil.createSuccessResponse(service.recentRuns(weeks));
	}

	@Operation(summary = "회차 상세",
		description = "weekOf 는 그 주 월요일(deps.dev 스냅샷 날짜)이다. 다른 요일은 V004 로 거부한다.")
	@GetMapping("/runs/{weekOf}")
	public ApiResponseBody<WeeklyRunResponse> getRun(
		@PathVariable("weekOf") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate weekOf
	) {
		return ApiResponseUtil.createSuccessResponse(service.run(weekOf));
	}

	@Operation(summary = "수동 실행 요청",
		description = "요청 객체만 남긴다. 실제 실행은 data 노드 타이머가 다음 발화(최대 10분)에 "
			+ "집어 간다. 연속 실패로 BLOCKED 된 회차를 푸는 유일한 방법이다. 멱등 — 이미 "
			+ "대기 중이어도 200 이다. 아직 오지 않은 주와 다시 받을 수 있는 한계(18개월)를 "
			+ "넘긴 주는 V002 로 거부한다.")
	@PostMapping("/runs/{weekOf}/manual-request")
	public ApiResponseBody<WeeklyRunResponse> requestManualRun(
		@PathVariable("weekOf") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate weekOf
	) {
		return ApiResponseUtil.createSuccessResponse(service.requestManualRun(weekOf));
	}
}
