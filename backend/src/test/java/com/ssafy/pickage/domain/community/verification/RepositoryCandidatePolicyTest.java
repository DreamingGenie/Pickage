package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** 구현계획 §저장소와 Issue "저장소 후보 결정" 표의 각 행을 순수 함수로 확인한다. */
class RepositoryCandidatePolicyTest {

	private static final CandidateSource.GitHubUrl PINO = new CandidateSource.GitHubUrl("pinojs", "pino", null);
	private static final CandidateSource.GitHubUrl OTHER = new CandidateSource.GitHubUrl("someone-else", "pino-fork", null);
	private static final CandidateSource ABSENT = new CandidateSource.Absent();

	@Test
	void DB와_npm이_같은_저장소면_그대로_진행한다() {
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(PINO, PINO);
		ResolvedCandidate candidate = proceed(selection);
		assertThat(candidate.owner()).isEqualTo("pinojs");
		assertThat(candidate.npmCorroborated()).isTrue();
		assertThat(candidate.conflictWithDb()).isFalse();
	}

	@Test
	void 서로_다르고_npm이_GitHub면_npm_후보로_진행하고_충돌을_표시한다() {
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(OTHER, PINO);
		ResolvedCandidate candidate = proceed(selection);
		assertThat(candidate.owner()).isEqualTo("pinojs");
		assertThat(candidate.conflictWithDb()).isTrue();
	}

	@Test
	void npm만_GitHub면_npm_후보로_진행한다() {
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(ABSENT, PINO);
		ResolvedCandidate candidate = proceed(selection);
		assertThat(candidate.npmCorroborated()).isTrue();
		assertThat(candidate.conflictWithDb()).isFalse();
	}

	@Test
	void DB만_GitHub면_DB_후보로_진행하되_npm_교차검증_없음으로_표시한다() {
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(PINO, ABSENT);
		ResolvedCandidate candidate = proceed(selection);
		assertThat(candidate.npmCorroborated()).isFalse();
	}

	@Test
	void npm에_repository_필드가_없어도_DB_후보로_진행한다() {
		// npm 필드 부재는 Absent 로 표현된다(NpmRepositoryLookup 이 NoRepositoryField 를 Absent 로 변환).
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(PINO, ABSENT);
		assertThat(selection).isInstanceOf(CandidateSelection.Proceed.class);
	}

	@Test
	void npm이_명시적으로_비GitHub_host면_DB가_뭐든_중단한다() {
		CandidateSource.NonGitHubHost nonGitHub = new CandidateSource.NonGitHubHost("https://gitlab.com/x/y");
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(PINO, nonGitHub);
		assertThat(selection).isInstanceOf(CandidateSelection.Unsupported.class);
		assertThat(((CandidateSelection.Unsupported) selection).rawUrl()).isEqualTo("https://gitlab.com/x/y");
	}

	@Test
	void DB만_비GitHub이고_npm도_없으면_중단한다() {
		CandidateSource.NonGitHubHost nonGitHub = new CandidateSource.NonGitHubHost("https://gitlab.com/x/y");
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(nonGitHub, ABSENT);
		assertThat(selection).isInstanceOf(CandidateSelection.Unsupported.class);
	}

	@Test
	void 둘_다_없으면_NoCandidate다() {
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(ABSENT, ABSENT);
		assertThat(selection).isInstanceOf(CandidateSelection.NoCandidate.class);
	}

	@Test
	void npm의_directory가_최종_후보에_보존된다() {
		CandidateSource.GitHubUrl withDirectory = new CandidateSource.GitHubUrl("facebook", "react", "packages/react");
		CandidateSelection selection = RepositoryCandidatePolicy.resolve(ABSENT, withDirectory);
		ResolvedCandidate candidate = proceed(selection);
		assertThat(candidate.directory()).isEqualTo("packages/react");
	}

	private static ResolvedCandidate proceed(CandidateSelection selection) {
		assertThat(selection).isInstanceOf(CandidateSelection.Proceed.class);
		return ((CandidateSelection.Proceed) selection).candidate();
	}
}
