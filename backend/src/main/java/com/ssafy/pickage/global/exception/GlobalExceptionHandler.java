package com.ssafy.pickage.global.exception;

import java.time.LocalDate;
import java.time.temporal.Temporal;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotAcceptableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import lombok.extern.slf4j.Slf4j;

/**
 * 전역 예외 → 명세 0.3 봉투.
 *
 * <p>스프링이 던지는 예외를 명세 0.4 의 코드로 옮긴다. 옮기는 규칙이 핵심이다 —
 * 같은 400 이라도 <b>누락(V001)·상한(V002)·날짜(V003)·형식(V004)</b> 이 화면에서 서로 다르게
 * 쓰인다. 예컨대 V003 은 "날짜를 다시 고르세요" 로, V002 는 "선택을 줄이세요" 로 읽힌다.
 * 전부 하나의 코드로 묶으면 화면이 무엇을 안내해야 할지 알 수 없다.
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

	private static ResponseEntity<ApiResponseBody<Void>> respond(ExceptionType type) {
		return ResponseEntity.status(type.getStatus()).body(ApiResponseUtil.createFailureResponse(type));
	}

	private static ResponseEntity<ApiResponseBody<Void>> respond(ExceptionType type, String message) {
		return ResponseEntity.status(type.getStatus())
			.body(ApiResponseUtil.createFailureResponse(type, message));
	}

	/** 서비스가 규칙 위반을 직접 판단해 던진 것. 상한 초과(V002)가 대부분 여기로 온다. */
	@ExceptionHandler(BusinessException.class)
	public ResponseEntity<ApiResponseBody<Void>> businessException(BusinessException e) {
		return ResponseEntity.status(e.getExceptionType().getStatus())
			.body(ApiResponseUtil.createFailureResponse(e.getExceptionType(), e.getMessage()));
	}

	/** {@code names} · {@code q} 가 아예 안 온 경우. */
	@ExceptionHandler(MissingServletRequestParameterException.class)
	public ResponseEntity<ApiResponseBody<Void>> missingParameter(MissingServletRequestParameterException e) {
		return respond(ExceptionType.REQUIRED_PARAM_MISSING,
			"%s은(는) 필수입니다.".formatted(e.getParameterName()));
	}

	/**
	 * 타입 변환 실패.
	 *
	 * <p>대상 타입이 날짜면 V003, 아니면 V004 다. {@code from=2026/01/01} 처럼 스프링이
	 * {@code LocalDate} 로 못 바꾼 경우가 명세의 "날짜 형식 오류" 와 정확히 같은 상황이라,
	 * 여기서 갈라 두면 서비스가 날짜를 다시 검사하지 않아도 된다.
	 */
	@ExceptionHandler(MethodArgumentTypeMismatchException.class)
	public ResponseEntity<ApiResponseBody<Void>> typeMismatch(MethodArgumentTypeMismatchException e) {
		Class<?> required = e.getRequiredType();
		boolean isDate = required != null
			&& (LocalDate.class.isAssignableFrom(required) || Temporal.class.isAssignableFrom(required));

		return isDate
			? respond(ExceptionType.INVALID_DATE_FORMAT)
			: respond(ExceptionType.INVALID_VALUE_FORMAT, "%s 형식이 올바르지 않습니다.".formatted(e.getName()));
	}

	/** {@code @Valid} 위반 (요청 DTO). v1 은 GET 뿐이라 자주 오지는 않는다. */
	@ExceptionHandler(MethodArgumentNotValidException.class)
	public ResponseEntity<ApiResponseBody<Void>> beanValidation(MethodArgumentNotValidException e) {
		return respond(ExceptionType.INVALID_VALUE_FORMAT,
			e.getBindingResult().getAllErrors().getFirst().getDefaultMessage());
	}

	/**
	 * 컨트롤러 파라미터에 직접 붙인 제약({@code @Size}, {@code @Pattern} 등) 위반.
	 *
	 * <p>배치 입력의 상한·형식 검사를 어노테이션으로 걸면 여기로 온다. 다만 메시지만으로는
	 * 상한(V002)인지 형식(V004)인지 구분할 수 없어서, <b>상한 검사는 어노테이션이 아니라
	 * 서비스에서 {@link BusinessException} 으로 던지는 편이 낫다.</b>
	 */
	@ExceptionHandler(HandlerMethodValidationException.class)
	public ResponseEntity<ApiResponseBody<Void>> handlerValidation(HandlerMethodValidationException e) {
		return respond(ExceptionType.INVALID_VALUE_FORMAT, e.getAllErrors().getFirst().getDefaultMessage());
	}

	/** 본문 파싱 실패. v1 에는 요청 본문이 없어서 사실상 오지 않는다. */
	@ExceptionHandler(HttpMessageNotReadableException.class)
	public ResponseEntity<ApiResponseBody<Void>> unreadableBody(HttpMessageNotReadableException e) {
		return respond(ExceptionType.INVALID_VALUE_FORMAT, "요청 본문 형식이 올바르지 않습니다.");
	}

	/* ── 명세 밖: HTTP 프로토콜 수준 ─────────────────────────────── */

	@ExceptionHandler(HttpRequestMethodNotSupportedException.class)
	public ResponseEntity<ApiResponseBody<Void>> methodNotSupported(HttpRequestMethodNotSupportedException e) {
		return respond(ExceptionType.NOT_SUPPORTED_METHOD);
	}

	/**
	 * 기본 정적 리소스 매핑이 켜져 있을 때의 404.
	 * {@code spring.web.resources.add-mappings=false} 로 끄면 대신
	 * {@code NoHandlerFoundException} 을 받아야 한다.
	 */
	@ExceptionHandler(NoResourceFoundException.class)
	public ResponseEntity<ApiResponseBody<Void>> noResource(NoResourceFoundException e) {
		return respond(ExceptionType.RESOURCE_NOT_FOUND);
	}

	@ExceptionHandler(HttpMediaTypeNotSupportedException.class)
	public ResponseEntity<ApiResponseBody<Void>> mediaTypeNotSupported(HttpMediaTypeNotSupportedException e) {
		return ResponseEntity.status(ExceptionType.NOT_SUPPORTED_MEDIA_TYPE.getStatus())
			.headers(e.getHeaders())
			.body(ApiResponseUtil.createFailureResponse(ExceptionType.NOT_SUPPORTED_MEDIA_TYPE));
	}

	@ExceptionHandler(HttpMediaTypeNotAcceptableException.class)
	public ResponseEntity<ApiResponseBody<Void>> mediaTypeNotAcceptable(HttpMediaTypeNotAcceptableException e) {
		return ResponseEntity.status(ExceptionType.NOT_ACCEPTABLE_MEDIA_TYPE.getStatus())
			.headers(e.getHeaders())
			.body(ApiResponseUtil.createFailureResponse(ExceptionType.NOT_ACCEPTABLE_MEDIA_TYPE));
	}

	/**
	 * 마지막 그물.
	 *
	 * <p>원인은 <b>로그에만</b> 남긴다. 예외 메시지를 그대로 내보내면 SQL 조각이나 테이블 이름이
	 * 응답에 실려 나간다.
	 */
	@ExceptionHandler(Exception.class)
	public ResponseEntity<ApiResponseBody<Void>> unexpected(Exception e) {
		log.error("Unexpected server error", e);
		return respond(ExceptionType.INTERNAL_ERROR);
	}
}
