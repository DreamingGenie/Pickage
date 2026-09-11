package com.ssafy.pickage.domain.community.verification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** 구현계획 §저장소와 Issue "패키지 연결과 Issue 귀속 범위" 표 + Jira 213 DB-only 규칙. */
class RepositoryScopePolicyTest {

	@Test
	void DB_only_루트_이름_일치하면_PACKAGE_SCOPED다() {
		ResolvedCandidate candidate = new ResolvedCandidate("pinojs", "pino", null, false, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.MATCH, PackageJsonNameCheck.NOT_FOUND, false);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.Verified.class);
		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.scope()).isEqualTo(RepositoryScope.PACKAGE_SCOPED);
		assertThat(verified.scopeLimited()).isFalse();
	}

	@Test
	void DB_only_루트_이름_불일치하면_UnverifiedRepository다_REPOSITORY_WIDE로_봐주지_않는다() {
		ResolvedCandidate candidate = new ResolvedCandidate("someone", "unrelated-repo", null, false, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.MISMATCH, PackageJsonNameCheck.NOT_FOUND, false);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.UnverifiedRepository.class);
	}

	@Test
	void npm_교차검증_directory_없음_루트_일치하면_PACKAGE_SCOPED다() {
		ResolvedCandidate candidate = new ResolvedCandidate("pinojs", "pino", null, true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.MATCH, PackageJsonNameCheck.NOT_FOUND, false);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.scope()).isEqualTo(RepositoryScope.PACKAGE_SCOPED);
	}

	@Test
	void npm_교차검증_directory_없음_루트_불일치해도_REPOSITORY_WIDE로_진행하고_한계표시한다() {
		// DB-only와 달리 npm이 이미 이 owner/repo를 가리켰으므로(교차검증 있음) 완전히
		// 포기하지 않는다 — table 2의 관대한 규칙.
		ResolvedCandidate candidate = new ResolvedCandidate("someorg", "monorepo", null, true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.MISMATCH, PackageJsonNameCheck.NOT_FOUND, false);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.Verified.class);
		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.scope()).isEqualTo(RepositoryScope.REPOSITORY_WIDE);
		assertThat(verified.scopeLimited()).isTrue();
	}

	@Test
	void directory_지정되고_이름_일치하면_REPOSITORY_WIDE다_전용_증거는_아니므로() {
		ResolvedCandidate candidate = new ResolvedCandidate("facebook", "react", "packages/react", true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.NOT_FOUND, PackageJsonNameCheck.MATCH, false);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.scope()).isEqualTo(RepositoryScope.REPOSITORY_WIDE);
		assertThat(verified.scopeLimited()).isTrue();
	}

	@Test
	void directory_경로가_404면_AMBIGUOUS_SCOPE다() {
		ResolvedCandidate candidate = new ResolvedCandidate("facebook", "react", "packages/missing", true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.NOT_FOUND, PackageJsonNameCheck.NOT_FOUND, false);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.AmbiguousScope.class);
	}

	@Test
	void directory_이름_불일치도_AMBIGUOUS_SCOPE다() {
		ResolvedCandidate candidate = new ResolvedCandidate("facebook", "react", "packages/react-dom", true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.NOT_FOUND, PackageJsonNameCheck.MISMATCH, false);

		assertThat(result).isInstanceOf(RepositoryVerificationResult.AmbiguousScope.class);
	}

	@Test
	void archived_여부가_Verified에_그대로_실린다() {
		ResolvedCandidate candidate = new ResolvedCandidate("pinojs", "pino", null, true, false);
		RepositoryVerificationResult result = RepositoryScopePolicy.classify(
			candidate, PackageJsonNameCheck.MATCH, PackageJsonNameCheck.NOT_FOUND, true);

		var verified = (RepositoryVerificationResult.Verified) result;
		assertThat(verified.repositoryArchived()).isTrue();
	}
}
