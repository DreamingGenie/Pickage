package com.ssafy.pickage.global.exception;

import static org.springframework.http.HttpStatus.*;

import org.springframework.http.HttpStatus;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 에러 코드.
 *
 * <p><b>V·S 코드는 API 명세 0.4 가 소유한다.</b> 프론트가 이 값을 보고 동작을 바꾼다 —
 * {@code api/client.ts} 의 {@code ApiError.isValidation} 이 코드가 {@code V} 로 시작하는지로
 * 재시도 여부를 가른다. 400 계열은 파라미터가 규칙을 어긴 것이라 다시 보내도 결과가 같기 때문이다.
 * 그러므로 <b>여기서 코드 문자열을 바꾸면 화면 동작이 바뀐다.</b> 명세를 먼저 고칠 것.
 *
 * <p>C 코드는 명세 밖이다. HTTP 프로토콜 수준의 오류(405·415·406·404)라서 정상적인
 * 클라이언트라면 마주칠 일이 없고, 명세에 자리가 없어 그대로 둔다. 사람이 URL 을 직접
 * 두드리거나 클라이언트에 버그가 있을 때만 나온다.
 */
@Getter
@AllArgsConstructor
public enum ExceptionType {

	/* ── API 명세 0.4 ────────────────────────────────────────────── */

	/** 필수 파라미터 누락. {@code names} 나 {@code q} 가 없거나 빈 문자열. */
	REQUIRED_PARAM_MISSING(BAD_REQUEST, "V001", "필수 파라미터가 누락되었습니다."),

	/**
	 * 개수·범위 상한 초과.
	 * {@code names} 3개 초과, 조회 기간 104주 초과, {@code limit} 50 초과.
	 */
	LIMIT_EXCEEDED(BAD_REQUEST, "V002", "요청 가능한 범위를 넘었습니다."),

	/** 날짜 형식 오류. {@code YYYY-MM-DD} 가 아니거나 존재하지 않는 날짜. */
	INVALID_DATE_FORMAT(BAD_REQUEST, "V003", "날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)"),

	/** 값 형식 오류 — 길이·문자·타입. 패키지명 규칙 위반이 여기 해당한다. */
	INVALID_VALUE_FORMAT(BAD_REQUEST, "V004", "값 형식이 올바르지 않습니다."),

	/** 서버 내부 오류. 원인은 로그에만 남기고 클라이언트에는 이 문구만 보낸다. */
	INTERNAL_ERROR(INTERNAL_SERVER_ERROR, "S001", "일시적인 오류입니다. 잠시 후 다시 시도해 주세요."),

	/* ── 명세 밖: HTTP 프로토콜 수준 ─────────────────────────────── */

	NOT_SUPPORTED_METHOD(METHOD_NOT_ALLOWED, "C005", "허용되지 않은 http method 접근"),
	RESOURCE_NOT_FOUND(NOT_FOUND, "C006", "요청한 리소스를 찾을 수 없음"),
	NOT_SUPPORTED_MEDIA_TYPE(UNSUPPORTED_MEDIA_TYPE, "C007", "지원하지 않는 Content-Type"),
	NOT_ACCEPTABLE_MEDIA_TYPE(NOT_ACCEPTABLE, "C008", "요청한 Accept에 맞는 응답 형식을 제공할 수 없음"),

	;

	private final HttpStatus status;
	private final String code;
	private final String message;
}
