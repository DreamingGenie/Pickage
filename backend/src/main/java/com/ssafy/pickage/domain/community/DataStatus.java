package com.ssafy.pickage.domain.community;

/**
 * {@code community_snapshot.data_status} 의 허용값(구현계획 §데이터베이스).
 *
 * <p>일시적인 외부 호출 실패(rate limit 등)나 진행 중 상태는 완성 결과가 아니므로 여기 없다 —
 * 그런 상태는 이 테이블에 아예 저장하지 않는다({@code community_snapshot} 은 "게시된 결과"만
 * 담는다).
 */
public enum DataStatus {
	AVAILABLE,
	PARTIAL,
	UNVERIFIED_REPOSITORY,
	AMBIGUOUS_SCOPE,
	UNSUPPORTED_HOST,
	NO_DISCUSSION_DATA
}
