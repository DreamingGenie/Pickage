package com.ssafy.pickage.domain.docs;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/*
* jsDelivr 에서 받아 문헌 한 장을 만든다.
*
* 프리로드가 최신 2개 안정 버전만 깔아 두었고 94,416개 패키지가 2개 이상을 갖고 있어,
* 사용자가 옛 버전을 고르면 없는 것이 정상이다. 그때 이 경로가 돈다.
*
* 호출은 최대 셋이다. 프리로드는 .d.ts 본문까지 받아 넷이었는데, 문헌에는 .d.ts 경로만
* 적히고 내용은 들어가지 않아 여기서는 안 받는다.
*
*   1. 파일 목록      data.jsdelivr.com/v1/packages/npm/{ref}?structure=flat
*   2. package.json   cdn.jsdelivr.net/npm/{ref}/package.json
*   3. README         1번이 경로를 찾았을 때만
*
* 1·2 는 서로 몰라도 되니 같이 보낸다. 3 은 1 의 결과가 있어야 해서 그다음이다.
* 왕복 두 번이라 정상이면 1초 안쪽이다.
*/
@Component
public class DocFetcher {

	private static final Logger log = LoggerFactory.getLogger(DocFetcher.class);

	private static final String CDN = "https://cdn.jsdelivr.net/npm";
	private static final String DATA_API = "https://data.jsdelivr.com/v1/packages/npm";

	// 연락처를 남긴다. 무명 클라이언트는 한도를 더 좁게 먹는다.
	private static final String USER_AGENT = "pickage-docs/1.0 (+https://j15a506.p.ssafy.io)";

	/*
	 * 그 버전이 CDN 에 없다는 뜻으로 보는 응답들.
	 *
	 * 403 이 대부분이다 — 프리로드 실측으로 못 받은 754건 중 677건이었다. 실패가 아니라
	 * 흔한 정상 경로라서, 다시 시도하지 않고 음성 캐시로 넘긴다.
	 */
	private static final Set<Integer> ABSENT = Set.of(403, 404, 410, 451);

	private static final List<String> README_NAMES =
		List.of("readme.md", "readme.markdown", "readme", "readme.txt", "readme.rst");
	private static final List<String> DTS_SUFFIX = List.of(".d.ts", ".d.mts", ".d.cts");

	private final HttpClient http = HttpClient.newBuilder()
		.connectTimeout(Duration.ofSeconds(5))
		.followRedirects(HttpClient.Redirect.NORMAL)
		.build();
	private final ObjectMapper json = new ObjectMapper();

	/*
	 * 문헌 한 장을 받아 만든다. CDN 에 없으면 빈 값이다.
	 *
	 * deadline 은 요청 전체가 공유하는 벽시계다. 패키지 셋이 같이 돌 때 앞의 하나가 예산을
	 * 다 먹지 않게 하려는 것이다.
	 */
	public Optional<String> fetch(String name, String version, long deadlineNanos) {
		String ref = reference(name, version);
		try {
			CompletableFuture<byte[]> listing =
				get(DATA_API + "/" + ref + "?structure=flat", deadlineNanos);
			CompletableFuture<byte[]> packageJson =
				get(CDN + "/" + ref + "/package.json", deadlineNanos);

			JsonNode tree = json.readTree(listing.join());
			JsonNode pkg = json.readTree(packageJson.join());

			Tree files = readTree(tree);
			DocAssembler.Manifest manifest = readManifest(pkg, name);

			String body = "";
			if (files.readmePath() != null) {
				byte[] raw = get(CDN + "/" + ref + "/" + encodePath(files.readmePath()),
					deadlineNanos).join();
				body = DocAssembler.clip(raw);
			}

			DocAssembler.Tree assemblerTree = new DocAssembler.Tree(
				files.count(), files.unpackedBytes(), files.readmePath(), files.dts());
			String kind = DocAssembler.entryKind(manifest, assemblerTree,
				strings(pkg.path("files")), hasStyle(pkg.path("exports")));
			int proseChars = DocAssembler.charCount(DocAssembler.prose(body));
			String status = DocAssembler.docStatus(proseChars, manifest, assemblerTree);
			int readmeBytes = body.getBytes(StandardCharsets.UTF_8).length;

			return Optional.of(DocAssembler.assemble(name, version, manifest, assemblerTree,
				body, kind, status, readmeBytes, proseChars));
		} catch (Absent e) {
			return Optional.empty();
		} catch (Exception e) {
			log.info("문헌을 받지 못했다 {}@{}: {}", name, version, e.toString());
			return Optional.empty();
		}
	}

	private record Tree(int count, long unpackedBytes, String readmePath, List<String> dts) {}

	// CDN 에 그 버전이 없다는 신호. 재시도하지 않고 위로 올린다.
	private static final class Absent extends RuntimeException {
		Absent(String message) {
			super(message, null, false, false);
		}
	}

	/*
	 * 한 번 받아 온다. 남은 예산 안에서만 다시 시도한다.
	 *
	 * 429 의 Retry-After 는 900초까지 오는데 그대로 자면 요청이 물린다. 남은 예산보다 길면
	 * 기다리지 않고 포기한다 — 이 건은 문헌 없이 가고, 다음 요청이 다시 시도한다.
	 */
	private CompletableFuture<byte[]> get(String url, long deadlineNanos) {
		return CompletableFuture.supplyAsync(() -> {
			RuntimeException last = null;
			for (int attempt = 0; attempt < DocsProperties.MAX_ATTEMPTS; attempt++) {
				long remain = deadlineNanos - System.nanoTime();
				if (remain <= 0) {
					throw new IllegalStateException("예산을 다 썼다: " + url);
				}
				Duration timeout = Duration.ofNanos(
					Math.min(remain, DocsProperties.CALL_TIMEOUT.toNanos()));
				try {
					HttpResponse<byte[]> res = http.send(
						HttpRequest.newBuilder(URI.create(url))
							.header("User-Agent", USER_AGENT)
							.timeout(timeout)
							.GET()
							.build(),
						HttpResponse.BodyHandlers.ofByteArray());

					int code = res.statusCode();
					if (code == 200) {
						return res.body();
					}
					if (ABSENT.contains(code)) {
						throw new Absent("HTTP " + code + " " + url);
					}
					if (code == 429) {
						sleepWithin(retryAfter(res), deadlineNanos);
						continue;
					}
					if (code < 500) {
						throw new IllegalStateException("HTTP " + code + " " + url);
					}
					last = new IllegalStateException("HTTP " + code + " " + url);
				} catch (Absent e) {
					throw e;
				} catch (IOException e) {
					last = new IllegalStateException(e.toString());
				} catch (InterruptedException e) {
					Thread.currentThread().interrupt();
					throw new IllegalStateException("중단됐다: " + url);
				}
				sleepWithin(Duration.ofMillis(200L << attempt), deadlineNanos);
			}
			throw last != null ? last : new IllegalStateException("받지 못했다: " + url);
		});
	}

	// 남은 예산을 넘지 않는 만큼만 기다린다. 넘으면 아예 안 기다리고 포기한다.
	private static void sleepWithin(Duration wait, long deadlineNanos) {
		long remain = deadlineNanos - System.nanoTime();
		if (remain <= 0 || wait.toNanos() > remain) {
			throw new IllegalStateException("남은 예산보다 대기가 길다");
		}
		try {
			Thread.sleep(wait.toMillis());
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("중단됐다");
		}
	}

	private static Duration retryAfter(HttpResponse<?> res) {
		return res.headers().firstValue("retry-after")
			.map(v -> {
				try {
					return Duration.ofSeconds(Long.parseLong(v.trim()));
				} catch (NumberFormatException e) {
					return Duration.ofSeconds(1);
				}
			})
			.orElse(Duration.ofSeconds(1));
	}

	/*
	 * 파일 경로를 주소에 넣을 수 있게 인코딩한다.
	 *
	 * 목록에 공백이 든 경로가 섞여 있다 — jquery-file-download@1.4.6 의
	 * "src/Scripts/ jquery.fileDownload.d.ts" 가 그렇다. 그대로 붙이면 요청을 보내기도 전에
	 * 거절당한다. 프리로드가 실제로 여기서 죽었다.
	 */
	private static String encodePath(String path) {
		StringBuilder b = new StringBuilder();
		for (String part : path.split("/", -1)) {
			if (b.length() > 0) {
				b.append('/');
			}
			b.append(URLEncoder.encode(part, StandardCharsets.UTF_8).replace("+", "%20"));
		}
		return b.toString();
	}

	private static String reference(String name, String version) {
		StringBuilder b = new StringBuilder();
		for (String part : name.split("/", -1)) {
			if (b.length() > 0) {
				b.append('/');
			}
			b.append(URLEncoder.encode(part, StandardCharsets.UTF_8)
				.replace("+", "%20").replace("%40", "@"));
		}
		return b + "@" + version;
	}

	/*
	 * 파일 목록에서 README 경로와 .d.ts 목록, 크기 합을 뽑는다.
	 *
	 * README 는 루트에 있는 것만 본다. 하위 폴더의 README 를 집으면 패키지 전체가 아니라
	 * 그 폴더 설명이 문헌 본문이 된다.
	 */
	private static Tree readTree(JsonNode tree) {
		int count = 0;
		long bytes = 0;
		String readme = null;
		List<String> dts = new ArrayList<>();

		for (JsonNode f : tree.path("files")) {
			String raw = f.path("name").asText("");
			if (raw.isEmpty()) {
				continue;
			}
			String path = raw.startsWith("/") ? raw.substring(1) : raw;
			count++;
			bytes += f.path("size").asLong(0);

			String lower = path.toLowerCase(Locale.ROOT);
			if (readme == null && !path.contains("/") && README_NAMES.contains(lower)) {
				readme = path;
			}
			if (DTS_SUFFIX.stream().anyMatch(lower::endsWith)) {
				dts.add(path);
			}
		}
		dts.sort(Comparator.naturalOrder());
		return new Tree(count, bytes, readme, dts.subList(0, Math.min(20, dts.size())));
	}

	/*
	 * package.json 을 정규화한다. 원문은 형식이 제각각이라 여기서 편다.
	 *
	 * bin 이 문자열이면 패키지 이름이 곧 명령 이름이고, keywords 가 쉼표 문자열일 때가 있고
	 * (lodash), license 는 {"type":"MIT"} 옛 형식이 남아 있다. 읽는 쪽이 매번 그 분기를
	 * 하지 않게 한다.
	 */
	private static DocAssembler.Manifest readManifest(JsonNode pkg, String name) {
		JsonNode exports = pkg.path("exports");
		List<String> subs = subpaths(exports);

		return new DocAssembler.Manifest(
			pkg.path("description").asText("").trim(),
			keywords(pkg.path("keywords")),
			license(pkg.path("license")),
			pkg.path("type").isTextual() ? pkg.path("type").asText() : null,
			truthy(pkg.path("main")),
			pkg.path("style").isTextual() ? pkg.path("style").asText() : null,
			bin(pkg.path("bin"), name),
			subs.size(),
			subs.subList(0, Math.min(DocAssembler.MAX_SUBPATHS, subs.size())).stream()
				.map(DocAssembler::lstripDotSlash).toList(),
			pkg.path("dependencies").size());
	}

	/*
	 * 값이 "있다" 로 볼 만한지 본다. 파이썬 bool() 과 같은 판정이다.
	 *
	 * @types 패키지들이 main 을 빈 문자열로 적어 둔다. 필드 유무만 보면 그 문서들이
	 * "main 있음" 으로 뒤집혀, 프리로드가 깔아 둔 문헌과 같은 패키지인데 다른 글이 된다.
	 * TYPES 가 코퍼스의 절반이라 이 한 줄이 절반을 가른다.
	 */
	private static boolean truthy(JsonNode node) {
		if (node == null || node.isMissingNode() || node.isNull()) {
			return false;
		}
		if (node.isTextual()) {
			return !node.asText().isEmpty();
		}
		if (node.isBoolean()) {
			return node.asBoolean();
		}
		if (node.isNumber()) {
			return node.asDouble() != 0;
		}
		if (node.isContainerNode()) {
			return node.size() > 0;
		}
		return true;
	}

	// exports 에서 우리가 쓰는 subpath 만 추린다. 글로브와 package.json 은 뺀다.
	private static List<String> subpaths(JsonNode exports) {
		List<String> out = new ArrayList<>();
		if (exports.isObject()) {
			exports.fieldNames().forEachRemaining(k -> {
				if (k.startsWith(".") && !k.contains("*") && !k.equals("./package.json")) {
					out.add(k);
				}
			});
		}
		out.sort(Comparator.naturalOrder());
		return out;
	}

	// exports 어딘가에 스타일시트가 걸려 있는지 본다. 값이 중첩 조건일 수 있어 재귀로 훑는다.
	private static boolean hasStyle(JsonNode node) {
		if (node.isTextual()) {
			String v = node.asText().toLowerCase(Locale.ROOT);
			return v.endsWith(".css") || v.endsWith(".scss") || v.endsWith(".sass")
				|| v.endsWith(".less");
		}
		for (JsonNode child : node) {
			if (hasStyle(child)) {
				return true;
			}
		}
		return false;
	}

	private static List<String> bin(JsonNode node, String name) {
		if (node.isTextual()) {
			String[] parts = name.split("/");
			return List.of(parts[parts.length - 1]);
		}
		if (node.isObject()) {
			List<String> out = new ArrayList<>();
			node.fieldNames().forEachRemaining(out::add);
			out.sort(Comparator.naturalOrder());
			return out;
		}
		return List.of();
	}

	private static List<String> keywords(JsonNode node) {
		if (node.isTextual()) {
			return java.util.Arrays.stream(node.asText().split(","))
				.map(String::trim).filter(s -> !s.isEmpty()).toList();
		}
		if (node.isArray()) {
			List<String> out = strings(node);
			return out.subList(0, Math.min(40, out.size()));
		}
		return List.of();
	}

	private static String license(JsonNode node) {
		if (node.isTextual() && !node.asText().isBlank()) {
			return cut(node.asText().trim());
		}
		if (node.isObject() && node.path("type").isTextual()) {
			return cut(node.path("type").asText());
		}
		return null;
	}

	private static String cut(String s) {
		return s.length() <= 100 ? s : s.substring(0, 100);
	}

	private static List<String> strings(JsonNode node) {
		List<String> out = new ArrayList<>();
		for (JsonNode n : node) {
			if (n.isTextual()) {
				out.add(n.asText());
			}
		}
		return out;
	}
}
