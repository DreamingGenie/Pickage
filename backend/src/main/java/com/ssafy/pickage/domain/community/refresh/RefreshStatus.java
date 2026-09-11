package com.ssafy.pickage.domain.community.refresh;

/** {@code refresh.status}(구현계획 §API "상태와 오류"). */
public enum RefreshStatus {
	NOT_STARTED,
	QUEUED,
	RUNNING,
	COMPLETED,
	FAILED,
	CAPACITY_LIMITED
}
