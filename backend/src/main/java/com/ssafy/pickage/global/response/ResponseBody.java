package com.ssafy.pickage.global.response;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public sealed abstract class ResponseBody<T> permits SuccessResponseBody, FailedResponseBody {
	private boolean success;
}
