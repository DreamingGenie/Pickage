package com.ssafy.pickage.domain.community.refresh;

import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

import java.time.Instant;

public sealed interface AdmissionDecision {
    record Started(RefreshTask task, boolean queued) implements AdmissionDecision {}

    record Joined(RefreshTask task) implements AdmissionDecision {}

    record Rejected(CommunityErrorCode code, Instant retryAt) implements AdmissionDecision {
        public Rejected() {
            this(CommunityErrorCode.CAPACITY_LIMITED, Instant.now().plusSeconds(2));
        }
    }
}
