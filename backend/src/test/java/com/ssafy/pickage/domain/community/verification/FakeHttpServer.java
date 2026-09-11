package com.ssafy.pickage.domain.community.verification;

import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.Function;

/**
 * 시험 전용 loopback HTTP 서버 — JDK 내장 {@code com.sun.net.httpserver}만 쓴다(WireMock 등 새 테스트 의존성을 추가하지
 * 않는다). npm·GitHub 응답을 흉내내 실제 네트워크 없이 {@link NpmRepositoryLookup}·{@link GitHubRepositoryClient}를
 * 검증한다.
 *
 * <p>{@code public}이다 — Phase 3({@code domain/community/collection}, S15P21A506-212)의 테스트도 같은 가짜
 * 서버가 필요하다. 정책 로직이 없는 순수 시험 유틸이라 {@code BoundedHttpReader}와 같은 이유로 새로 만들지 않고 가시성만 넓혀 재사용한다.
 */
public final class FakeHttpServer implements AutoCloseable {

    private final HttpServer server;

    private FakeHttpServer(HttpServer server) {
        this.server = server;
    }

    public static FakeHttpServer start() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.start();
            return new FakeHttpServer(server);
        } catch (IOException e) {
            throw new IllegalStateException("가짜 HTTP 서버 기동 실패", e);
        }
    }

    public void respond(String path, int status, String body, Map<String, String> headers) {
        server.createContext(
                path,
                exchange -> {
                    headers.forEach(
                            (name, value) -> exchange.getResponseHeaders().add(name, value));
                    byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(status, bytes.length);
                    try (var os = exchange.getResponseBody()) {
                        os.write(bytes);
                    }
                    exchange.close();
                });
    }

    /**
     * 200 OK({@code "{}"})을 돌려주면서 요청 헤더 하나를 {@code capture}에 담는다.
     *
     * <p>단언은 이 안에서 하지 않는다 — 여기는 서버 스레드라 {@code AssertionError}가 나도 테스트 스레드로 전파되지 않고 조용히 묻힌다. 값을 받아
     * 온 뒤 테스트 스레드에서 단언한다.
     */
    public void respondCapturingHeader(String path, String headerName, Consumer<String> capture) {
        server.createContext(
                path,
                exchange -> {
                    capture.accept(exchange.getRequestHeaders().getFirst(headerName));
                    byte[] bytes =
                            "{\"private\":false,\"archived\":false}"
                                    .getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200, bytes.length);
                    try (var os = exchange.getResponseBody()) {
                        os.write(bytes);
                    }
                    exchange.close();
                });
    }

    /**
     * 쿼리 파라미터 값(예: {@code page})에 따라 다른 응답을 준다 — GitHub 페이지네이션처럼 같은 경로를 여러 page로 반복 호출하는 API를 흉내낼 때
     * 쓴다. {@code answer}는 쿼리 문자열 전체(디코드 안 함, 필요하면 호출자가 {@link #queryParam}으로 값을 뽑는다)를 받아 {@link
     * Answer}를 돌려준다.
     */
    public void respondDynamic(String path, Function<String, Answer> answer) {
        server.createContext(
                path,
                exchange -> {
                    Answer result = answer.apply(exchange.getRequestURI().getRawQuery());
                    result.headers()
                            .forEach(
                                    (name, value) ->
                                            exchange.getResponseHeaders().add(name, value));
                    byte[] bytes = result.body().getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(result.status(), bytes.length);
                    try (var os = exchange.getResponseBody()) {
                        os.write(bytes);
                    }
                    exchange.close();
                });
    }

    /** {@code respondDynamic}에 넘긴 쿼리 문자열에서 파라미터 하나를 뽑는다. 없으면 {@code null}. */
    public static String queryParam(String rawQuery, String name) {
        if (rawQuery == null) {
            return null;
        }
        for (String pair : rawQuery.split("&")) {
            int eq = pair.indexOf('=');
            if (eq < 0) continue;
            String key = URLDecoder.decode(pair.substring(0, eq), StandardCharsets.UTF_8);
            if (key.equals(name)) {
                return URLDecoder.decode(pair.substring(eq + 1), StandardCharsets.UTF_8);
            }
        }
        return null;
    }

    public record Answer(int status, String body, Map<String, String> headers) {}

    /** 끝에 슬래시가 없다 — {@code GitHubRepositoryClient}의 {@code REAL_API_BASE}와 같은 규칙. */
    public String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
