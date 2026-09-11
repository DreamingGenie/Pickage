package com.ssafy.pickage.domain.community.dto;

/** 커뮤니티 v2 계약. 공개 필드/내부 근거는 별도 DTO로 구분한다. */
public record CommunitySummaryResponse(
        int issueCount, long commentCount, long reactionCount, int openIssueCount) {}
