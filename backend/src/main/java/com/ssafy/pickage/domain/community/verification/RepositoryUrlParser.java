package com.ssafy.pickage.domain.community.verification;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * DB {@code package.repo_url}이나 npm {@code repository.url}처럼 신뢰할 수 없는 문자열에서
 * {@code owner/repo}만 뽑아낸다. <b>이 클래스는 어떤 네트워크 연결도 만들지 않는다</b> — 문자열
 * 파싱뿐이다. 실제 HTTP 호출은 여기서 뽑은 {@code owner}·{@code repo}(둘 다 GitHub API 경로
 * 세그먼트로만 쓰인다)로 항상 고정된 {@code api.github.com}에만 나간다({@code GitHubRepositoryClient}).
 * 이것이 이 Phase의 SSRF 방어 원리다 — 공격자가 넣은 host에 애초에 연결하지 않는다.
 *
 * <p>지원하는 형태: {@code https://github.com/owner/repo}, {@code git+https://...},
 * {@code git://github.com/owner/repo.git}, {@code git@github.com:owner/repo.git}(npm
 * {@code repository} 필드에서 흔한 SCP-스타일). host가 정확히 {@code github.com}이 아니면
 * (서브도메인·IP 리터럴·다른 forge 포함) {@link CandidateSource.NonGitHubHost}로 분류한다 —
 * 대소문자만 다른 경우는 허용한다.
 */
final class RepositoryUrlParser {

	// git@github.com:owner/repo.git 같은 SCP 스타일. URI 로 못 판다.
	private static final Pattern SCP_STYLE = Pattern.compile(
		"^(?:[a-zA-Z0-9_.-]+)@([a-zA-Z0-9.-]+):(.+)$");

	private static final String GITHUB_HOST = "github.com";

	private RepositoryUrlParser() {
	}

	static CandidateSource parse(String rawUrl, String npmDirectory) {
		if (rawUrl == null || rawUrl.isBlank()) {
			return new CandidateSource.Absent();
		}

		String normalized = stripGitPrefix(rawUrl.trim());

		Matcher scp = SCP_STYLE.matcher(normalized);
		if (scp.matches() && !normalized.contains("://")) {
			return classify(scp.group(1), scp.group(2), rawUrl, npmDirectory);
		}

		try {
			URI uri = new URI(normalized);
			String scheme = uri.getScheme();
			String host = uri.getHost();
			if (scheme == null || host == null) {
				return new CandidateSource.Absent();
			}
			if (!isAllowedScheme(scheme)) {
				return new CandidateSource.NonGitHubHost(rawUrl);
			}
			// 명시적 포트는 허용하지 않는다 — 정상적인 저장소 URL은 포트를 지정하지 않는다.
			if (uri.getPort() != -1) {
				return new CandidateSource.NonGitHubHost(rawUrl);
			}
			String path = uri.getPath();
			if (path == null || path.isBlank()) {
				return new CandidateSource.Absent();
			}
			return classify(host, path, rawUrl, npmDirectory);
		} catch (URISyntaxException e) {
			return new CandidateSource.Absent();
		}
	}

	private static boolean isAllowedScheme(String scheme) {
		String lower = scheme.toLowerCase();
		return lower.equals("https") || lower.equals("http") || lower.equals("git") || lower.equals("ssh");
	}

	private static String stripGitPrefix(String url) {
		// npm repository.url 에 흔한 "git+https://..." 표기.
		if (url.regionMatches(true, 0, "git+", 0, 4)) {
			return url.substring(4);
		}
		return url;
	}

	private static CandidateSource classify(String host, String path, String rawUrl, String npmDirectory) {
		if (!GITHUB_HOST.equalsIgnoreCase(host)) {
			return new CandidateSource.NonGitHubHost(rawUrl);
		}

		String[] segments = splitPath(path);
		if (segments.length < 2) {
			return new CandidateSource.Absent();
		}
		String owner = segments[0];
		String repo = stripDotGit(segments[1]);

		if (!isSafeSegment(owner) || !isSafeSegment(repo)) {
			// path traversal(".."), 빈 세그먼트, 제어문자 등 — 저장소 이름으로 쓸 수 없다.
			return new CandidateSource.Absent();
		}

		String directory = (npmDirectory == null || npmDirectory.isBlank()) ? null : npmDirectory.trim();
		return new CandidateSource.GitHubUrl(owner, repo, directory);
	}

	private static String[] splitPath(String path) {
		String trimmed = path.startsWith("/") ? path.substring(1) : path;
		if (trimmed.endsWith("/")) {
			trimmed = trimmed.substring(0, trimmed.length() - 1);
		}
		return trimmed.split("/", -1);
	}

	private static String stripDotGit(String repo) {
		return repo.endsWith(".git") ? repo.substring(0, repo.length() - 4) : repo;
	}

	private static boolean isSafeSegment(String segment) {
		if (segment == null || segment.isBlank()) {
			return false;
		}
		if (segment.equals(".") || segment.equals("..")) {
			return false;
		}
		return segment.chars().allMatch(c -> c == '-' || c == '_' || c == '.'
			|| Character.isLetterOrDigit(c));
	}
}
