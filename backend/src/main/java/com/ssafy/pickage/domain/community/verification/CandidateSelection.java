package com.ssafy.pickage.domain.community.verification;

/** {@link RepositoryCandidatePolicy#resolve} 결과 — 계속 진행하거나, 곧바로 끝나거나. */
sealed interface CandidateSelection {

	record Proceed(ResolvedCandidate candidate) implements CandidateSelection {
	}

	record Unsupported(String rawUrl) implements CandidateSelection {
	}

	/** DB·npm 둘 다 후보가 없다(둘 다 {@link CandidateSource.Absent}). */
	record NoCandidate() implements CandidateSelection {
	}
}
