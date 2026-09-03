package com.ssafy.pickage.global.response;

import lombok.Getter;

@Getter
public sealed abstract class ApiResponseBody<T> permits SuccessResponseBody, FailedResponseBody {
	private final boolean success;

	protected ApiResponseBody(boolean success) {
		this.success = success;
	}
}
