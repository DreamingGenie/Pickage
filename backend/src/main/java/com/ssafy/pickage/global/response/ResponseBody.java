package com.ssafy.pickage.global.response;

import lombok.Getter;

@Getter
public sealed abstract class ResponseBody<T> permits SuccessResponseBody, FailedResponseBody {
	private final boolean success;

	protected ResponseBody(boolean success) {
		this.success = success;
	}
}
