"""로컬 개발용 README 인계 파일 생성기 (S15P21A506-419).

운영 노드의 `/srv/pickage/docs` 는 데이터팀이 채운 것이라 로컬에서는 rag 파이프라인을
돌릴 수 없다. 이 스크립트는 npm 배포 tarball 로 **같은 서식의 인계 파일**을 만든다.

서식과 판정 규칙은 백엔드 `DocAssembler.java` / `DocFetcher.java`(393 브랜치)를 그대로
옮긴 것이다 — 그쪽 주석대로 "파이썬 프리로드와 글자 하나까지 같아야" 하는 서식이라,
여기서 임의로 고치면 로컬 결과가 운영과 달라진다. 옮길 때 지킨 것:

  1. 진입점: exports 키 중 "." 로 시작하고 `*` 가 없고 `./package.json` 이 아닌 것,
     자연 정렬, 최대 30개. 각 항목에서 앞의 `./` 문자 집합을 벗긴다(그래서 "." 는 ""가 된다).
  2. 소비 형태 판정 순서: CSS → CLI(bin) → LIB(진입점 3개 이상) → TYPES(.d.ts) → BARE.
  3. 문헌 상태: 산문 1,000자 이상 OK / 진입점·bin·.d.ts 가 있으면 LIMITED /
     설명만 있으면 LIMITED / 그 밖 NONE.
  4. 본문은 32,768 바이트에서 자른다(글자가 아니라 바이트).

파일 목록은 jsDelivr 대신 tarball 안의 파일로 센다. 같은 배포본이라 같아야 하고,
실제로 운영 파일(js-yaml@5.4.1)과 파일 수·크기를 대조해 검증했다.

사용:
    python ai/rag/scripts/make_local_docs.py <출력 루트> yaml@2.9.0 js-yaml@5.4.1 ...
그 뒤 `README_SOURCE_ROOT=<출력 루트>` 로 파이프라인을 돌린다.

npm 이 필요하다. 받는 것은 공개 배포본의 텍스트뿐이고 아무것도 실행하지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.rag.readme_source import resolve_readme_path  # noqa: E402

MAX_README_BYTES = 32 * 1024
STUB_PROSE = 1000
MAX_SUBPATHS = 30
README_NAMES = ("readme.md", "readme.markdown", "readme", "readme.txt", "readme.rst")
DTS_SUFFIX = (".d.ts", ".d.mts", ".d.cts")

_KIND_LABEL = {
    "CSS": "스타일시트로 소비 (CSS import)",
    "CLI": "명령줄 도구",
    "LIB": "라이브러리 (진입점 다수)",
    "TYPES": "라이브러리 (타입 선언 제공)",
    "BARE": "라이브러리",
}

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_RULE = re.compile(r"^\s*[-=*_]{3,}\s*$", re.MULTILINE)
_HEADING = re.compile(r"^#+\s*", re.MULTILINE)
_SPACES = re.compile(r"\s+")


def prose(markdown: str) -> str:
    """산문만 남긴다. 글자 수를 세려고만 쓰고 문서에는 들어가지 않는다."""
    t = _FENCE.sub("", markdown)
    t = _TAG.sub("", t)
    t = _IMAGE.sub("", t)
    t = _LINK.sub(r"\1", t)
    t = _RULE.sub("", t)
    t = _HEADING.sub("", t)
    return _SPACES.sub(" ", t).strip()


def _truthy(value) -> bool:
    """파이썬 bool() 과 같은 판정 — @types 패키지의 빈 문자열 main 을 "없음"으로 본다."""
    return bool(value)


def _strings(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _has_style(node) -> bool:
    if isinstance(node, str):
        return node.lower().endswith((".css", ".scss", ".sass", ".less"))
    if isinstance(node, dict):
        return any(_has_style(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_style(v) for v in node)
    return False


def _subpaths(exports) -> list[str]:
    if not isinstance(exports, dict):
        return []
    keys = [k for k in exports if k.startswith(".") and "*" not in k and k != "./package.json"]
    return sorted(keys)


def _bin(node, name: str) -> list[str]:
    if isinstance(node, str):
        return [name.split("/")[-1]]
    if isinstance(node, dict):
        return sorted(node)
    return []


def _keywords(node) -> list[str]:
    if isinstance(node, str):
        return [s.strip() for s in node.split(",") if s.strip()]
    if isinstance(node, list):
        return _strings(node)[:40]
    return []


def _license(node) -> str | None:
    if isinstance(node, str) and node.strip():
        return node.strip()[:100]
    if isinstance(node, dict) and isinstance(node.get("type"), str):
        return node["type"][:100]
    return None


def _lstrip_dot_slash(s: str) -> str:
    return re.sub(r"^[./]+", "", s)


def _entry_kind(manifest: dict, dts: list[str], files_field: list[str], style_in_exports: bool) -> str:
    css = manifest["style"] is not None or style_in_exports
    if not css:
        css = any(f.endswith((".css", ".scss")) for f in files_field)
    if css:
        return "CSS"
    if manifest["bin"]:
        return "CLI"
    if manifest["subpath_count"] >= 3:
        return "LIB"
    if dts:
        return "TYPES"
    return "BARE"


def _doc_status(prose_chars: int, manifest: dict, dts: list[str]) -> str:
    if prose_chars >= STUB_PROSE:
        return "OK"
    if manifest["subpath_count"] >= 3 or manifest["bin"] or dts:
        return "LIMITED"
    if manifest["description"]:
        return "LIMITED"
    return "NONE"


def assemble(name: str, version: str, pkg: dict, count: int, unpacked: int, dts: list[str],
             body: str, kind: str, status: str, readme_bytes: int, prose_chars: int) -> str:
    """DocAssembler.assemble 과 같은 고정 서식."""
    manifest = _manifest(pkg, name)
    out: list[str] = []
    line = out.append

    line(f"# {name}@{version}")
    line("")
    line(manifest["description"] or "(설명 없음)")
    line("")
    line("## 소비 형태 · 진입점")
    line("")
    line(f"- 형태: {_KIND_LABEL.get(kind, kind)}")
    line(f"- 명령: {', '.join(manifest['bin']) if manifest['bin'] else '없음'}")
    line(f"- 스타일 진입점: {manifest['style'] or '없음'}")
    if manifest["subpaths"]:
        shown = len(manifest["subpaths"])
        extra = "" if manifest["subpath_count"] <= shown else f" 외 {manifest['subpath_count'] - shown}개"
        line(f"- 진입점 {manifest['subpath_count']}개: {', '.join(manifest['subpaths'])}{extra}")
    else:
        line("- 진입점: exports 선언 없음 (단일 진입점)")
    line(
        f"- 모듈 형식: type={manifest['type'] if manifest['type'] else 'commonjs (기본값)'}, "
        f"main {'있음' if manifest['main'] else '없음'}"
    )
    line("- 타입 선언: " + ("없음 (@types 별도 필요)" if not dts else "포함 — " + ", ".join(dts[:5])))
    line(f"- 키워드: {', '.join(manifest['keywords']) if manifest['keywords'] else '없음'}")
    line("")
    line("## 설치 조건")
    line("")
    line(f"- 설치 크기: {unpacked:,} B")
    line(f"- 파일 수: {count}")
    line(f"- 직접 의존성: {manifest['dependencies']}개")
    line(f"- 라이선스: {manifest['license'] if manifest['license'] else '미표기'}")
    line("")
    line("## README 전문")
    line("")
    line(body.strip() if body.strip() else "(README 없음)")
    line("")
    line("---")
    return "\n".join(out) + "\n" + (
        f"근거: S1 README {readme_bytes:,} B / 산문 {prose_chars:,}자 · S2 manifest · S3 spec · 상태 {status}"
    )


def _manifest(pkg: dict, name: str) -> dict:
    subs = _subpaths(pkg.get("exports"))
    deps = pkg.get("dependencies")
    return {
        "description": (pkg.get("description") or "").strip() if isinstance(pkg.get("description"), str) else "",
        "keywords": _keywords(pkg.get("keywords")),
        "license": _license(pkg.get("license")),
        "type": pkg["type"] if isinstance(pkg.get("type"), str) else None,
        "main": _truthy(pkg.get("main")),
        "style": pkg["style"] if isinstance(pkg.get("style"), str) else None,
        "bin": _bin(pkg.get("bin"), name),
        "subpath_count": len(subs),
        "subpaths": [_lstrip_dot_slash(s) for s in subs[:MAX_SUBPATHS]],
        "dependencies": len(deps) if isinstance(deps, dict) else 0,
    }


def build_document(name: str, version: str, tgz: Path) -> str:
    count = 0
    unpacked = 0
    readme_path: str | None = None
    dts: list[str] = []
    pkg: dict = {}
    body_raw = b""

    with tarfile.open(tgz) as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        for m in members:
            path = m.name.split("/", 1)[1] if "/" in m.name else m.name
            count += 1
            unpacked += m.size
            lower = path.lower()
            if readme_path is None and "/" not in path and lower in README_NAMES:
                readme_path = path
            if lower.endswith(DTS_SUFFIX):
                dts.append(path)
        dts.sort()
        dts = dts[:20]
        for m in members:
            path = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if path == "package.json":
                pkg = json.loads(tar.extractfile(m).read().decode("utf-8"))
            if readme_path and path == readme_path:
                body_raw = tar.extractfile(m).read()

    body = body_raw[:MAX_README_BYTES].decode("utf-8", errors="replace")
    manifest = _manifest(pkg, name)
    kind = _entry_kind(manifest, dts, _strings(pkg.get("files")), _has_style(pkg.get("exports")))
    prose_chars = len(prose(body))
    status = _doc_status(prose_chars, manifest, dts)
    readme_bytes = len(body.encode("utf-8"))
    return assemble(name, version, pkg, count, unpacked, dts, body, kind, status, readme_bytes, prose_chars)


def _split_spec(spec: str) -> tuple[str, str]:
    name, sep, version = spec.rpartition("@")
    if not sep or not name:
        raise SystemExit(f"'패키지@버전' 형식이어야 합니다: {spec!r}")
    return name, version


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    root = Path(argv[1])
    # Windows 에서 확장자 없는 `npm` 은 셸 스크립트라 CreateProcess 가 실행하지 못한다.
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm 을 찾을 수 없습니다.")
    with tempfile.TemporaryDirectory() as tmp:
        for spec in argv[2:]:
            name, version = _split_spec(spec)
            result = subprocess.run(
                [npm, "pack", f"{name}@{version}", "--pack-destination", tmp, "--silent"],
                capture_output=True, text=True, encoding="utf-8",
            )
            if result.returncode != 0:
                print(f"[건너뜀] {spec}: npm pack 실패 — {result.stderr.strip()[:120]}")
                continue
            tgz = Path(tmp) / result.stdout.strip().splitlines()[-1]
            doc = build_document(name, version, tgz)
            path = resolve_readme_path(name, version, root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(doc, encoding="utf-8")
            status = re.search(r"상태 (\w+)$", doc).group(1)
            print(f"[만듦] {spec} → {path}  ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
