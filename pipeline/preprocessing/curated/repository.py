"""Pure, conservative normalization of GitHub/GitLab repository references."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit


_HOSTS = {"github.com", "gitlab.com", "www.github.com", "www.gitlab.com"}
_CANONICAL_HOSTS = {"www.github.com": "github.com", "www.gitlab.com": "gitlab.com"}
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_UI_MARKERS = {"tree", "blob", "issues", "pull", "pulls", "commit", "commits", "actions"}


def _decode_path(path: str) -> str | None:
    """Decode a URL path while rejecting malformed/unsafe escapes."""
    if re.search(r"%(?![0-9a-fA-F]{2})", path) or re.search(r'%2f|%5c', path, re.I):
        return None
    decoded = unquote(path)
    if any(ord(char) < 32 or ord(char) == 127 for char in decoded):
        return None
    return decoded


def _split_reference(value: str) -> tuple[str, str] | None:
    """Return (host, path) for a supported URL or host shorthand."""
    value = value.strip()
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None

    # Friendly shorthand forms such as github:owner/repo.
    shorthand = re.match(r"^(github|gitlab):(.+)$", value, re.IGNORECASE)
    if shorthand:
        return shorthand.group(1).lower() + ".com", shorthand.group(2)

    # SCP-style references (git@github.com:owner/repo), plus the common
    # host:path shorthand. Only the transport user ``git`` is accepted.
    scp = re.match(r"^(?:(git)@)?([^/:?#]+):(.+)$", value, re.IGNORECASE)
    if scp and not _SCHEME_RE.match(value):
        user, host, path = scp.groups()
        if user and user.lower() != "git":
            return None
        if host.lower() not in _HOSTS:
            return None
        return host.lower(), path

    # Explicit host shorthand, e.g. github.com/owner/repo.
    if not _SCHEME_RE.match(value) and re.match(r"^(?:www\.)?(?:github|gitlab)\.com/", value, re.I):
        host, path = value.split("/", 1)
        return host.lower(), "/" + path

    if not _SCHEME_RE.match(value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https", "git", "git+http", "git+https", "ssh", "git+ssh"}:
            return None
        host = parsed.hostname
        # Accessing .port also validates malformed ports.
        port = parsed.port
    except ValueError:
        return None
    if not host or host.lower() not in _HOSTS or port is not None:
        return None
    if parsed.username is not None and parsed.username.lower() != "git":
        return None
    if parsed.password is not None:
        return None
    return host.lower(), parsed.path


def normalize_repository_url(value: str | None) -> str | None:
    """Normalize a repository reference to a public browser HTTPS URL.

    Only exact github.com and gitlab.com hosts are accepted. This function
    performs syntax normalization only; it never makes network requests.
    Invalid, ambiguous, unsafe, or overlong references return ``None``.
    """
    if value is None or not isinstance(value, str):
        return None
    split = _split_reference(value)
    if split is None:
        return None
    host, raw_path = split
    host = _CANONICAL_HOSTS.get(host, host)
    # Remove explicit URL query/fragment before decoding. Encoded delimiters
    # are rejected below so they cannot smuggle path content into this step.
    raw_path = raw_path.split("?", 1)[0].split("#", 1)[0].strip("/")
    path = _decode_path(raw_path)
    if path is None:
        return None
    if "?" in path or "#" in path:
        return None
    if not path or "\\" in path or any(char.isspace() for char in path):
        return None
    segments = path.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        return None
    if any(any(char in segment for char in '<>"|{}[]^') for segment in segments):
        return None

    if host == "github.com":
        if len(segments) < 2:
            return None
        # GitHub repository identity is unambiguous in the first owner/repo
        # pair. Recognized UI suffixes are discarded; arbitrary suffixes are
        # rejected instead of guessing whether they are part of a repo path.
        if len(segments) > 2:
            if segments[2].lower() not in _UI_MARKERS:
                return None
            segments = segments[:2]
    else:
        if len(segments) < 2:
            return None
        # GitLab namespaces may contain arbitrary subgroup depth. A /-/ UI
        # marker makes the repository boundary explicit; without it retain
        # the complete namespace/project path.
        if "-" in segments:
            marker = segments.index("-")
            if marker < 2:
                return None
            segments = segments[:marker]
        elif len(segments) > 2 and any(segment.lower() in _UI_MARKERS for segment in segments[1:]):
            return None

    if segments[-1].lower().endswith('.git'):
        segments[-1] = segments[-1][:-4]
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+', segment) or segment in ('.', '..')
           for segment in segments):
        return None
    result = f"https://{host}/{'/'.join(segments)}"
    if len(result) > 200:
        return None
    return result


__all__ = ["normalize_repository_url"]
