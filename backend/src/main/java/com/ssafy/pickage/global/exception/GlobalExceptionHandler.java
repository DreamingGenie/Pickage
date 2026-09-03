package com.ssafy.pickage.global.exception;

import org.springframework.http.HttpStatus;
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
// import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import com.ssafy.pickage.global.response.ResponseBody;
import com.ssafy.pickage.global.response.ResponseUtil;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@RequiredArgsConstructor
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

	@ExceptionHandler(BusinessException.class)
	public ResponseEntity<ResponseBody<Void>> businessException(BusinessException e) {
		ExceptionType exceptionType = e.getExceptionType();
		return ResponseEntity.status(exceptionType.getStatus()).body(ResponseUtil.createFailureResponse(exceptionType));
	}

	@ExceptionHandler(MethodArgumentNotValidException.class)
	public ResponseEntity<ResponseBody<Void>> methodArgumentNotValidException(MethodArgumentNotValidException e) {
		String customMessage = e.getBindingResult().getAllErrors().getFirst().getDefaultMessage();
		return ResponseEntity.status(ExceptionType.BINDING_ERROR.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.BINDING_ERROR, customMessage));
	}

	@ExceptionHandler(MissingServletRequestParameterException.class)
	public ResponseEntity<ResponseBody<Void>> handleMissingServletRequestParameterException(
		MissingServletRequestParameterException e) {
		return ResponseEntity.status(ExceptionType.ESSENTIAL_FIELD_MISSING_ERROR.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.ESSENTIAL_FIELD_MISSING_ERROR));
	}

	@ExceptionHandler(HttpMessageNotReadableException.class)
	public ResponseEntity<ResponseBody<Void>> handleHttpMessageNotReadableException(HttpMessageNotReadableException e) {
		return ResponseEntity.status(ExceptionType.INVALID_JSON_FORMAT.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.INVALID_JSON_FORMAT));
	}

	@ExceptionHandler(HttpRequestMethodNotSupportedException.class)
	public ResponseEntity<ResponseBody<Void>> handleHttpRequestMethodNotSupportedException(
		HttpRequestMethodNotSupportedException e) {
		return ResponseEntity.status(ExceptionType.NOT_SUPPORTED_METHOD.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.NOT_SUPPORTED_METHOD));
	}

	@ExceptionHandler(MethodArgumentTypeMismatchException.class)
	public ResponseEntity<ResponseBody<Void>> methodArgumentTypeMismatchException(
		MethodArgumentTypeMismatchException e) {
		String customMessage = e.getName() + " 형식이 올바르지 않습니다.";
		return ResponseEntity.status(ExceptionType.BINDING_ERROR.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.BINDING_ERROR, customMessage));
	}

	@ExceptionHandler(HandlerMethodValidationException.class)
	public ResponseEntity<ResponseBody<Void>> handlerMethodValidationException(
		HandlerMethodValidationException e) {
		String customMessage = e.getAllErrors().getFirst().getDefaultMessage();
		return ResponseEntity.status(ExceptionType.BINDING_ERROR.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.BINDING_ERROR, customMessage));
	}

	// 기본 정적 리소스 매핑이 활성화된 경우 사용하는 404 핸들러.
	// application.yaml에서 spring.web.resources.add-mappings=false로 설정하고 별도 리소스 핸들러도 없다면,
	// 이 메서드를 주석 처리하고 아래 handleNoHandlerFoundException 메서드와 해당 import의 주석을 해제한다.
	@ExceptionHandler(NoResourceFoundException.class)
	public ResponseEntity<ResponseBody<Void>> handleNoResourceFoundException(NoResourceFoundException e) {
		return ResponseEntity.status(ExceptionType.RESOURCE_NOT_FOUND.getStatus())
			.body(ResponseUtil.createFailureResponse(ExceptionType.RESOURCE_NOT_FOUND));
	}

	// 정적 리소스 매핑을 끈 경우 사용하는 404 핸들러.
	// 기본 매핑을 다시 활성화하면 이 메서드를 주석 처리하고 위 handleNoResourceFoundException을 사용한다.
	// @ExceptionHandler(NoHandlerFoundException.class)
	// public ResponseEntity<ResponseBody<Void>> handleNoHandlerFoundException(NoHandlerFoundException e) {
	// 	return ResponseEntity.status(ExceptionType.RESOURCE_NOT_FOUND.getStatus())
	// 		.body(ResponseUtil.createFailureResponse(ExceptionType.RESOURCE_NOT_FOUND));
	// }

	@ExceptionHandler(HttpMediaTypeNotSupportedException.class)
	public ResponseEntity<ResponseBody<Void>> handleHttpMediaTypeNotSupportedException(
		HttpMediaTypeNotSupportedException e) {
		return ResponseEntity.status(ExceptionType.NOT_SUPPORTED_MEDIA_TYPE.getStatus())
			.headers(e.getHeaders())
			.body(ResponseUtil.createFailureResponse(ExceptionType.NOT_SUPPORTED_MEDIA_TYPE));
	}

	@ExceptionHandler(HttpMediaTypeNotAcceptableException.class)
	public ResponseEntity<ResponseBody<Void>> handleHttpMediaTypeNotAcceptableException(
		HttpMediaTypeNotAcceptableException e) {
		return ResponseEntity.status(ExceptionType.NOT_ACCEPTABLE_MEDIA_TYPE.getStatus())
			.headers(e.getHeaders())
			.body(ResponseUtil.createFailureResponse(ExceptionType.NOT_ACCEPTABLE_MEDIA_TYPE));
	}

	@ExceptionHandler(Exception.class)
	public ResponseEntity<ResponseBody<Void>> exception(Exception e) {
		log.error("Unexpected server error", e);
		return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
			.body(ResponseUtil.createFailureResponse(ExceptionType.UNEXPECTED_SERVER_ERROR));
	}
}
