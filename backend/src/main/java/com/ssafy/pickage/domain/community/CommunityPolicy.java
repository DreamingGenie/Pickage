package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.*;

import java.util.List;
import java.util.Map;
import java.util.Set;

/** 저장 버전과 공개 한계 문구를 함께 관리한다. 외부 문자열을 표시 문구로 사용하지 않는다. */
public final class CommunityPolicy {
    public static final short PAYLOAD_VERSION = 2;
    public static final String VERSION = "github-active-v1";
    public static final String SOURCE_NOTE = "검증된 저장소의 선택된 이슈 최대 2개와 이슈별 최신 댓글 최대 100개 기준입니다.";
    private static final Map<String, String> MESSAGES =
            Map.ofEntries(
                    Map.entry("REPOSITORY_SOURCE_CONFLICT", "npm과 등록된 저장소 정보가 달라 npm 연결을 확인했습니다."),
                    Map.entry("REPOSITORY_WIDE_SCOPE", "여러 패키지를 포함하는 저장소 전체의 논의입니다."),
                    Map.entry(
                            "ROOT_PACKAGE_SCOPE_HEURISTIC",
                            "루트 package.json 연결에 기반한 패키지 범위 추정입니다."),
                    Map.entry("NPM_REPOSITORY_ONLY", "npm의 저장소 연결 정보에 기반합니다."),
                    Map.entry("REPOSITORY_ARCHIVED", "보관된 저장소의 논의입니다."),
                    Map.entry("SEARCH_INCOMPLETE", "검색 결과가 불완전하여 논의 전체를 확인하지 못했습니다."),
                    Map.entry("ISSUE_FILTERED", "수집 범위에 포함되지 않는 이슈를 제외했습니다."),
                    Map.entry("COMMENTS_TRUNCATED", "댓글 일부만 수집했습니다."),
                    Map.entry("COMMENTS_UNAVAILABLE", "댓글을 확인하지 못했습니다."),
                    Map.entry("SUMMARY_INPUT_LIMITED", "입력 한도로 원문 일부만 요약에 사용했습니다."),
                    Map.entry("SUMMARY_UNAVAILABLE", "요약을 제공하지 못해 확인된 원문 제목과 수치를 표시합니다."),
                    Map.entry("RESPONSE_SIZE_LIMITED", "응답 크기 한도로 일부 자료를 확인하지 못했습니다."));

    private CommunityPolicy() {}

    public static LimitationPayload limitation(String code, Integer issue) {
        String message = MESSAGES.get(code);
        if (message == null) throw new IllegalArgumentException("Unknown limitation code");
        return new LimitationPayload(code, message, issue);
    }

    public static boolean validLimitation(LimitationPayload value) {
        return value != null
                && value.message() != null
                && value.message().equals(MESSAGES.get(value.code()));
    }

    public static SummaryStatus summaryStatus(List<TopicPayload> topics) {
        if (topics.isEmpty()) return SummaryStatus.SKIPPED;
        long failed = topics.stream().filter(t -> "FAILED".equals(t.summaryStatus())).count();
        if (failed == topics.size()) return SummaryStatus.FAILED;
        if (failed > 0 || topics.stream().anyMatch(t -> "PARTIAL".equals(t.summaryStatus())))
            return SummaryStatus.PARTIAL;
        return SummaryStatus.READY;
    }

    public static boolean incompleteData(List<LimitationPayload> limitations) {
        Set<String> partial =
                Set.of(
                        "SEARCH_INCOMPLETE",
                        "COMMENTS_TRUNCATED",
                        "COMMENTS_UNAVAILABLE",
                        "RESPONSE_SIZE_LIMITED");
        return limitations.stream().anyMatch(l -> partial.contains(l.code()));
    }
}
