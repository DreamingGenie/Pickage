package com.ssafy.pickage.domain.community.verification;

/**
 * {@link RepositoryUrlParser}가 원문 URL 문자열 하나를 분류한 결과.
 *
 * <p>"파싱 실패"와 "GitHub가 아닌 host"를 구분하는 것이 SSRF 방지의 핵심이다(구현계획 §저장소와 Issue "npm이 GitHub를 가리키는데... 명시
 * 비GitHub 중단"). {@link NonGitHubHost}는 문자열 자체는 유효한 URL이지만 host가 {@code github.com}이 아니라는 뜻이고, 이 값이
 * 있으면 최종 후보가 GitHub 외 host를 가리킨 것으로 처리해 {@link RepositoryVerificationResult.UnsupportedHost}로 끝낸다.
 */
public sealed interface CandidateSource {

    /**
     * {@code owner/repo}로 정규화된 GitHub 저장소 후보.
     *
     * @param directory npm {@code repository.directory}로 지정된 monorepo 내 경로. 없으면 {@code null}(빈 문자열이
     *     아니다 — "지정 안 함"과 "빈 경로"를 구분한다)
     */
    record GitHubUrl(String owner, String repo, String directory) implements CandidateSource {}

    /** 유효한 URL이지만 host가 github.com이 아니다(다른 forge, IP 리터럴, 사설 host 등). */
    record NonGitHubHost(String rawUrl) implements CandidateSource {}

    /** 필드 자체가 없거나(null) 형식이 깨져 owner/repo 를 뽑을 수 없다. */
    record Invalid() implements CandidateSource {}

    record Absent() implements CandidateSource {}
}
