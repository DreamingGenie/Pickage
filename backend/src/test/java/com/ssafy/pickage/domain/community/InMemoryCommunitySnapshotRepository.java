package com.ssafy.pickage.domain.community;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

/**
 * 실제 Postgres 없이 {@link CommunityRefreshOrchestrator}의 게시 분기를 검증하기 위한 시험 전용 대역(같은 기법: {@link
 * StubRepositoryVerificationService} 참고). {@code super(null, null)}이 안전한 이유도 같다 — {@code
 * upsert}·{@code findByPackageId}를 전부 오버라이드해 부모의 {@code JdbcTemplate}·{@code ObjectMapper} 필드를 쓰지
 * 않는다.
 */
class InMemoryCommunitySnapshotRepository extends CommunitySnapshotRepository {

    private final Map<Integer, CommunitySnapshotRow> rows = new ConcurrentHashMap<>();

    /** {@code upsert} 호출 시점에 예외를 던지고 싶을 때만 채운다({@code PUBLISH_FAILED} 시험용). */
    private Consumer<CommunitySnapshotRow> onUpsert = row -> {};

    InMemoryCommunitySnapshotRepository() {
        super(null, null);
    }

    void failNextUpsertWith(RuntimeException exception) {
        this.onUpsert =
                row -> {
                    throw exception;
                };
    }

    @Override
    public void upsert(CommunitySnapshotRow row) {
        onUpsert.accept(row);
        rows.put(row.packageId(), row);
    }

    @Override
    public Optional<CommunitySnapshotRow> findByPackageId(int packageId) {
        return Optional.ofNullable(rows.get(packageId));
    }
}
