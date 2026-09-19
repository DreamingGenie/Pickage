"""RAG 비교 API — 130(백엔드)이 호출하는 HTTP 엔드포인트 (S15P21A506-178).

컨테이너가 상시 대기하는 서버로 뜬다(일회성 배치가 아님 — 2026-09-18 결정,
ai/similarity의 배치 컨테이너와는 실행 방식이 다르다).
"""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai.rag.pipeline import VerificationFailedError, compare_packages
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
    }


def create_app(compare_fn: Callable[..., ComparisonResult] = compare_packages) -> FastAPI:
    """compare_fn을 주입 가능하게 둬서, 175~180 실구현 없이도 라우팅·직렬화만 테스트한다."""
    app = FastAPI()

    @app.post("/compare")
    def compare(req: CompareRequest) -> dict:
        packages = [PackageRef(name=p.package, version=p.version) for p in req.packages]
        try:
            result = compare_fn(packages)
        except VerificationFailedError as exc:
            raise HTTPException(status_code=502, detail={"violations": exc.violations}) from exc
        return _serialize(result)

    return app


app = create_app()
