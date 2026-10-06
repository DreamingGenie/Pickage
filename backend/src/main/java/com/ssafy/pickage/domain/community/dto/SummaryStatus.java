package com.ssafy.pickage.domain.community.dto;

/** 이슈 하나의 요약 상태, 그리고 그걸 합산한 전체 요약 상태(구현계획 §상태와 오류). */
public enum SummaryStatus {
	READY,
	PARTIAL,
	FAILED,
	SKIPPED
}
