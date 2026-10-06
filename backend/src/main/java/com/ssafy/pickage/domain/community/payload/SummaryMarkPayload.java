package com.ssafy.pickage.domain.community.payload;

/**
 * 요약문({@code summary_ko}) 안의 강조 구간. 위치는 UTF-16 코드 단위 오프셋이라 Java {@code String}과 JS 문자열이
 * 같은 값을 쓴다({@code [start, end)}). {@code kind}는 {@code KEY_TERM}(핵심어 — 굵게)과 {@code KEY_SENTENCE}(핵심 문장 —
 * 형광펜) 둘이다. 강조는 읽기 보조일 뿐이라 없거나 어긋나도 요약 자체에는 영향이 없다.
 */
public record SummaryMarkPayload(int start, int end, String kind) {
    public static final String KEY_TERM = "KEY_TERM";
    public static final String KEY_SENTENCE = "KEY_SENTENCE";
}
