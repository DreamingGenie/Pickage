"""Pickage 기능 비교 RAG 공용 데이터 구조 (S15P21A506-112 계열).

EvidenceChunk 필드는 docs/Pickage_기능별_개발_구상안_0917.md §7.1의
EvidenceRecord와 1:1 대응한다. 설계 근거는 readme-valiant-feather 계획 문서 참고.
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

GroundedIn = Literal["EVIDENCE", "GENERAL_KNOWLEDGE"]
Verdict = Literal[
    "SUPPORTED",
    "CONDITIONALLY_SUPPORTED",
    "LIMITED_SUPPORT",
    "UNCONFIRMED",
    "UNSUPPORTED",
]
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
class FeatureResult:
    """features[].results[] 한 셀 — 패키지 하나에 대한 판정.

    version(2026-09-18 추가): 176이 DB 없이 그때그때 청킹하는 방식으로 바뀌면서,
    179(근거ID·패키지·버전 검증)가 다른 곳(ComparisonResult.packages)을 다시 조회하지
    않고 셀 하나만 보고 검증할 수 있도록 셀 안에 버전을 직접 싣는다.
    """

    package: str
    version: str
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
class PackageSource:
    """비교 대상 한 패키지의 인계 파일 상태 — 꼬리 `근거: … 상태 …` 줄에서 읽는다 (S15P21A506-419).

    못 읽은 값은 None 이다. 추측해서 채우지 않는다 — 소비하는 쪽이 "모름"과 "OK"를 구분해야 한다.
    """

    package: str
    version: str
    status: SourceStatus | None = None
    readme_bytes: int | None = None
    prose_chars: int | None = None


@dataclass
class ComparisonResult:
    """178(generate)의 출력. `ai/기능비교 프론트화면.png` 시안 구조 그대로."""

    data_status: DataStatus
    packages: list[PackageRef]
    features: list[FeatureRow]
    narrative: list[NarrativeSection] = field(default_factory=list)
    narrative_error: str | None = None
    # 패키지별 인계 파일 상태. LLM 이 만드는 값이 아니라 pipeline 이 파일에서 읽어 붙인다.
    sources: list[PackageSource] = field(default_factory=list)
