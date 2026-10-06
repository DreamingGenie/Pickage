"""Pickage 기능 비교 RAG 공용 데이터 구조 (S15P21A506-112 계열).

EvidenceChunk는 0917 보관 설계의 EvidenceRecord에서 시작한 내부 검색 단위다. 0923 현재 UI는
Evidence Drawer나 근거 ID 인용을 제공하지 않는다. 현재 계약은 docs/Pickage_기능별_개발_구상안_0923.md
§6을 참고한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 175가 실제로 생성하는 값의 부분집합 (전체 enum은 §7.4 참고)
#
# TARBALL_PACKAGE_JSON(S15P21A506-420): 인계 파일 헤더(소비 형태·진입점, 설치 조건, 설명)에서 뽑은
# 패키지 메타데이터 근거. package.json 과 배포 파일 목록에서 기계적으로 만든 값이다.
SourceType = Literal["TARBALL_README", "TARBALL_PACKAGE_JSON"]
VerificationLevel = Literal["DISTRIBUTED_ARTIFACT", "SUPPLEMENTARY"]

DataStatus = Literal["COMPLETE", "COMPARISON_LIMITED"]
# 인계 파일 꼬리의 `상태 …`(백엔드 DocAssembler 판정). README 산문 1,000자 이상이면 OK,
# 짧지만 진입점·bin·.d.ts 등이 있으면 LIMITED, 그 밖 NONE. dataStatus 와 다른 축이다.
SourceStatus = Literal["OK", "LIMITED", "NONE"]


@dataclass
class PackageRef:
    """비교 대상 패키지 하나 (정확한 버전 고정)."""

    name: str
    version: str


@dataclass
class DataTeamEnvelope:
    """데이터팀 인계 파일(`{package}@{version}.md`)을 0단계에서 분리한 결과.

    - structured_facts: `소비 형태·진입점`, `설치 조건` 섹션의 key-value (청킹 대상 아님)
    - readme_body: `README 전문` 아래 원본 마크다운 (chunk_readme()의 입력)
    - source_footer: 꼬리의 `근거: S1 ... 상태 OK` 줄 (SourceSnapshot류 출처 메타데이터)
    """

    package: str
    version: str
    structured_facts: dict[str, str]
    readme_body: str
    source_footer: str
    # 제목 아래 한 줄 설명. 인계 파일이 자리표시 `(설명 없음)`을 쓰면 빈 문자열이다.
    description: str = ""


@dataclass
class EvidenceChunk:
    """175(chunk_readme)의 출력 단위.

    2026-09-18 결정으로 DB 영속화는 폐기됨(요청마다 그때그때 청킹) —
    [[rag-176-no-db-cache]] 참고. snapshot_id는 이제 DB row가 아니라 원문 파일의
    sha256 해시(앞 16자)다 — 내용이 같으면 항상 같은 값이 나온다(pipeline.py의
    get_or_build_evidence 참고).
    """

    evidence_id: str
    snapshot_id: str
    package: str
    version: str
    section: str
    excerpt: str
    confirmed_content: str
    source_type: SourceType = "TARBALL_README"
    verification_level: VerificationLevel = "DISTRIBUTED_ARTIFACT"
    path: str = "README.md"


@dataclass
class PackageSource:
    """비교 대상 한 패키지의 인계 파일 상태 — 꼬리 `근거: … 상태 …` 줄에서 읽는다 (S15P21A506-419).

    못 읽은 값은 None 이다. 추측해서 채우지 않는다 — 소비하는 쪽이 "모름"과 "OK"를 구분해야 한다.
    """

    package: str
    version: str
    status: SourceStatus | None = None
    readme_bytes: int | None = None
    prose_chars: int | None = None


MarkKind = Literal["KEY_TERM", "KEY_SENTENCE"]


@dataclass
class Mark:
    """`body` 안의 강조 구간(S15P21A506-470). 위치는 UTF-16 코드 단위 오프셋 `[start, end)` 라 JS 문자열과
    같은 단위다 — 프런트 `TextMark`(백엔드 커뮤니티 `SummaryMarkPayload`)와 같은 계약이다. `KEY_TERM` 은
    핵심어(굵게), `KEY_SENTENCE` 는 핵심 문장(형광펜)이다. 강조는 읽기 보조일 뿐이라 없어도 문단 자체에는
    영향이 없다.
    """

    start: int
    end: int
    kind: MarkKind


@dataclass
class PackageNote:
    """차이점 문단 하나 — 그 패키지만의 특징을 서술한다 (2026-09-22, 표 대신 서술형으로 전환)."""

    package: str
    version: str
    body: str
    # 핵심 문장 1개·핵심어 최대 3개의 강조 구간(S15P21A506-470). `generate()`가 모델이 준 문자열을
    # `body` 안에서 찾아 계산한다 — 없거나 어긋나면 빈 목록이다.
    marks: list[Mark] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """178(generate)의 출력 — 공통점 서술 + 패키지별 차이점 서술.

    2026-09-22 결정으로 기능별 판정표(features)·해설(narrative)·근거 ID 인용을 없앴다. 화면이
    표 대신 글 두 덩어리(공통점 / 패키지별 차이점)만 보여주기 때문이다.
    """

    data_status: DataStatus
    packages: list[PackageRef]
    common: str
    differences: list[PackageNote] = field(default_factory=list)
    # 패키지별 인계 파일 상태. LLM 이 만드는 값이 아니라 pipeline 이 파일에서 읽어 붙인다.
    sources: list[PackageSource] = field(default_factory=list)
