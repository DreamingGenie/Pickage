package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

class CommunitySnapshotTtlTest {

    private final Instant now = Instant.parse("2026-09-11T00:00:00Z");

    @Test
    void isFresh_경계값_24시간은_false() {
        Instant justInside = now.minus(24, ChronoUnit.HOURS);
        assertThat(CommunitySnapshotTtl.isFresh(justInside, now)).isFalse();
    }

    @Test
    void isFresh_24시간_1초_초과는_false() {
        Instant justOutside = now.minus(24, ChronoUnit.HOURS).minusSeconds(1);
        assertThat(CommunitySnapshotTtl.isFresh(justOutside, now)).isFalse();
    }

    @Test
    void isServable_경계값_7일은_false() {
        Instant justInside = now.minus(7, ChronoUnit.DAYS);
        assertThat(CommunitySnapshotTtl.isServable(justInside, now)).isFalse();
    }

    @Test
    void isServable_7일_1초_초과는_false() {
        Instant justOutside = now.minus(7, ChronoUnit.DAYS).minusSeconds(1);
        assertThat(CommunitySnapshotTtl.isServable(justOutside, now)).isFalse();
    }

    @Test
    void isExpiredForCleanup_은_isServable_의_반대다() {
        Instant stale = now.minus(8, ChronoUnit.DAYS);
        assertThat(CommunitySnapshotTtl.isServable(stale, now)).isFalse();
        assertThat(CommunitySnapshotTtl.isExpiredForCleanup(stale, now)).isTrue();
    }

    @Test
    void 정리_배치가_지연돼도_TTL_판정은_항상_collectedAt_기준이다() {
        // 배치 실행 여부와 무관하게 조회 시점(now)만 바뀌면 판정이 그대로 바뀐다 —
        // 별도의 "정리됨" 플래그가 없다는 것이 이 설계의 핵심(구현계획 §migration과 seed).
        Instant collectedAt = Instant.parse("2026-09-01T00:00:00Z");
        Instant beforeCleanupWouldRun = collectedAt.plus(6, ChronoUnit.DAYS);
        Instant afterServeWindowPassed = collectedAt.plus(8, ChronoUnit.DAYS);

        assertThat(CommunitySnapshotTtl.isServable(collectedAt, beforeCleanupWouldRun)).isTrue();
        assertThat(CommunitySnapshotTtl.isServable(collectedAt, afterServeWindowPassed)).isFalse();
    }
}
