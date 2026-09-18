"""README → EvidenceChunk 청킹 (S15P21A506-175).

설계 근거: readme-valiant-feather 계획 문서.
무거운 의존성 없이 stdlib만으로 테스트 가능하게 유지한다
(ai/similarity/similarity_batch_pipeline.py의 지연 import 관례와 같은 이유).

175는 순수 함수다 — 같은 (package, version, README 원문, 분석 로직 버전) 입력이면
항상 같은 EvidenceChunk 목록을 반환한다. 언제/얼마나 자주 호출할지(캐시 관리)는
호출부(pipeline.py의 get_or_build_evidence)의 책임이지 이 모듈의 책임이 아니다.
"""

from __future__ import annotations

from ai.rag.types import DataTeamEnvelope, EvidenceChunk

# 잡음 필터링 deny-list — 시작점일 뿐, 127 실제 수집물로 튜닝 필요 (계획 문서 참고)
_NOISE_HEADINGS = {
    "license",
    "contributors",
    "sponsors",
    "backers",
    "changelog",
    "code of conduct",
    "authors",
}


class EnvelopeParseError(Exception):
    """데이터팀 인계 포맷(봉투)이 예상과 다를 때 명확히 실패시키기 위한 예외.

    앵커 텍스트(`## README 전문` 등)가 안 맞으면 조용히 잘못 파싱하지 않고 여기서 멈춘다.
    """


def parse_data_team_envelope(doc_text: str) -> DataTeamEnvelope:
    """0단계: `소비 형태·진입점`/`설치 조건`(구조화 데이터) / README 전문 / 꼬리 출처메타 3분리.

    파일 구조 (debug@4.4.3.md 실물 기준):
        # {package}@{version}
        {한 줄 설명}

        ## 소비 형태 · 진입점
        - ...

        ## 설치 조건
        - ...

        ## README 전문
        {원본 README 마크다운 전체}

        ---
        근거: S1 README ... 상태 OK

    Raises:
        EnvelopeParseError: `## README 전문` 헤딩을 찾을 수 없을 때.
    """
    raise NotImplementedError


def chunk_readme(
    readme_text: str,
    package: str,
    version: str,
    snapshot_id: str,
    max_chunk_chars: int = 1800,
) -> list[EvidenceChunk]:
    """1~3단계: README 전문 텍스트 → EvidenceChunk 목록.

    규칙 (계획 문서 "처리 파이프라인" 절 참고):
        - 헤딩(ATX `#`~`######`, Setext `===`/`---`) 아무 레벨이나 분리 기준. 레벨은
          section 경로 표기(`"A > B"`)에만 쓰고 분리 여부 판단엔 안 씀.
        - 문서 최상단 제목~첫 헤딩 사이는 `section: "(intro)"` 청크로 묶음 — 헤딩 없는
          짧은 README일수록 여기에 핵심 정보가 있는 경우가 많음.
        - 헤딩이 없거나 부족하면 문단(빈 줄) 분리 → 그래도 크면 겹침 있는 슬라이딩 윈도우.
        - 코드블록(```)·표는 절대 안에서 안 자름 (경계 보존).
        - 몸통이 빈 헤딩은 청크를 만들지 않고 드롭 (SUPPLEMENTARY 격하 대상과 다른 케이스).
        - _NOISE_HEADINGS 매칭 섹션은 삭제 대신 verificationLevel=SUPPLEMENTARY로 격하.
        - README의 지시문(install/build/postinstall 등)은 절대 실행하지 않음 — 텍스트로만 취급.

    Args:
        max_chunk_chars: 청크당 문자 상한(기본 1800 ≈ 450토큰). §8 "전체 문서를 무제한
            AI 입력으로 전달하지 않음" 기준. bge-small 512토큰 한도와는 독립적으로 잡은
            값 — 147이 검색/생성 임베딩 모델을 확정하면 재검토 필요.

    Returns:
        section/excerpt/verificationLevel이 채워진 EvidenceChunk 리스트.
        sourceType은 항상 "TARBALL_README".
    """
    raise NotImplementedError
