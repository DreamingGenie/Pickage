package com.ssafy.pickage.domain.community.verification;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.function.Consumer;

import com.sun.net.httpserver.HttpServer;

/**
 * 시험 전용 loopback HTTP 서버 — JDK 내장 {@code com.sun.net.httpserver}만 쓴다(WireMock 등
 * 새 테스트 의존성을 추가하지 않는다). npm·GitHub 응답을 흉내내 실제 네트워크 없이
 * {@link NpmRepositoryLookup}·{@link GitHubRepositoryClient}를 검증한다.
 */
final class FakeHttpServer implements AutoCloseable {

	private final HttpServer server;

	private FakeHttpServer(HttpServer server) {
		this.server = server;
	}

	static FakeHttpServer start() {
		try {
			HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
			server.start();
			return new FakeHttpServer(server);
		} catch (IOException e) {
			throw new IllegalStateException("가짜 HTTP 서버 기동 실패", e);
		}
	}

	void respond(String path, int status, String body, Map<String, String> headers) {
		server.createContext(path, exchange -> {
			headers.forEach((name, value) -> exchange.getResponseHeaders().add(name, value));
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
	 * <p>단언은 이 안에서 하지 않는다 — 여기는 서버 스레드라 {@code AssertionError}가 나도
	 * 테스트 스레드로 전파되지 않고 조용히 묻힌다. 값을 받아 온 뒤 테스트 스레드에서
	 * 단언한다.
	 */
	void respondCapturingHeader(String path, String headerName, Consumer<String> capture) {
		server.createContext(path, exchange -> {
			capture.accept(exchange.getRequestHeaders().getFirst(headerName));
			byte[] bytes = "{}".getBytes(StandardCharsets.UTF_8);
			exchange.sendResponseHeaders(200, bytes.length);
			try (var os = exchange.getResponseBody()) {
				os.write(bytes);
			}
			exchange.close();
		});
	}

	/** 끝에 슬래시가 없다 — {@code GitHubRepositoryClient}의 {@code REAL_API_BASE}와 같은 규칙. */
	String baseUrl() {
		return "http://127.0.0.1:" + server.getAddress().getPort();
	}

	@Override
	public void close() {
		server.stop(0);
	}
}
