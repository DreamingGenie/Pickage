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
 * <p>2026-09-16 curl 실측(`docs/history/0923_0917_pickage_final_set_archive/for_community/GMS_연동_참고.md`)은 평면 2-필드 스키마로만 구조화 출력을
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
                                        "user-2",
                                        0)),
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
        assertThat(summary.messages()).isNotEmpty();
    }

    /**
     * S15P21A506-408 — 하이라이트 댓글 4개 + 핵심어·핵심 문장. 실제 GitHub 이슈가 아닌 합성 이슈로 전체 경로
     * (highlights → GMS → 검증기)를 돌려, 발화가 입력 댓글 수만큼 나오고 강조 구간이 요약문 안에서 유효한지 본다.
     * 강조는 모델이 요약문에서 글자 그대로 옮겨야 하므로 실제 모델이 그 지시를 따르는지가 이 시험의 관심사다.
     */
    @Test
    void 실제_GMS_호출로_발화_4개와_핵심어_강조를_받는다() {
        var base = Instant.parse("2026-02-01T00:00:00Z");
        var comments =
                List.of(
                        new CollectedComment("5001", "reporter2", "NONE", false, base.plusSeconds(60),
                                "Same here on Android 13 with release builds. Debug builds work fine, which is"
                                        + " strange. Cleartext traffic is disabled in our manifest.",
                                "u-2", 12),
                        new CollectedComment("5002", "maintainer", "MEMBER", false, base.plusSeconds(120),
                                "This is almost always the Android network security config, not axios. Release"
                                        + " builds block cleartext HTTP unless you allow the host explicitly.",
                                "u-3", 5),
                        new CollectedComment("5003", "reporter2", "NONE", false, base.plusSeconds(180),
                                "Confirmed — adding android:usesCleartextTraffic=\"true\" for our staging host"
                                        + " fixed it. Thanks!",
                                "u-2", 2),
                        new CollectedComment("5004", "helper", "CONTRIBUTOR", false, base.plusSeconds(240),
                                "For production you should switch the endpoint to HTTPS instead of enabling"
                                        + " cleartext globally; a domain-scoped network_security_config.xml is safer.",
                                "u-4", 8),
                        new CollectedComment("5005", "dependabot", "NONE", true, base.plusSeconds(300),
                                "Bump axios from 1.6.0 to 1.6.2", "bot-1", 99));
        var issue =
                new CollectedIssue(
                        88,
                        "Network Error on Android release builds only",
                        "closed",
                        base.plusSeconds(400),
                        "reporter1",
                        comments.size(),
                        3,
                        CommentCollectionStatus.COMPLETE,
                        comments,
                        List.of(),
                        "881",
                        base,
                        "u-1",
                        "Requests succeed on iOS and in Android debug builds but fail with 'Network Error' in"
                                + " Android release builds. The endpoint is plain HTTP on port 8080.");

        var bundle = CommunitySummarySourceBundle.highlights(issue);
        assertThat(bundle.issue().comments()).hasSize(4); // Bot 댓글은 후보에서 빠진다

        TopicSummary raw = client().summarize(bundle.issue(), Duration.ofSeconds(30));
        TopicSummary summary = CommunitySummaryValidator.validate(bundle, raw);

        System.out.println("[실네트워크 GMS 강조 결과] raw.keyTerms=" + raw.keyTerms()
                + ", raw.keySentences=" + raw.keySentences() + ", messages=" + raw.messages().size());
        System.out.println("[실네트워크 GMS 요약문] " + summary.summaryKo());
        for (var mark : summary.summaryMarks())
            System.out.println("  " + mark.kind() + " [" + mark.start() + "," + mark.end() + ") "
                    + summary.summaryKo().substring(mark.start(), mark.end()));

        assertThat(summary.status())
                .as("실호출 결과 — 실패하면 프롬프트·스키마를 다시 봐야 한다: %s", raw)
                .isEqualTo(SummaryStatus.READY);
        assertThat(summary.messages())
                .as("입력 댓글 하나당 발화 하나(최대 4개)")
                .hasSize(bundle.issue().comments().size());
        assertThat(summary.summaryMarks()).as("핵심어·핵심 문장이 요약문에서 유효한 구간으로 남아야 한다").isNotEmpty();
        for (var mark : summary.summaryMarks())
            assertThat(mark.start()).isBetween(0, summary.summaryKo().length() - 1);
    }

    /**
     * S15P21A506-373 0단계 — 댓글 85개 안팎(합성, 실제 GitHub 이슈 아님)으로 실제 GMS를 호출해
     * {@code max_output_tokens=2048} 근처에서 응답이 {@code incomplete}로 잘리는지, 페이로드 파싱이
     * 실패하는지를 관측한다. 이 테스트의 목적 자체가 "READY로 끝나는지 아닌지 관측"이므로,
     * {@link SummaryStatus#READY}를 단정하지 않는다 — 실패하면 {@link GmsCommunitySummarizer}에
     * 추가된 {@code log.warn}이 실제 {@code status}/파싱 실패 형태를 남긴다(콘솔·테스트 로그 확인).
     *
     * <p>댓글 본문은 코드 블록·스택트레이스를 포함해 500~1200자 안팎으로 만든다(짧은 템플릿
     * 반복 댓글로는 모델 출력이 작아 {@code max_output_tokens}에 못 미쳐 {@code incomplete}가
     * 재현되지 않는 것을 먼저 확인했다 — 이 무게로 다시 확인한다).
     */
    @Test
    void 실제_GMS_호출로_대용량_댓글_이슈를_요약한다() {
        var issue = largeSyntheticIssue(85);

        TopicSummary summary = client().summarize(issue, Duration.ofSeconds(15));

        System.out.println(
                "[실네트워크 GMS 대형 fixture 결과] status="
                        + summary.status()
                        + ", messages.size="
                        + summary.messages().size());
        assertThat(summary).as("항상 TopicSummary를 반환해야 함(예외 전파 금지)").isNotNull();
    }

    private static CollectedIssue largeSyntheticIssue(int commentCount) {
        String[] templates = {
            """
            I can reproduce this consistently on v{V}.x. Minimal repro:

            ```ts
            import { z } from "somelib";
            const Config = z.object({
              host: z.string(),
              port: z.number().int().positive(),
              retries: z.number().optional(),
            });
            const raw = JSON.parse(fs.readFileSync("config.json", "utf8"));
            const parsed = Config.parse(raw); // <- throws here when retries is a string
            ```

            Stack trace:
            ```
            ZodError: Invalid input
              at Config.parse (dist/index.cjs:412:19)
              at loadConfig (src/config.ts:28:34)
              at Object.<anonymous> (src/index.ts:9:20)
              at Module._compile (node:internal/modules/cjs/loader:1256:14)
            ```

            My node version is 20.11, package version is v{V}.2.0. Happy to share the full
            config.json if that helps narrow it down further.
            """,
            """
            Following up after digging in a bit more — I think the issue is in how the
            discriminated union resolves when one branch has an optional discriminant key.
            When I trace through the internal `_parse` call, the union resolver picks the
            first matching branch by looking at required keys only, so an object missing the
            discriminant entirely still matches branch A instead of failing fast. Here's a
            smaller repro that isolates just that behavior:

            ```ts
            const A = z.object({ kind: z.literal("a"), value: z.string() });
            const B = z.object({ kind: z.literal("b").optional(), value: z.number() });
            const U = z.discriminatedUnion("kind", [A, B]);
            console.log(U.safeParse({ value: 42 }));
            ```

            This prints a success with branch A coerced, which is clearly wrong given `value`
            isn't even a string here. I don't have a fix yet but wanted to write this down
            before I lose the thread.
            """,
            """
            +1, hitting the exact same crash in production. For anyone stuck on this in the
            meantime, here's the workaround we shipped: wrap the parse call and fall back to
            a manually-constructed default object, then log a warning so we notice when it
            happens.

            ```ts
            function safeLoad(raw: unknown) {
              const result = Config.safeParse(raw);
              if (!result.success) {
                console.warn("config parse failed, using defaults", result.error.format());
                return DEFAULT_CONFIG;
              }
              return result.data;
            }
            ```

            Not ideal since it silently masks bad configs, but it stopped the crashes while
            we wait for an upstream fix. Environment: node 18.19, alpine docker image,
            package-lock pinned to v{V}.1.3.
            """,
            """
            Thanks both for the detailed repros — this is genuinely useful. I was able to
            reproduce the union resolution bug locally with the second snippet above. Rough
            plan for a fix: change the discriminated-union matcher to require the discriminant
            key to be *present and equal* to the literal, not just "no conflicting required
            key missing". That should make the failing case above correctly report an error
            instead of silently matching branch A. I'll open a draft PR with a fix and a
            regression test covering optional-discriminant branches; will link it here once
            it's up. Please hold off on further workarounds until we confirm this doesn't
            regress the existing discriminated-union test suite (there are ~40 cases there).
            """,
            """
            Just pushed a draft fix and ran the full suite locally — all existing
            discriminated-union tests still pass, plus the two new regression cases from this
            thread. Before/after on the repro:

            ```
            // before
            { success: true, data: { kind: 'a', value: 42 } }
            // after
            { success: false, error: ZodError: [ { code: 'invalid_union_discriminator', ... } ] }
            ```

            If anyone here can pull the branch and confirm against their real config schema
            (not just this minimal repro) that would help a lot before we merge — especially
            if you were relying on the old (buggy) coercion behavior anywhere, since this is
            technically a breaking change for you.
            """
        };
        List<CollectedComment> comments = new ArrayList<>(commentCount);
        Instant start = Instant.parse("2026-01-02T00:00:00Z");
        for (int i = 0; i < commentCount; i++) {
            String body =
                    templates[i % templates.length].replace("{V}", String.valueOf(i % 5 + 1))
                            + "\n\n(synthetic comment #"
                            + i
                            + ")";
            comments.add(
                    new CollectedComment(
                            String.valueOf(9_100_000_000_000L + i),
                            "synthetic-user-" + (i % 20),
                            i % 7 == 0 ? "MEMBER" : "NONE",
                            false,
                            start.plusSeconds(3600L * i),
                            body,
                            "synthetic-author-" + (i % 20),
                            0));
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
                        + " GmsCommunitySummarizer behaves with a large number of long,"
                        + " code-heavy comments. It is not a real GitHub issue and does not"
                        + " reference any real user, repository, or package content.");
    }
}
