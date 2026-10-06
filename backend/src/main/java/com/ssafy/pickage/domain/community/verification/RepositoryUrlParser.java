package com.ssafy.pickage.domain.community.verification;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** metadata URL은 후보 판정에만 사용한다. 실제 호출은 고정 API 경로로 조립한다. */
final class RepositoryUrlParser {
    private RepositoryUrlParser() {}

    static CandidateSource parse(String raw, String directory) {
        if (raw == null) return new CandidateSource.Absent();
        if (raw.isBlank()) return new CandidateSource.Invalid();
        try {
            String value = raw.trim().replaceFirst("(?i)^git\\+", "");
            if (value.startsWith("git@") && !value.contains("://"))
                value = "ssh://" + value.replaceFirst(":", "/");
            URI uri = URI.create(value);
            String scheme = uri.getScheme(), host = uri.getHost();
            if (scheme == null || host == null) return new CandidateSource.Invalid();
            if (!java.util.Set.of("https", "http", "git", "ssh")
                    .contains(scheme.toLowerCase(Locale.ROOT)))
                return new CandidateSource.NonGitHubHost(raw);
            if (uri.getPort() != -1 || uri.getQuery() != null) return new CandidateSource.Invalid();
            if (uri.getUserInfo() != null
                    && !(scheme.equalsIgnoreCase("ssh") && uri.getUserInfo().equals("git")))
                return new CandidateSource.Invalid();
            if (!host.equalsIgnoreCase("github.com")) return new CandidateSource.NonGitHubHost(raw);
            String path = uri.getRawPath();
            if (path == null || !path.startsWith("/") || path.contains("%"))
                return new CandidateSource.Invalid();
            String[] parts = path.substring(1).replaceFirst("/$", "").split("/", -1);
            if (parts.length != 2) return new CandidateSource.Invalid();
            String repo = parts[1].replaceFirst("\\.git$", "");
            if (!segment(parts[0]) || !segment(repo) || !safeDirectory(directory))
                return new CandidateSource.Invalid();
            return new CandidateSource.GitHubUrl(parts[0], repo, directory);
        } catch (RuntimeException e) {
            return new CandidateSource.Invalid();
        }
    }

    private static boolean segment(String s) {
        return s != null && !s.equals(".") && !s.equals("..") && s.matches("[A-Za-z0-9_.-]+");
    }

    static boolean safeDirectory(String directory) {
        if (directory == null) return true;
        if (directory.isBlank() || directory.startsWith("/") || directory.contains("\\"))
            return false;
        String value = directory;
        for (int pass = 0; pass < 3; pass++) {
            for (String s : value.split("/", -1))
                if (!segment(s) && !s.matches("@[A-Za-z0-9_.-]+")) return false;
            String decoded = URLDecoder.decode(value, StandardCharsets.UTF_8);
            if (decoded.equals(value)) return true;
            value = decoded;
        }
        return false;
    }
}
