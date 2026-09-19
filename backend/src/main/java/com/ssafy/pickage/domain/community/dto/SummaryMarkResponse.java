package com.ssafy.pickage.domain.community.dto;

/** 요약문 안의 강조 구간(UTF-16 오프셋 {@code [start, end)}). 자세한 뜻은 {@code SummaryMarkPayload}. */
public record SummaryMarkResponse(int start, int end, String kind) {}
