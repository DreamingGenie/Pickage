package com.ssafy.pickage.global.response;

import lombok.Getter;

@Getter
public final class FailedResponseBody extends ResponseBody<Void> {
	private final String code;
	private final String msg;

	public FailedResponseBody(String code, String msg) {
		this.code = code;
		this.msg = msg;
		this.setSuccess(false);
	}
}
