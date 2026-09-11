package com.ssafy.pickage.domain.community.collection;

/** 이슈 하나의 댓글 수집 결과 상태(구현계획 §API 응답 예시의 {@code collection_status}). */
public enum CommentCollectionStatus {
	/** 최신 100개(또는 전체, 100개 미만이면)를 확정적으로 확보했다. */
	COMPLETE,
	/** 일부는 확보했지만 호출 사이 증감·page 실패로 정확히 최신 100개임을 보장 못 한다. */
	TRUNCATED,
	/** 댓글을 하나도 확보하지 못했다. */
	FAILED
}
