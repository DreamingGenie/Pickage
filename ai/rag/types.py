"""Pickage 기능 비교 RAG 공용 데이터 구조 (S15P21A506-112 계열).

EvidenceChunk 필드는 docs/Pickage_기능별_개발_구상안_0917.md §7.1의
EvidenceRecord와 1:1 대응한다. 설계 근거는 readme-valiant-feather 계획 문서 참고.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 175가 실제로 생성하는 값의 부분집합 (전체 enum은 §7.4 참고)
SourceType = Literal["TARBALL_README"]
VerificationLevel = Literal["DISTRIBUTED_ARTIFACT", "SUPPLEMENTARY"]

GroundedIn = Literal["EVIDENCE", "GENERAL_KNOWLEDGE"]
Verdict = Literal[
    "SUPPORTED",
    "CONDITIONALLY_SUPPORTED",
    "LIMITED_SUPPORT",
    "UNCONFIRMED",
    "UNSUPPORTED",
]
DataStatus = Literal["COMPLETE", "COMPARISON_LIMITED"]


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
class FeatureResult:
    """features[].results[] 한 셀 — 패키지 하나에 대한 판정."""

    package: str
    verdict: Verdict
    evidence_ids: list[str] = field(default_factory=list)
    grounded_in: GroundedIn = "EVIDENCE"
    note: str = ""


@dataclass
class FeatureRow:
    """표의 행 하나 (비교 축 하나)."""

    feature_label: str
    results: list[FeatureResult] = field(default_factory=list)


@dataclass
class NarrativeSection:
    """"기능 비교 해설" 문단 하나."""

    heading: str
    body: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """178(generate)의 출력. `ai/기능비교 프론트화면.png` 시안 구조 그대로."""

    data_status: DataStatus
    packages: list[PackageRef]
    features: list[FeatureRow]
    narrative: list[NarrativeSection] = field(default_factory=list)
    narrative_error: str | None = None
