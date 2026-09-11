package com.ssafy.pickage.domain.community.verification;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 구현계획 §저장소와 Issue 두 판정표를 실제 npm·GitHub 호출과 이어 붙인다. 이 클래스가 이
 * Phase의 유일한 공개 진입점이다 — 나머지(정책 함수·클라이언트·파서)는 패키지 전용이다.
 *
 * <p>이슈·댓글 조회(Phase 3, {@code S15P21A506-212})·API 응답 조립(Phase 4,
 * {@code S15P21A506-317})은 이 클래스를 호출해 {@link RepositoryVerificationResult}만
 * 받는다 — {@link RepositoryVerificationResult.Verified}가 아니면 이슈를 조회하지 않는다.
 */
@Slf4j
@RequiredArgsConstructor
public class RepositoryVerificationService {

	private final NpmRepositoryLookup npmLookup;
	private final GitHubRepositoryClient githubClient;

	public RepositoryVerificationResult verify(String packageName, String dbRepoUrl) {
		NpmLookupOutcome npmOutcome;
		try {
			npmOutcome = npmLookup.fetchRepositoryField(packageName);
		} catch (UpstreamFetchException e) {
			log.warn("npm registry 조회 실패: package={}, cause={}", packageName, e.getMessage());
			return new RepositoryVerificationResult.FetchLimited("npm registry 통신 오류", null);
		}

		if (npmOutcome instanceof NpmLookupOutcome.NotFound) {
			// "npm 조회 404" — 이 패키지는 이미 우리 DB에 있는 이름이므로(§저장소와 Issue
			// "패키지 identity 재확인"), 여기서 다시 검증할 identity는 요청 이름 자체뿐이다.
			return new RepositoryVerificationResult.UnverifiedRepository(
				"npm registry에 패키지가 없음: " + packageName);
		}

		CandidateSource dbSource = RepositoryUrlParser.parse(dbRepoUrl, null);
		CandidateSource npmSource = (npmOutcome instanceof NpmLookupOutcome.Found found)
			? RepositoryUrlParser.parse(found.rawRepositoryUrl(), found.directory())
			: new CandidateSource.Absent();

		CandidateSelection selection = RepositoryCandidatePolicy.resolve(dbSource, npmSource);

		if (selection instanceof CandidateSelection.Unsupported unsupported) {
			return new RepositoryVerificationResult.UnsupportedHost(unsupported.rawUrl());
		}
		if (selection instanceof CandidateSelection.NoCandidate) {
			return new RepositoryVerificationResult.UnverifiedRepository(
				"DB·npm 어느 쪽에도 저장소 후보가 없음: " + packageName);
		}

		ResolvedCandidate candidate = ((CandidateSelection.Proceed) selection).candidate();
		if (candidate.conflictWithDb()) {
			log.info("DB와 npm의 저장소 후보가 달라 npm 후보로 진행: package={}, db={}, npm={}/{}",
				packageName, dbRepoUrl, candidate.owner(), candidate.repo());
		}

		boolean archived;
		try {
			archived = githubClient.isArchived(candidate.owner(), candidate.repo());
		} catch (GitHubRepositoryNotFoundException e) {
			return new RepositoryVerificationResult.UnverifiedRepository(e.getMessage());
		} catch (GitHubRateLimitException e) {
			return new RepositoryVerificationResult.FetchLimited("GitHub rate limit", e.retryAt());
		} catch (UpstreamFetchException e) {
			log.warn("GitHub repos 조회 실패: owner={}, repo={}, cause={}",
				candidate.owner(), candidate.repo(), e.getMessage());
			return new RepositoryVerificationResult.FetchLimited("GitHub 통신 오류", null);
		}

		PackageJsonNameCheck rootCheck = PackageJsonNameCheck.NOT_FOUND;
		PackageJsonNameCheck directoryCheck = PackageJsonNameCheck.NOT_FOUND;
		try {
			if (candidate.directory() != null) {
				directoryCheck = githubClient.checkPackageJsonName(
					candidate.owner(), candidate.repo(), candidate.directory(), packageName);
			} else {
				rootCheck = githubClient.checkPackageJsonName(
					candidate.owner(), candidate.repo(), null, packageName);
			}
		} catch (GitHubRateLimitException e) {
			return new RepositoryVerificationResult.FetchLimited("GitHub rate limit", e.retryAt());
		} catch (UpstreamFetchException e) {
			log.warn("GitHub contents 조회 실패: owner={}, repo={}, cause={}",
				candidate.owner(), candidate.repo(), e.getMessage());
			return new RepositoryVerificationResult.FetchLimited("GitHub 통신 오류", null);
		}

		return RepositoryScopePolicy.classify(candidate, rootCheck, directoryCheck, archived);
	}
}
