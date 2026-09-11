package com.ssafy.pickage.domain.community.verification;

/**
 * npm·GitHub 호출의 일시적 실패 — 네트워크 오류, 응답 byte 상한 초과, rate-limit이 아닌 timeout 등. {@link
 * RepositoryVerificationService}는 이 예외를 {@link RepositoryVerificationResult.FetchLimited}로 바꾼다 —
 * "저장소가 없다"고 단정하지 않는다(구현계획: "필수 metadata 응답 byte 초과·통신 오류는 확정 연결 실패로 저장하지 않는다").
 *
 * <p>메시지에 원인 예외의 raw 내용(응답 body, 인증 헤더)을 담지 않는다 — 상태 코드·호스트 정도만 남긴다.
 */
public class UpstreamFetchException extends RuntimeException {

    public boolean sizeLimited() {
        return "RESPONSE_SIZE_LIMITED".equals(getMessage());
    }

    public UpstreamFetchException(String message) {
        super(message);
    }

    public UpstreamFetchException(String message, Throwable cause) {
        super(
                cause != null && "Community response size limit".equals(cause.getMessage())
                        ? "RESPONSE_SIZE_LIMITED"
                        : message);
    }
}
