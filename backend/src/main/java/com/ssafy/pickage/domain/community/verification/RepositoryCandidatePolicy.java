package com.ssafy.pickage.domain.community.verification;

/**
 * 구현계획 §저장소와 Issue "저장소 후보 결정" 표를 그대로 옮긴 순수 함수. 외부 I/O가 전혀 없다 — 이미 파싱된 {@link CandidateSource} 두
 * 개(DB·npm)만 받아 다음 GitHub 호출에 쓸 후보를 고르거나 즉시 끝낸다.
 *
 * <p>이 클래스가 다루지 않는 표의 행: "npm 조회 404"·"네트워크 오류·429·rate-limit 403"· "GitHub 404·403"은 HTTP 응답이 있어야
 * 판단할 수 있으므로 {@link RepositoryVerificationService}가 직접 처리한다.
 */
final class RepositoryCandidatePolicy {

    private RepositoryCandidatePolicy() {}

    static CandidateSelection resolve(CandidateSource db, CandidateSource npm) {
        if (npm instanceof CandidateSource.Invalid) return new CandidateSelection.NoCandidate();
        boolean dbIsGitHub = db instanceof CandidateSource.GitHubUrl;
        boolean npmIsGitHub = npm instanceof CandidateSource.GitHubUrl;

        if (dbIsGitHub && npmIsGitHub) {
            CandidateSource.GitHubUrl dbUrl = (CandidateSource.GitHubUrl) db;
            CandidateSource.GitHubUrl npmUrl = (CandidateSource.GitHubUrl) npm;
            boolean same =
                    dbUrl.owner().equalsIgnoreCase(npmUrl.owner())
                            && dbUrl.repo().equalsIgnoreCase(npmUrl.repo());
            // "DB·npm이 같은 GitHub 저장소" → 그대로, "서로 다르고 npm이 GitHub" → npm 후보.
            // 두 경우 다 최종 후보는 npm 쪽 표기(directory 포함)를 쓴다 — npm이 directory
            // 정보를 가진 유일한 원천이다.
            return new CandidateSelection.Proceed(
                    new ResolvedCandidate(
                            npmUrl.owner(), npmUrl.repo(), npmUrl.directory(), true, !same));
        }

        if (npmIsGitHub) {
            // "npm만 GitHub" → npm 후보로 진행.
            CandidateSource.GitHubUrl npmUrl = (CandidateSource.GitHubUrl) npm;
            return new CandidateSelection.Proceed(
                    new ResolvedCandidate(
                            npmUrl.owner(), npmUrl.repo(), npmUrl.directory(), true, false));
        }

        if (npm instanceof CandidateSource.NonGitHubHost nonGitHubNpm) {
            // "npm 우선·명시 비GitHub 중단"(Jira 213 세부 항목) — npm이 실제로 값을 줬는데
            // GitHub가 아니면 DB가 뭐라 하든 그 즉시 중단한다. npm이 아예 없는 경우
            // (Absent)는 여기 해당하지 않고 아래 DB-only 분기로 간다.
            return new CandidateSelection.Unsupported(nonGitHubNpm.rawUrl());
        }

        if (dbIsGitHub) {
            // "DB만 GitHub 또는 npm에 repository 없음" → DB 후보, 단 루트 이름 검증은
            // RepositoryScopePolicy(npmCorroborated=false 분기)가 별도 GitHub 호출 뒤에 한다.
            CandidateSource.GitHubUrl dbUrl = (CandidateSource.GitHubUrl) db;
            return new CandidateSelection.Proceed(
                    new ResolvedCandidate(dbUrl.owner(), dbUrl.repo(), null, false, false));
        }

        if (db instanceof CandidateSource.NonGitHubHost nonGitHub) {
            return new CandidateSelection.Unsupported(nonGitHub.rawUrl());
        }

        return new CandidateSelection.NoCandidate();
    }
}
