package com.ssafy.pickage.domain.community.collection;

import java.time.Instant;
import java.util.List;

/** {@link IssueCollectionService#collect}의 최종 산출물. */
public sealed interface IssueCollectionResult {

    /** 이슈 1~2건(github-active-v1 정책으로 선택됨). */
    record Success(List<CollectedIssue> topics, List<String> limitations, int lookbackDays)
            implements IssueCollectionResult {}

    /** 조건에 맞는 논의가 없다 — 180일(필요시 365일)·필터 후에도 이슈가 하나도 안 남음. */
    record NoDiscussionData(int lookbackDays, List<String> limitations)
            implements IssueCollectionResult {}

    /** rate limit·네트워크 오류 — "논의가 없다"고 단정하지 않는다. */
    record FetchLimited(String reason, Instant retryAt) implements IssueCollectionResult {}
}
