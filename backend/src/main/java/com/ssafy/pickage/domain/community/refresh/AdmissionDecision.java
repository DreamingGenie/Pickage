package com.ssafy.pickage.domain.community.refresh;

/**
 * {@link RefreshAdmissionCoordinator#admit}의 결과. Jira 317 완료 판단 기준 — "새 task202/
 * 기존 참여·거절200"에 맞춰 호출자(컨트롤러)가 HTTP 상태를 고른다: {@link Started}→202,
 * {@link Joined}·{@link Rejected}→200.
 */
public sealed interface AdmissionDecision {

	/** 새 task를 만들었다 — 즉시 실행을 시작했거나(queued=false) TAB_OPENED 대기 큐에 넣었다(queued=true). */
	record Started(RefreshTask task, boolean queued) implements AdmissionDecision {
	}

	/** 이미 진행 중인 task에 참여시켰다. */
	record Joined(RefreshTask task) implements AdmissionDecision {
	}

	/** registry 용량·시작 토큰·동시 실행·대기 큐 중 하나가 꽉 찼다. */
	record Rejected() implements AdmissionDecision {
	}
}
