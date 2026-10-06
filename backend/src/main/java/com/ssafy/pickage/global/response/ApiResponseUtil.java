package com.ssafy.pickage.global.response;

import com.ssafy.pickage.global.exception.ExceptionType;

public class ApiResponseUtil {
	public static ApiResponseBody<Void> createSuccessResponse() {
		return new SuccessResponseBody<>();
	}

	public static <T> ApiResponseBody<T> createSuccessResponse(T data) {
		return new SuccessResponseBody<>(data);
	}

	public static ApiResponseBody<Void> createFailureResponse(ExceptionType exceptionType) {
		return new FailedResponseBody(exceptionType.getCode(), exceptionType.getMessage());
	}

	public static ApiResponseBody<Void> createFailureResponse(ExceptionType exceptionType, String customMessage) {
		return new FailedResponseBody(exceptionType.getCode(), customMessage);
	}
}
