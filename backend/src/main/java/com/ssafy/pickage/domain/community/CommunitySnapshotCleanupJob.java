package com.ssafy.pickage.domain.community;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;

/**
 * {@code collected_at} 이 7일보다 오래된 {@code community_snapshot} 행을 매시간 최대 500개 지운다(구현계획 §migration과
 * seed).
 *
 * <p><b>이 저장소의 다른 주기 배치는 전부 앱 밖의 cron 이 1회성 잡을 띄우는 방식이다</b> (예: {@code compose.yaml} 의 유사도 배치 —
 * "운영에서는 EC2 #1 의 cron 이 배치 시각마다 새로 띄우는 1회성 잡"). 이 코드베이스에 {@code @Scheduled} 선례는 없다.
 *
 * <p>그럼에도 인앱 {@code @Scheduled} 를 택했다 — 외부 cron 패턴의 이유("켜고 끄는 주체가 문제")는 GPU/Spark 다중 노드 조율이 필요한
 * 배치에서 나온 것이고, 이 정리는 {@code api} 컨테이너 하나 안에서 테이블 하나를 지우는 가벼운 작업이라 그 조율 문제가 없다. 이 판단은 {@code
 * docs/history/0923_0917_pickage_final_set_archive/for_community/specs/S15P21A506-314.md} §3.4 에서 사용자 승인을 받았다 — 이후 일관성을 위해 외부 트리거 방식으로 바꾸기로 하면
 * 이 클래스만 바꾸면 된다(다른 코드는 {@link CommunitySnapshotRepository#deleteExpiredBefore} 만 의존한다).
 *
 * <p>{@link CommunitySnapshotTtl#isExpiredForCleanup} 이 실제 판정 기준이고, 조회 시점의 TTL 검사는 이 배치의 실행 여부와
 * 무관하게 항상 {@code collected_at} 으로 다시 계산되므로, 이 배치가 지연돼도 만료된 결과가 화면에 노출되지 않는다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class CommunitySnapshotCleanupJob {

    private static final int MAX_ROWS_PER_RUN = 500;

    private final CommunitySnapshotRepository repository;

    @Scheduled(cron = "0 0 * * * *")
    public void cleanupExpiredSnapshots() {
        Instant threshold = Instant.now().minus(CommunitySnapshotTtl.SERVE_WINDOW);
        int deleted = repository.deleteExpiredBefore(threshold, MAX_ROWS_PER_RUN);
        if (deleted > 0) {
            log.info("community_snapshot 정리: collected_at <= {} 인 {}행 삭제", threshold, deleted);
        }
    }
}
