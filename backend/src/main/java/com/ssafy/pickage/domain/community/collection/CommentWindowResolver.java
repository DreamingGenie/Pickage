package com.ssafy.pickage.domain.community.collection;

import java.math.BigInteger;
import java.util.*;

final class CommentWindowResolver {
    static final int TARGET_COMMENT_COUNT = 100;

    private CommentWindowResolver() {}

    /**
     * Compatibility for selection-only callers; collection decides the previous page after reading
     * last.
     */
    static List<Integer> planAdditionalPages(int lastPage) {
        return lastPage <= 1 ? List.of() : List.of(lastPage);
    }

    static List<CollectedComment> selectLatest(List<CollectedComment> candidates) {
        var byId = new LinkedHashMap<String, CollectedComment>();
        for (var c : candidates) byId.put(c.sourceCommentId(), c);
        var sorted =
                byId.values().stream()
                        .sorted(
                                Comparator.comparing(CollectedComment::createdAt)
                                        .thenComparing(c -> new BigInteger(c.sourceCommentId())))
                        .toList();
        return List.copyOf(sorted.subList(Math.max(0, sorted.size() - 100), sorted.size()));
    }
}
