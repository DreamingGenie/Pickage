package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.*;

import java.util.List;

/**
 * C1 adapter의 구조화된 산출물. support는 검증 후 폐기하고 snapshot에 저장하지 않는다.
 *
 * <p>{@code keyTerms}·{@code keySentences}는 모델이 "요약문에서 그대로 옮겨 온" 문자열이라 **아직 믿지 않는다**.
 * {@link CommunitySummaryValidator}가 요약문 안에서 실제로 찾아 위치를 계산한 것만 {@code summaryMarks}로 남긴다.
 *
 * <p>논의 흐름({@code flow})은 만들지 않는다(S15P21A506-412). 화면이 S15P21A506-406 부터 그리지 않아 출력 토큰만 썼다.
 */
public record TopicSummary(
        String titleKo,
        String summaryKo,
        List<MessagePayload> messages,
        SummaryStatus status,
        List<SourceRef> summarySupport,
        List<String> keyTerms,
        List<String> keySentences,
        List<SummaryMarkPayload> summaryMarks) {
    public record SourceRef(String type, String id) {}

    /** 강조 정보 없이 만드는 기존 생성자. */
    public TopicSummary(
            String titleKo,
            String summaryKo,
            List<MessagePayload> messages,
            SummaryStatus status,
            List<SourceRef> summarySupport) {
        this(titleKo, summaryKo, messages, status, summarySupport, List.of(), List.of(), List.of());
    }

    public static TopicSummary failed() {
        return new TopicSummary(null, null, List.of(), SummaryStatus.FAILED, List.of());
    }
}
