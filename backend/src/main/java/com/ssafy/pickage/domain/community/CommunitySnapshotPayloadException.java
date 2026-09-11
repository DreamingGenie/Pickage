package com.ssafy.pickage.domain.community;

/**
 * {@code result} JSONB 를 {@link com.ssafy.pickage.domain.community.payload.CommunityResultPayload}
 * 로 직렬화·역직렬화하는 데 실패했을 때.
 *
 * <p>이 Phase(314)는 이 예외를 던지기만 한다 — "지원하는 JSON 형식이 손상됐다"를 공개
 * 오류 코드({@code S001} 등)로 분류하는 것은 API 계층(Phase 4, {@code S15P21A506-317})의
 * 몫이다.
 */
public class CommunitySnapshotPayloadException extends RuntimeException {

	public CommunitySnapshotPayloadException(String message, Throwable cause) {
		super(message, cause);
	}
}
