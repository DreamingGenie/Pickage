package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
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

        TopicSummary summary = client().summarize(issue, Duration.ofSeconds(15));

        System.out.println("[실네트워크 GMS 결과] " + summary);
        assertThat(summary.status())
                .as("gpt-5.4-mini·중첩 스키마 실호출 결과 — 실패하면 GMS_연동_참고.md 갱신 필요: %s", summary)
                .isEqualTo(SummaryStatus.READY);
        assertThat(summary.titleKo()).isNotBlank();
        assertThat(summary.summaryKo()).isNotBlank();
        assertThat(summary.discussionFlow()).isNotEmpty();
    }

    /**
     * S15P21A506-373 0단계 — 댓글 85개 안팎(합성, 실제 GitHub 이슈 아님)으로 실제 GMS를 호출해
     * {@code max_output_tokens=2048} 근처에서 응답이 {@code incomplete}로 잘리는지, 페이로드 파싱이
     * 실패하는지를 관측한다. 이 테스트의 목적 자체가 "READY로 끝나는지 아닌지 관측"이므로,
     * {@link SummaryStatus#READY}를 단정하지 않는다 — 실패하면 {@link GmsCommunitySummarizer}에
     * 추가된 {@code log.warn}이 실제 {@code status}/파싱 실패 형태를 남긴다(콘솔·테스트 로그 확인).
     */
    @Test
    void 실제_GMS_호출로_대용량_댓글_이슈를_요약한다() {
        var issue = largeSyntheticIssue(85);

        TopicSummary summary = client().summarize(issue, Duration.ofSeconds(15));

        System.out.println(
                "[실네트워크 GMS 대형 fixture 결과] status="
                        + summary.status()
                        + ", flow.size="
                        + summary.discussionFlow().size()
                        + ", messages.size="
                        + summary.messages().size());
        assertThat(summary).as("항상 TopicSummary를 반환해야 함(예외 전파 금지)").isNotNull();
    }

    private static CollectedIssue largeSyntheticIssue(int commentCount) {
        String[] templates = {
            "I'm seeing the same issue on version %d.x — happens every time the config is"
                    + " missing a required field. Here's my workaround for now: I wrap the call"
                    + " in a try/catch and fall back to a default schema.",
            "Any update on this? We've been blocked by this for a couple of weeks and it's"
                    + " affecting our CI pipeline. Happy to help test a fix if someone puts one"
                    + " up.",
            "I think the root cause is that the validator doesn't narrow the union type"
                    + " correctly when the discriminant field is optional. I traced it down to"
                    + " the parser internals but haven't found a clean fix yet.",
            "+1, also hitting this. For anyone else stuck, downgrading to the previous minor"
                    + " version fixes it, but obviously that's not a long-term solution.",
            "Thanks for the detailed repro! I was able to reproduce it locally. Looking into a"
                    + " fix now — will open a PR once I have something working with tests."
        };
        List<CollectedComment> comments = new ArrayList<>(commentCount);
        Instant start = Instant.parse("2026-01-02T00:00:00Z");
        for (int i = 0; i < commentCount; i++) {
            String body = templates[i % templates.length] + " (comment #" + i + ")";
            comments.add(
                    new CollectedComment(
                            String.valueOf(9_100_000_000_000L + i),
                            "synthetic-user-" + (i % 20),
                            i % 7 == 0 ? "MEMBER" : "NONE",
                            false,
                            start.plusSeconds(3600L * i),
                            String.format(body, i % 5 + 1),
                            "synthetic-author-" + (i % 20)));
        }
        return new CollectedIssue(
                479,
                "Large synthetic issue for S15P21A506-373 0단계 diagnostics ("
                        + commentCount
                        + " comments)",
                "open",
                start.plusSeconds(3600L * commentCount),
                "synthetic-reporter",
                commentCount,
                0,
                CommentCollectionStatus.COMPLETE,
                comments,
                List.of(),
                "701701",
                start,
                "synthetic-reporter-id",
                "This is a synthetic (fabricated) issue body used only to test how"
                        + " GmsCommunitySummarizer behaves with a large number of comments. It"
                        + " is not a real GitHub issue and does not reference any real user or"
                        + " repository content.");
    }
}
