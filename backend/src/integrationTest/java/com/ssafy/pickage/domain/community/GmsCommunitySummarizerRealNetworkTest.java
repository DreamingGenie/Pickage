package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.net.http.HttpClient;
import java.time.Instant;
import java.util.List;

/**
 * 실제 {@code gms.ssafy.io}를 호출한다. {@link com.ssafy.pickage.domain.community.verification
 * .RepositoryVerificationRealNetworkTest}와 같은 패턴 — 키가 없는 환경(CI·다른 팀원)에서는 자동으로 skip된다.
 *
 * <p>2026-09-16 curl 실측(`docs/for_community/GMS_연동_참고.md`)은 평면 2-필드 스키마로만 구조화 출력을
 * 확인했다 — 이 시험은 실제로 이 클래스가 만드는 중첩 배열/객체 스키마와 `gpt-5.4-mini` 모델명이 그대로
 * 통하는지를 실제 호출로 확인하기 위한 것이다.
 *
 * <p>실행: {@code GMS_API_KEY=<발급받은 키> ./gradlew integrationTest --tests
 * "*.GmsCommunitySummarizerRealNetworkTest"} ({@code GMS_MODEL} 등 나머지는 2026-09-16 실측값으로
 * 기본 지정돼 있다 — 다르게 확인됐다면 환경변수로 덮어쓸 것)
 */
@EnabledIfEnvironmentVariable(named = "GMS_API_KEY", matches = ".+")
class GmsCommunitySummarizerRealNetworkTest {

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private GmsCommunitySummarizer client() {
        return new GmsCommunitySummarizer(
                HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build(),
                env("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com"),
                env("GMS_REQUEST_PATH", "/v1/responses"),
                System.getenv("GMS_API_KEY"),
                env("GMS_AUTH_HEADER", "Authorization"),
                env("GMS_AUTH_SCHEME", "Bearer"),
                env("GMS_MODEL", "gpt-5.4-mini"),
                2L * 1024 * 1024);
    }

    @Test
    void 실제_GMS_호출로_구조화_요약을_받는다() {
        var issue =
                new CollectedIssue(
                        7,
                        "App crashes on startup when config file is missing",
                        "open",
                        Instant.parse("2026-01-02T00:00:00Z"),
                        "asker",
                        1,
                        0,
                        CommentCollectionStatus.COMPLETE,
                        List.of(
                                new CollectedComment(
                                        "9007199254740993",
                                        "helper",
                                        "CONTRIBUTOR",
                                        false,
                                        Instant.parse("2026-01-02T01:00:00Z"),
                                        "Create an empty config.json before starting the app —"
                                                + " that fixed it for me.",
                                        "user-2")),
                        List.of(),
                        "701",
                        Instant.parse("2026-01-01T00:00:00Z"),
                        "user-1",
                        "The app throws a NullPointerException and exits immediately if"
                                + " config.json does not exist in the working directory.");

        TopicSummary summary = client().summarize(issue);

        System.out.println("[실네트워크 GMS 결과] " + summary);
        assertThat(summary.status())
                .as("gpt-5.4-mini·중첩 스키마 실호출 결과 — 실패하면 GMS_연동_참고.md 갱신 필요: %s", summary)
                .isEqualTo(SummaryStatus.READY);
        assertThat(summary.titleKo()).isNotBlank();
        assertThat(summary.summaryKo()).isNotBlank();
        assertThat(summary.discussionFlow()).isNotEmpty();
    }
}
