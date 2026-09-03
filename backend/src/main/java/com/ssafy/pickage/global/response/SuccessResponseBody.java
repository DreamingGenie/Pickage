package com.ssafy.pickage.global.response;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;

@Getter
public final class SuccessResponseBody<T> extends ResponseBody<T> {
	@JsonInclude(JsonInclude.Include.NON_NULL)
	private final T data;

	public SuccessResponseBody() {
		data = null;
		this.setSuccess(true);
	}

	public SuccessResponseBody(T result) {
		this.data = result;
		this.setSuccess(true);
	}
}
