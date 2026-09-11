package com.ssafy.pickage.domain.community;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.refresh.RefreshTrigger;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * Spec §2 — 명령(POST)과 조회(GET)를 분리한다(구현계획 §API "엔드포인트와 응답").
 *
 * <p>{@code name}·{@code trigger}는 {@code required} 기본값(true)을 그대로 둔다 — 둘 다
 * 없으면 스프링이 {@code MissingServletRequestParameterException}을 던지고
 * {@code GlobalExceptionHandler}가 이미 V001로 옮긴다. {@code trigger}가 {@link RefreshTrigger}
 * 값이 아니면 {@code MethodArgumentTypeMismatchException} → V004로 옮겨진다(같은 핸들러,
 * 날짜가 아닌 타입은 전부 V004). {@code PackageController}처럼 파라미터를 값 객체로 감싸
 * 직접 검증하지 않는 이유는 이 두 파라미터에는 3개 상한 같은 추가 규칙이 없어서다.
 *
 * <p>두 응답 모두 {@code no-store}를 붙인다 — 진행 상태·용량 초과 판정이 매 요청 달라질 수
 * 있어 캐시되면 안 된다(이 저장소에서 처음 추가하는 헤더, Spec §6).
 */
@Tag(name = "community", description = "GitHub 커뮤니티 현황 갱신·조회")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class CommunityController {

	private final CommunityService service;

	@Operation(summary = "커뮤니티 현황 조회",
		description = "진행 상태 또는 저장된 결과만 읽는다. 새 수집을 시작하지 않는다.")
	@GetMapping("/packages/community")
	public ResponseEntity<ApiResponseBody<CommunityStatusResponse>> getStatus(
		@RequestParam(name = "name") String name
	) {
		return noStore(HttpStatus.OK, service.getStatus(name));
	}

	@Operation(summary = "커뮤니티 현황 갱신",
		description = "새 작업을 수락하면 202, 이미 신선한 결과가 있거나 같은 작업에 참여하거나 "
			+ "용량이 초과되면 200이다.")
	@PostMapping("/packages/community/refresh")
	public ResponseEntity<ApiResponseBody<CommunityStatusResponse>> refresh(
		@RequestParam(name = "name") String name,
		@RequestParam(name = "trigger") RefreshTrigger trigger
	) {
		CommunityService.RefreshOutcome outcome = service.refresh(name, trigger);
		HttpStatus status = outcome.accepted() ? HttpStatus.ACCEPTED : HttpStatus.OK;
		return noStore(status, outcome.status());
	}

	private ResponseEntity<ApiResponseBody<CommunityStatusResponse>> noStore(
		HttpStatus status, CommunityStatusResponse body
	) {
		return ResponseEntity.status(status)
			.cacheControl(CacheControl.noStore())
			.body(ApiResponseUtil.createSuccessResponse(body));
	}
}
