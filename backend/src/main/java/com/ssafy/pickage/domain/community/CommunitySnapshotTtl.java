package com.ssafy.pickage.domain.community;

import java.time.Duration;
import java.time.Instant;

/**
 * {@code collected_at} 하나로 신선도·제공 가능 여부·정리 대상 여부를 판정하는 순수 함수.
 *
 * <p>구현계획 §"컬럼으로 만들지 않는 값" — {@code fresh_until}·{@code serve_until}은 DB에 넣지 않고 매번 이 계산으로 만든다. 정리
 * 배치가 지연돼도 이 판정은 항상 {@code collected_at} 기준으로 다시 계산되므로, 배치 지연이 만료된 결과를 노출하는 원인이 되지 않는다.
 *
 * <p>이 클래스는 판정만 한다 — 실제 조회 흐름에서의 사용(예: {@code view_status} 조립)은 Phase 4({@code S15P21A506-317})의
 * 몫이다.
 */
public final class CommunitySnapshotTtl {

    /** 구현계획 §설정과 보안 — 결과 재사용 24시간. */
    public static final Duration FRESH_WINDOW = Duration.ofHours(24);

    /** 구현계획 §설정과 보안 — 결과 제공 7일. */
    public static final Duration SERVE_WINDOW = Duration.ofDays(7);

    /**
     * 저장소 전체 Issue 수가 비어 있는 스냅샷을 다시 수집해도 되는 나이(S15P21A506-415).
     *
     * <p>수치가 못 구해진 채 저장되면(조회 실패, 또는 수치를 더하기 전에 저장된 스냅샷) 24시간 신선 창 동안 화면이 계속 "—" 이다.
     * 그렇다고 열 때마다 다시 수집하면 GMS 요약 비용이 매번 든다 — 이 간격이 그 사이의 절충이다. 수치가 있는 스냅샷에는 적용하지
     * 않는다.
     */
    public static final Duration COUNTS_RETRY_WINDOW = Duration.ofMinutes(30);

    private CommunitySnapshotTtl() {}

    /** 24시간 이내면 갱신 없이 그대로 재사용한다({@code freshness=FRESH}). */
    public static boolean isFresh(Instant collectedAt, Instant now) {
        return now.isBefore(collectedAt.plus(FRESH_WINDOW));
    }

    /** 7일이 지나면 이전 결과라도 더는 보여주지 않는다. */
    public static boolean isServable(Instant collectedAt, Instant now) {
        return now.isBefore(collectedAt.plus(SERVE_WINDOW));
    }

    /** 매시간 정리 배치가 지우는 대상(= 더 이상 제공하지 않는 행)인지. */
    public static boolean isExpiredForCleanup(Instant collectedAt, Instant now) {
        return !isServable(collectedAt, now);
    }
}
