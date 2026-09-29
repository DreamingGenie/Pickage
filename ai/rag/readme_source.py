"""데이터팀이 넘겨준 README 인계 파일 경로 해석 + 읽기 (S15P21A506-176).

배치 규칙 (2026-09-18, 데이터팀 전달 — app 노드 `/srv/pickage/docs` 실물 기준):

    <루트>/{shard}/{key}.md
    key   = {name에서 '/' -> '__' 치환}@{version}
    shard = name에서 맨 앞 '@' 뗀 뒤 첫 글자를 소문자로. 비면 '_'.

    이름 자체는 원문 그대로 보존한다 — 대문자 든 패키지 71건이 있고 리눅스는
    대소문자를 가리므로 소문자화하지 않는다(샤드 글자 하나만 예외).
    스코프 패키지가 전체의 54%라 '/' -> '__' 치환을 빠뜨리면 절반이 안 열린다.
"""

from __future__ import annotations

from pathlib import Path

from ai.rag.readme_chunker import parse_data_team_envelope
from ai.rag.types import DataTeamEnvelope


class InvalidPackageRefError(ValueError):
    """package·version 이 파일 경로로 쓰기에 안전하지 않을 때 (S15P21A506-484).

    이 두 값은 /compare 요청에서 그대로 오므로, 그대로 경로에 붙이면 `../` 로 루트 밖 파일을
    가리킬 수 있다. `field` 는 어느 값이 문제인지(응답 코드용)이고, 입력값 자체는 응답에 싣지 않는다.
    """

    def __init__(self, field: str, value: str) -> None:
        super().__init__(f"{field} 값이 안전하지 않음: {value!r}")
        self.field = field


def _validate_ref(package: str, version: str) -> None:
    """경로 구분자·`..`·NUL·빈 값을 거부한다. 스코프 이름(`@scope/name`)의 `/` 는 하나만 허용한다."""
    for field, value in (("package", package), ("version", version)):
        if not value or "\\" in value or "\x00" in value or ".." in value:
            raise InvalidPackageRefError(field, value)
    if package.startswith("@"):
        scope, sep, name = package[1:].partition("/")
        if not (scope and sep and name and "/" not in name):
            raise InvalidPackageRefError("package", package)
    elif "/" in package:
        raise InvalidPackageRefError("package", package)
    if "/" in version:
        raise InvalidPackageRefError("version", version)


def resolve_readme_path(package: str, version: str, root: str | Path) -> Path:
    """(package, version)이 저장돼 있을 README 인계 파일 경로를 계산한다(파일 존재 여부는 확인 안 함).

    Raises:
        InvalidPackageRefError: package·version 이 루트 밖을 가리킬 수 있는 값일 때.
    """
    _validate_ref(package, version)
    unscoped = package[1:] if package.startswith("@") else package
    shard = unscoped[0].lower()
    key = package.replace("/", "__") + "@" + version
    path = Path(root) / shard / f"{key}.md"
    # 위 검사를 놓친 경우를 대비한 마지막 방어선 — 계산한 경로가 루트 아래인지 다시 확인한다.
    if Path(root).resolve() not in path.resolve().parents:
        raise InvalidPackageRefError("package", package)
    return path


class ReadmeSourceNotFoundError(Exception):
    """이 (package, version)의 README 인계 파일이 해당 경로에 없을 때.

    TODO: "청킹 실패"와 구분되는 "재수집 필요" 상태로 호출자에게 알려야 한다는
    pipeline.py의 옛 TODO가 아직 남아 있음 — 지금은 이 예외 하나로만 구분한다.

    package·version(S15P21A506-419)은 API 가 "어느 패키지의 자료가 없는지"를 404 로 알리는 데
    쓴다. `path` 는 서버 내부 경로라 응답에 싣지 않는다.
    """

    def __init__(self, path: str, package: str | None = None, version: str | None = None) -> None:
        super().__init__(path)
        self.path = path
        self.package = package
        self.version = version


def read_readme_envelope(package: str, version: str, root: str | Path) -> DataTeamEnvelope:
    """README 인계 파일을 읽어 0단계 분리(DataTeamEnvelope)까지 마친다."""
    path = resolve_readme_path(package, version, root)
    try:
        doc_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReadmeSourceNotFoundError(str(path), package=package, version=version) from exc
    return parse_data_team_envelope(doc_text)
