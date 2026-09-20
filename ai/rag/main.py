"""RAG 비교 API — 130(백엔드)이 호출하는 HTTP 엔드포인트 (S15P21A506-178).

컨테이너가 상시 대기하는 서버로 뜬다(일회성 배치가 아님 — 2026-09-18 결정,
ai/similarity의 배치 컨테이너와는 실행 방식이 다르다).
"""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai.rag.pipeline import VerificationFailedError, compare_packages
from ai.rag.readme_source import ReadmeSourceNotFoundError
from ai.rag.types import ComparisonResult, PackageRef


class PackageRefIn(BaseModel):
    package: str
    version: str


class CompareRequest(BaseModel):
    packages: list[PackageRefIn]


def _serialize(result: ComparisonResult) -> dict:
    return {
        "dataStatus": result.data_status,
        "packages": [{"package": p.name, "version": p.version} for p in result.packages],
        "features": [
            {
                "featureLabel": row.feature_label,
                "results": [
                    {
                        "package": r.package,
                        "version": r.version,
                        "verdict": r.verdict,
                        "evidenceIds": r.evidence_ids,
                        "groundedIn": r.grounded_in,
                        "note": r.note,
                    }
                    for r in row.results
                ],
            }
            for row in result.features
        ],
        "narrative": [
            {"heading": n.heading, "body": n.body, "evidenceIds": n.evidence_ids}
            for n in result.narrative
        ],
        "narrativeError": result.narrative_error,
        # 패키지별 인계 파일 상태(S15P21A506-419). 못 읽은 값은 null — "모름"과 "OK"를 구분한다.
        # dataStatus(비교 가능 여부)와는 다른 축이라 섞지 않는다.
        "sources": [
            {
                "package": s.package,
                "version": s.version,
                "status": s.status,
                "readmeBytes": s.readme_bytes,
                "proseChars": s.prose_chars,
            }
            for s in result.sources
        ],
    }


def create_app(compare_fn: Callable[..., ComparisonResult] = compare_packages) -> FastAPI:
    """compare_fn을 주입 가능하게 둬서, 175~180 실구현 없이도 라우팅·직렬화만 테스트한다."""
    app = FastAPI()

    @app.post("/compare")
    def compare(req: CompareRequest) -> dict:
        packages = [PackageRef(name=p.package, version=p.version) for p in req.packages]
        try:
            result = compare_fn(packages)
        except ReadmeSourceNotFoundError as exc:
            # 인계 파일이 없다 — 서버 오류가 아니라 "이 버전의 자료가 아직 없음"이다(스냅샷은
            # 특정 시점까지만 채워져 있다). 서버 내부 경로는 응답에 싣지 않는다.
            raise HTTPException(
                status_code=404,
                detail={"code": "DOC_NOT_FOUND", "package": exc.package, "version": exc.version},
            ) from exc
        except VerificationFailedError as exc:
            raise HTTPException(status_code=502, detail={"violations": exc.violations}) from exc
        return _serialize(result)

    return app


app = create_app()
