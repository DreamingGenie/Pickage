package com.ssafy.pickage.domain.community.verification;

import java.time.Instant;

/**
 * {@link RepositoryVerificationService}의 최종 산출물. 성공은 하나, 실패는 성격이 다른 셋으로 나뉜다 — 이 구분 자체가 구현계획 §저장소와
 * Issue 판정표의 핵심이다.
 *
 * <ul>
 *   <li>{@link Verified} — 이슈 조회(Phase 3)로 진행해도 된다.
 *   <li>{@link UnverifiedRepository}·{@link AmbiguousScope}·{@link UnsupportedHost} — terminal. 다른
 *       후보로 자동 대체하지 않고 빈 topics로 인계한다({@code data_status}로 Phase 4가 저장할 값과 이름이 같다 — 우연이 아니라 이 세 값이
 *       정확히 §데이터베이스의 허용값 집합이기 때문이다. 다만 타입은 공유하지 않는다 — Phase 1의 {@code CommunitySnapshotRow}에 대한 의존을
 *       만들지 않기 위해서다).
 *   <li>{@link FetchLimited} — terminal이 아니다. "저장소가 없다"고 단정하지 않고 나중에 재시도한다(구현계획: "일시 실패는 DB 결과를
 *       덮어쓰지 않으며 retry_at 이후 재시도").
 * </ul>
 */
public sealed interface RepositoryVerificationResult {

    record Verified(
            String owner,
            String repo,
            RepositoryScope scope,
            boolean scopeLimited,
            boolean repositoryArchived,
            java.util.List<com.ssafy.pickage.domain.community.payload.LimitationPayload>
                    limitations)
            implements RepositoryVerificationResult {}

    /** DB·npm 어느 후보도 GitHub 저장소로 확정 연결되지 않았다(404, private, DB-only 이름 불일치 등). */
    record UnverifiedRepository(String reason) implements RepositoryVerificationResult {}

    /** 연결은 확인됐지만 이슈를 이 패키지 범위로 볼 근거가 없다 — directory 경로 404 또는 이름 불일치. */
    record AmbiguousScope(String owner, String repo) implements RepositoryVerificationResult {}

    /** 최종 후보가 GitHub가 아닌 host를 가리킨다. */
    record UnsupportedHost(String rawUrl) implements RepositoryVerificationResult {}

    /**
     * 네트워크 오류·429·rate-limit 403·응답 byte 초과 — "저장소가 없다"는 판단이 아니다. {@code retryAt}은 안다면 채우고(예:
     * {@code X-RateLimit-Reset}), 모르면 {@code null}.
     */
    record FetchLimited(String reason, Instant retryAt) implements RepositoryVerificationResult {}
}
