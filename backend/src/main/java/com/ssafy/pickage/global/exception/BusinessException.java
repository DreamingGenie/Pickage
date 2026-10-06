package com.ssafy.pickage.global.exception;

import lombok.Getter;

/**
 * 규칙 위반. 코드는 {@link ExceptionType} 이 정하고, 문구는 상황이 정한다.
 *
 * <p>같은 V002 라도 화면에 필요한 안내가 다르다 —
 * "한 번에 최대 3개까지 조회할 수 있습니다" 와 "최대 104주까지 조회할 수 있습니다" 는
 * 사용자가 취해야 할 행동이 서로 다르다. 그래서 <b>메시지를 덮어쓸 수 있게</b> 둔다.
 * 덮어쓰지 않으면 열거형의 기본 문구가 나간다.
 */
@Getter
public class BusinessException extends RuntimeException {
	private final ExceptionType exceptionType;

	public BusinessException(ExceptionType exceptionType) {
		super(exceptionType.getMessage());
		this.exceptionType = exceptionType;
	}

	public BusinessException(ExceptionType exceptionType, String message) {
		super(message);
		this.exceptionType = exceptionType;
	}
}
