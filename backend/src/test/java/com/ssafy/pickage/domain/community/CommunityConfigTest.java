package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.net.http.HttpClient;

/**
 * S15P21A506-368 — env var가 "설정 안 됨"(null)이 아니라 "빈 문자열로 설정됨" 상태일 때도
 * FakeCommunitySummarizer로 안전하게 폴백하는지 확인한다. 운영에서 실제로 GMS_MODEL이 빈
 * 문자열로 배포돼 GMS가 매번 400을 반환하던 사고(status=400, "model": "")가 재발하지 않게 한다.
 */
class CommunityConfigTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Test
    void 값이_전부_있으면_GmsCommunitySummarizer를_쓴다() {
        var summarizer =
                CommunityConfig.resolveSummarizer(
                        CLIENT, "key", "https://gms.ssafy.io", "/v1/responses", "Authorization", "Bearer", "gpt-5.4-mini");

        assertThat(summarizer).isInstanceOf(GmsCommunitySummarizer.class);
    }

    @ParameterizedTest
    @CsvSource({
        "'', https://gms.ssafy.io, /v1/responses, Authorization, Bearer, gpt-5.4-mini",
        "key, '', /v1/responses, Authorization, Bearer, gpt-5.4-mini",
        "key, https://gms.ssafy.io, '', Authorization, Bearer, gpt-5.4-mini",
        "key, https://gms.ssafy.io, /v1/responses, '', Bearer, gpt-5.4-mini",
        "key, https://gms.ssafy.io, /v1/responses, Authorization, '', gpt-5.4-mini",
        "key, https://gms.ssafy.io, /v1/responses, Authorization, Bearer, ''",
    })
    void 값_하나라도_빈_문자열이면_Fake로_폴백한다(
            String apiKey, String baseUrl, String requestPath, String authHeader, String authScheme, String model) {
        var summarizer =
                CommunityConfig.resolveSummarizer(
                        CLIENT, apiKey, baseUrl, requestPath, authHeader, authScheme, model);

        assertThat(summarizer).isInstanceOf(FakeCommunitySummarizer.class);
    }

    @Test
    void 값이_아예_null이어도_Fake로_폴백한다() {
        var summarizer = CommunityConfig.resolveSummarizer(CLIENT, null, null, null, null, null, null);

        assertThat(summarizer).isInstanceOf(FakeCommunitySummarizer.class);
    }
}
