package com.ssafy.pickage.domain.community.verification;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import java.time.Duration;
import java.time.Instant;

/**
 * 구현계획 §저장소와 Issue 두 판정표를 실제 npm·GitHub 호출과 이어 붙인다. 이 클래스가 이 Phase의 유일한 공개 진입점이다 — 나머지(정책
 * 함수·클라이언트·파서)는 패키지 전용이다.
 *
 * <p>이슈·댓글 조회(Phase 3, {@code S15P21A506-212})·API 응답 조립(Phase 4, {@code S15P21A506-317})은 이 클래스를
 * 호출해 {@link RepositoryVerificationResult}만 받는다 — {@link RepositoryVerificationResult.Verified}가
 * 아니면 이슈를 조회하지 않는다.
 *
 * <p><b>예산 전달({@link #verify(String, String, Duration)}).</b> 이 클래스는 원래 20초 단일 예산 개념이 없었다 — npm 조회
 * 1회 + GitHub 호출 최대 2회를 각각 고정 10초 상한으로 순서대로 부르므로, 셋 다 느리면 그 자체로 30초까지 걸려 317 ({@code
 * CommunityRefreshOrchestrator})이 가정하는 20초 전체 예산을 검증 단계에서 이미 넘길 수 있었다(1~4 Phase 전체 정밀 리뷰에서 발견).
 * 212의 {@code IssueCollectionService.collect()}와 정확히 같은 방식으로 고친다 — 진입 시점에 {@code deadline = now +
 * budget}을 한 번만 계산하고, 각 외부 호출 직전에 그때까지 남은 시간을 다시 계산해 그 호출의 상한으로 넘긴다. 예산을 안 받는 {@link
 * #verify(String, String)}는 이전 동작(최악 30초)을 그대로 보존하도록 넉넉한 기본값으로 위임한다 — 기존 호출부(213 자체 시험 등)를 깨지 않기
 * 위해서다.
 */
@Slf4j
@RequiredArgsConstructor
public class RepositoryVerificationService {

    /** 예산을 안 받는 호출의 기본값 — 기존 고정 10초×3회 구조의 최악 실행 시간과 같다. */
    private static final Duration DEFAULT_BUDGET = Duration.ofSeconds(30);

    private final NpmRepositoryLookup npmLookup;
    private final GitHubRepositoryClient githubClient;

    public RepositoryVerificationResult verify(String packageName, String dbRepoUrl) {
        return verify(packageName, dbRepoUrl, DEFAULT_BUDGET);
    }

    public RepositoryVerificationResult verify(
            String packageName, String dbRepoUrl, Duration budget) {
        Instant deadline = Instant.now().plus(budget);

        if (timeLeft(deadline).isZero()) {
            return new RepositoryVerificationResult.FetchLimited("시간 예산 소진", null);
        }
        NpmLookupOutcome npmOutcome;
        try {
            npmOutcome = npmLookup.fetchRepositoryField(packageName, timeLeft(deadline));
        } catch (UpstreamFetchException e) {
            log.warn("npm registry 조회 실패");
            return new RepositoryVerificationResult.FetchLimited("npm registry 통신 오류", null);
        }

        if (npmOutcome instanceof NpmLookupOutcome.NotFound) {
            // "npm 조회 404" — 이 패키지는 이미 우리 DB에 있는 이름이므로(§저장소와 Issue
            // "패키지 identity 재확인"), 여기서 다시 검증할 identity는 요청 이름 자체뿐이다.
            return new RepositoryVerificationResult.UnverifiedRepository(
                    "npm registry에 패키지가 없음: " + packageName);
        }

        CandidateSource dbSource = RepositoryUrlParser.parse(dbRepoUrl, null);
        CandidateSource npmSource =
                (npmOutcome instanceof NpmLookupOutcome.Found found)
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

        if (timeLeft(deadline).isZero()) {
            return new RepositoryVerificationResult.FetchLimited("시간 예산 소진", null);
        }
        boolean archived;
        try {
            archived =
                    githubClient.isArchived(
                            candidate.owner(), candidate.repo(), timeLeft(deadline));
        } catch (GitHubRepositoryNotFoundException e) {
            return new RepositoryVerificationResult.UnverifiedRepository(
                    "Repository is not public or unavailable");
        } catch (GitHubRateLimitException e) {
            return new RepositoryVerificationResult.FetchLimited("GitHub rate limit", e.retryAt());
        } catch (UpstreamFetchException e) {
            log.warn("GitHub metadata 조회 실패");
            return new RepositoryVerificationResult.FetchLimited("GitHub 통신 오류", null);
        }

        if (timeLeft(deadline).isZero()) {
            return new RepositoryVerificationResult.FetchLimited("시간 예산 소진", null);
        }
        PackageJsonNameCheck rootCheck = PackageJsonNameCheck.NOT_FOUND;
        PackageJsonNameCheck directoryCheck = PackageJsonNameCheck.NOT_FOUND;
        try {
            if (candidate.directory() != null) {
                directoryCheck =
                        githubClient.checkPackageJsonName(
                                candidate.owner(),
                                candidate.repo(),
                                candidate.directory(),
                                packageName,
                                timeLeft(deadline));
            } else {
                rootCheck =
                        githubClient.checkPackageJsonName(
                                candidate.owner(),
                                candidate.repo(),
                                null,
                                packageName,
                                timeLeft(deadline));
            }
        } catch (GitHubRateLimitException e) {
            return new RepositoryVerificationResult.FetchLimited("GitHub rate limit", e.retryAt());
        } catch (UpstreamFetchException e) {
            log.warn("GitHub metadata 조회 실패");
            return new RepositoryVerificationResult.FetchLimited("GitHub 통신 오류", null);
        }

        return RepositoryScopePolicy.classify(candidate, rootCheck, directoryCheck, archived);
    }

    /** 212의 {@code IssueCollectionService.timeLeft}와 같다 — 음수가 되지 않게 0으로 바닥을 둔다. */
    private static Duration timeLeft(Instant deadline) {
        Duration left = Duration.between(Instant.now(), deadline);
        return left.isNegative() ? Duration.ZERO : left;
    }
}
