package com.ssafy.pickage.domain.community.verification;

import java.net.http.HttpResponse;
import java.time.*;
import java.time.format.DateTimeFormatter;

/** 동일 token의 core/search와 secondary 제한을 모든 커뮤니티 client가 공유한다. */
public final class GitHubRateGate {
    private final Clock clock;
    private Instant core = Instant.MIN, search = Instant.MIN, secondary = Instant.MIN;

    public GitHubRateGate() {
        this(Clock.systemUTC());
    }

    public GitHubRateGate(Clock clock) {
        this.clock = clock;
    }

    public synchronized Instant retryAt() {
        Instant next = max(secondary, max(core, search));
        return next.isAfter(clock.instant()) ? next : null;
    }

    public synchronized void check(String resource) {
        Instant next = max(secondary, "search".equals(resource) ? search : core);
        if (next.isAfter(clock.instant()))
            throw new GitHubRateLimitException("GitHub rate limit", next);
    }

    public synchronized void observe(String resource, HttpResponse<?> response) {
        Instant now = clock.instant();
        int status = response.statusCode();
        boolean exhausted =
                response.headers().firstValue("X-RateLimit-Remaining").orElse("").equals("0");
        Instant until = null;
        if (exhausted) {
            until =
                    parseReset(
                            response.headers().firstValue("X-RateLimit-Reset").orElse(null), now);
            if ("search".equals(resource)) search = max(search, until);
            else core = max(core, until);
        }
        if (status == 429
                || (status == 403
                        && (exhausted
                                || response.headers().firstValue("Retry-After").isPresent()
                                || secondaryBody(response)))) {
            String retry = response.headers().firstValue("Retry-After").orElse(null);
            if (!exhausted || retry != null) {
                secondary = max(secondary, parseRetry(retry, now));
                until = until == null ? secondary : max(until, secondary);
            }
            throw new GitHubRateLimitException("GitHub rate limit", until);
        }
    }

    /** 본문 초과/timeout이어도 이미 받은 token 제한 헤더는 잃지 않는다. */
    public synchronized void observeHeaders(String resource, HttpResponse.ResponseInfo response) {
        Instant now = clock.instant();
        boolean exhausted =
                response.headers().firstValue("X-RateLimit-Remaining").orElse("").equals("0");
        if (exhausted) {
            Instant until =
                    parseReset(
                            response.headers().firstValue("X-RateLimit-Reset").orElse(null), now);
            if ("search".equals(resource)) search = max(search, until);
            else core = max(core, until);
        }
        String retry = response.headers().firstValue("Retry-After").orElse(null);
        if ((response.statusCode() == 429 || response.statusCode() == 403 && retry != null)
                && (!exhausted || retry != null))
            secondary = max(secondary, parseRetry(retry, now));
    }

    private static boolean secondaryBody(HttpResponse<?> response) {
        if (!(response.body() instanceof java.io.InputStream body) || !body.markSupported())
            return false;
        try {
            body.mark(Integer.MAX_VALUE);
            String text =
                    new String(body.readNBytes(8192), java.nio.charset.StandardCharsets.UTF_8)
                            .toLowerCase(java.util.Locale.ROOT);
            body.reset();
            return text.contains("secondary rate")
                    || text.contains("abuse detection")
                    || text.contains("rate limit");
        } catch (java.io.IOException e) {
            return false;
        }
    }

    private static Instant parseReset(String value, Instant now) {
        try {
            Instant t = Instant.ofEpochSecond(Long.parseLong(value));
            return t.isAfter(now) ? t : now.plusSeconds(60);
        } catch (RuntimeException e) {
            return now.plusSeconds(60);
        }
    }

    private static Instant parseRetry(String value, Instant now) {
        try {
            return now.plusSeconds(Math.max(60, Long.parseLong(value)));
        } catch (RuntimeException e) {
            try {
                return max(
                        now.plusSeconds(60),
                        ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME)
                                .toInstant());
            } catch (RuntimeException ignored) {
                return now.plusSeconds(60);
            }
        }
    }

    private static Instant max(Instant a, Instant b) {
        return a.isAfter(b) ? a : b;
    }
}
