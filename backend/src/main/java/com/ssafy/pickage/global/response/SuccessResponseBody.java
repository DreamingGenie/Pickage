package com.ssafy.pickage.global.response;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;

@Getter
public final class SuccessResponseBody<T> extends ResponseBody<T> {
	@JsonInclude(JsonInclude.Include.NON_NULL)
	private final T data;

	public SuccessResponseBody() {
		super(true);
		data = null;
	}

	public SuccessResponseBody(T result) {
		super(true);
		this.data = result;
	}
}
