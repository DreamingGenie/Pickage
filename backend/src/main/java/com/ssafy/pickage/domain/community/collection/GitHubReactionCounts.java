package com.ssafy.pickage.domain.community.collection;

import com.fasterxml.jackson.databind.JsonNode;

/** {@code reactions.total_count} 검증 — {@link GitHubIssueSearchClient}(이슈)와 {@link GitHubIssueCommentsClient}(댓글) 둘 다 같은 규칙을 쓴다. */
final class GitHubReactionCounts {
    private GitHubReactionCounts() {}

    static boolean isValidTotalCount(JsonNode node) {
        JsonNode totalCount = node.path("reactions").path("total_count");
        return totalCount.canConvertToInt() && totalCount.asInt() >= 0;
    }
}
