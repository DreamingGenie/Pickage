package com.ssafy.pickage.domain.community;

import java.time.Duration;

/**
 * 구현계획 §설정과 보안의 숫자값 전부를 한 곳에 모은다. 2026-09-11 사용자 결정 — {@code application.yaml}(공용 파일)을 건드리지 않고 상수
 * 클래스로 시작한다. 운영에서 실제로 조정이 필요해지면(문서: "20초가 충분한지는 운영 p95를 보고 조정") 그때
 * {@code @ConfigurationProperties}로 승격한다.
 */
public final class CommunityProperties {

    private CommunityProperties() {}

    /** 동시 실행 permit — 세마포어 크기. */
    public static final int MAX_CONCURRENT_EXECUTIONS = 2;

    /** {@code TAB_OPENED} 트리거가 permit을 못 얻었을 때 대기할 수 있는 큐 용량. */
    public static final int TAB_OPENED_QUEUE_CAPACITY = 4;

    /** 새 refresh 시작 토큰 버킷 — 분당 리필량. GitHub Search 한도(10/분)에 맞춘 값. */
    public static final int START_TOKENS_PER_MINUTE = 10;

    /** 토큰 버킷 burst 허용량. */
    public static final int START_TOKEN_BURST = 4;

    /** 작업 실행기 고정 worker 수. */
    public static final int EXECUTOR_WORKER_COUNT = 2;

    /**
     * 저장소 검증→이슈 검색→댓글 수집→GMS→게시 전체에 허용된 시간. 2026-09-16 운영 실측 —
     * 이슈 2개를 순차로 GMS 호출하면 대형 저장소(예: react/react, 댓글 500개대)에서 20초를
     * 넘겨 HttpTimeoutException/InterruptedException으로 매번 실패했다(S15P21A506-368 후속).
     * 이슈 병렬 호출(S15P21A506-368 후속, {@link CommunityRefreshOrchestrator})로 GMS 몫은
     * 줄였지만, 그래도 수집(5~6초 안팎) + 병렬 GMS 최악값({@link
     * GmsCommunitySummarizer}의 상한) + 게시 여유를 더하면 빠듯해 30초로 올렸다.
     *
     * <p>2026-09-16 4단계(Map-Reduce) 로컬 실측으로 30초→35초로 재조정 — 배치가 있는 이슈는
     * Map(N회, 동시 디스패치)이 끝나야 Reduce(1회)가 순차로 붙어 GMS 구간이 단일 호출 상한
     * ({@link GmsCommunitySummarizer}의 {@code MAX_CALL_TIMEOUT}=30초)보다 더 걸릴 수 있다 —
     * 오세진 님이 시연 안정성을 위해 5초 여유를 더 두기로 결정.
     */
    public static final Duration TOTAL_BUDGET = Duration.ofSeconds(35);

    /** DB 게시 트랜잭션의 {@code statement_timeout} 예약(314의 실제 값과 별개로, 이 Phase가 기대하는 상한). */
    public static final Duration PUBLISH_BUDGET = Duration.ofSeconds(2);

    /** 완료된 작업을 registry에서 조회 가능하게 보존하는 시간. */
    public static final Duration COMPLETED_TASK_RETENTION = Duration.ofMinutes(10);

    /** 요약 실패(FAILED) 후 재시도를 허용하기까지의 쿨다운. */
    public static final Duration FAILURE_COOLDOWN = Duration.ofMinutes(5);

    /** 진행 중 조회 응답의 {@code poll_after_seconds} 안내값. */
    public static final int POLL_AFTER_SECONDS = 2;

    /** {@link RefreshTaskRegistry} 최대 항목 수(구현계획 "registry128"). */
    public static final int REGISTRY_MAX_ENTRIES = 128;

    /** 종료(shutdown) 시 실행 중 작업에 주는 유예 시간. */
    public static final Duration SHUTDOWN_GRACE_PERIOD = Duration.ofSeconds(5);

    /**
     * {@code result.data_limits.max_issues} — 응답에 적용된 상한을 그대로 보여주기 위한 값. 실제 선정 로직의 상한은 212의 {@code
     * IssueSelectionPolicy.MAX_SELECTED_ISSUES}가 소유한다(패키지 전용, 의도적으로 캡슐화됨) — 이 값은 그걸 다시 강제하지 않고 API
     * 응답용 정보 표시로만 쓴다. 두 값이 같다는 사실은 계약 시험으로 확인한다.
     */
    public static final int MAX_ISSUE_COUNT = 2;

    /**
     * {@code result.data_limits.max_comments_per_issue} — 위와 같은 이유로 212의 {@code
     * CommentWindowResolver.TARGET_COMMENT_COUNT}와 별개로 둔다.
     */
    public static final int MAX_COMMENTS_PER_ISSUE = 100;

    /**
     * Map-Reduce(S15P21A506-373 4단계) 배치 하나의 문자 예산. {@link
     * CommunitySummarySourceBundle#from}의 이슈 전체 48,000자 예산과 별개 — 이슈가 그 예산을
     * 넘길 때만({@code limited()}) {@link CommunitySummarySourceBundle#batches}가 이 값으로
     * 배치를 나눈다.
     */
    public static final int SUMMARY_BATCH_CHAR_BUDGET = 12000;

    /**
     * 이슈 하나당 만들 수 있는 배치 수 상한. 이 이상 남는 댓글은 버리고 저하(limited)로
     * 표시한다 — 48,000자를 넘으면 버리는 것과 같은 종류의 저하.
     */
    public static final int MAX_SUMMARY_BATCHES = 5;

    /**
     * {@link BoundedCommunitySummarizer}의 GMS 호출 worker 수. {@link
     * com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator}가 쓰는 {@link
     * #EXECUTOR_WORKER_COUNT}(refresh task 자체의 동시 실행 풀)와는 다른 별개의 풀이다 —
     * Map-Reduce로 이슈 하나가 N+1번 GMS를 호출하게 되면서 기존 2로는 배치 호출이 곧바로 큐잉·
     * 거부되므로 4단계에서 상향한다.
     */
    public static final int SUMMARIZER_WORKER_COUNT = 6;

    /** {@link #SUMMARIZER_WORKER_COUNT} 워커가 꽉 찼을 때 대기할 수 있는 큐 용량. */
    public static final int SUMMARIZER_QUEUE_CAPACITY = 8;
}
