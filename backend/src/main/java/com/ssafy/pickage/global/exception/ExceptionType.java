package com.ssafy.pickage.global.exception;

import static org.springframework.http.HttpStatus.*;

import org.springframework.http.HttpStatus;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum ExceptionType {

	// common
	UNEXPECTED_SERVER_ERROR(INTERNAL_SERVER_ERROR, "C001", "예상치 못한 에러 발생"),
	BINDING_ERROR(BAD_REQUEST, "C002", "바인딩시 에러 발생"),
	ESSENTIAL_FIELD_MISSING_ERROR(BAD_REQUEST, "C003", "필수적인 필드 부재"),
	INVALID_JSON_FORMAT(BAD_REQUEST, "C004", "잘못된 JSON 데이터 형식"),
	NOT_SUPPORTED_METHOD(METHOD_NOT_ALLOWED, "C005", "허용되지 않은 http method 접근"),


	;

	private final HttpStatus status;
	private final String code;
	private final String message;
}
