package com.ssafy.pickage.global.response;

import lombok.Getter;

/**
 * 실패 응답 본문.
 *
 * <p>필드 이름은 {@code msg} 가 아니라 <b>{@code message}</b> 다. API 명세 0.3 이
 * {@code { "success": false, "code": "V001", "message": "" }} 로 정해 두었고,
 * 프론트의 {@code api/client.ts} 가 {@code body.message} 를 읽는다.
 * {@code msg} 로 두면 직렬화는 성공하고 화면에는 빈 메시지가 뜬다 —
 * 에러 없이 조용히 틀리는 쪽이라 눈에 잘 안 띈다.
 */
@Getter
public final class FailedResponseBody extends ApiResponseBody<Void> {
	private final String code;
	private final String message;

	public FailedResponseBody(String code, String message) {
		super(false);
		this.code = code;
		this.message = message;
	}
}
