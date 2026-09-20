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


def resolve_readme_path(package: str, version: str, root: str | Path) -> Path:
    """(package, version)이 저장돼 있을 README 인계 파일 경로를 계산한다(파일 존재 여부는 확인 안 함)."""
    unscoped = package[1:] if package.startswith("@") else package
    shard = unscoped[0].lower() if unscoped else "_"
    key = package.replace("/", "__") + "@" + version
    return Path(root) / shard / f"{key}.md"


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
