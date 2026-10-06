package com.ssafy.pickage.domain.community.refresh;

public enum RefreshStage {
    REPOSITORY_VERIFY("VERIFYING_REPOSITORY", "저장소 연결을 확인하고 있습니다."),
    ISSUE_SEARCH("SEARCHING_ISSUES", "공개 이슈를 검색하고 있습니다."),
    COMMENTS("COLLECTING_COMMENTS", "핵심 이슈의 공개 댓글을 확인하고 있습니다."),
    GMS("SUMMARIZING", "논의 내용을 요약하고 있습니다."),
    VALIDATING("VALIDATING", "요약 근거를 확인하고 있습니다."),
    PUBLISHING("PUBLISHING", "확인한 결과를 저장하고 있습니다.");
    private final String wireName, message;

    RefreshStage(String wireName, String message) {
        this.wireName = wireName;
        this.message = message;
    }

    public String wireName() {
        return wireName;
    }

    public String defaultMessage() {
        return message;
    }
}
