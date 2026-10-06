"""RAG 비교 API — 130(백엔드)이 호출하는 HTTP 엔드포인트 (S15P21A506-178).

컨테이너가 상시 대기하는 서버로 뜬다(일회성 배치가 아님 — 2026-09-18 결정,
ai/similarity의 배치 컨테이너와는 실행 방식이 다르다).
"""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from ai.rag.generation import GmsCallError, GmsTimeoutError
from ai.rag.pipeline import VerificationFailedError, compare_packages
from ai.rag.readme_source import InvalidPackageRefError, ReadmeSourceNotFoundError
from ai.rag.types import ComparisonResult, PackageRef


class PackageRefIn(BaseModel):
    package: str
    version: str


# 백엔드 PackageRefs.MAX(=3) 와 같은 값이다 — 백엔드가 통과시킨 요청을 여기서 거부하지 않는다.
MAX_COMPARE_PACKAGES = 3


class CompareRequest(BaseModel):
    """비교 요청. 개수·중복 검증은 LLM 호출 전에 끝낸다(위반 시 FastAPI 가 422)."""

    packages: list[PackageRefIn] = Field(min_length=1, max_length=MAX_COMPARE_PACKAGES)

    @field_validator("packages")
    @classmethod
    def _no_duplicate_names(cls, packages: list[PackageRefIn]) -> list[PackageRefIn]:
        names = [p.package for p in packages]
        if len(set(names)) != len(names):
            raise ValueError("같은 패키지를 두 번 비교할 수 없음")
        return packages


def _serialize(result: ComparisonResult) -> dict:
    return {
        "dataStatus": result.data_status,
        "packages": [{"package": p.name, "version": p.version} for p in result.packages],
        "common": result.common,
        "differences": [
            {
                "package": d.package,
                "version": d.version,
                "body": d.body,
                # 핵심 문장 1개·핵심어 최대 3개의 강조 구간(S15P21A506-470). 프런트 `TextMark` 와
                # 같은 모양([start,end) UTF-16, kind).
                "marks": [{"start": m.start, "end": m.end, "kind": m.kind} for m in d.marks],
            }
            for d in result.differences
        ],
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
        except InvalidPackageRefError as exc:
            # 경로로 쓸 수 없는 값 — 입력 오류다. 어느 필드인지만 알리고 값은 되돌려주지 않는다.
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PACKAGE_REF", "field": exc.field},
            ) from exc
        except ReadmeSourceNotFoundError as exc:
            # 인계 파일이 없다 — 서버 오류가 아니라 "이 버전의 자료가 아직 없음"이다(스냅샷은
            # 특정 시점까지만 채워져 있다). 서버 내부 경로는 응답에 싣지 않는다.
            raise HTTPException(
                status_code=404,
                detail={"code": "DOC_NOT_FOUND", "package": exc.package, "version": exc.version},
            ) from exc
        except GmsTimeoutError as exc:
            # 내부 메시지(본문·키 가능성)는 싣지 않는다 — 코드만 알린다.
            raise HTTPException(status_code=504, detail={"code": "GMS_TIMEOUT"}) from exc
        except GmsCallError as exc:
            # 502 는 백엔드(RagClient)가 "검증 실패"로만 읽는 값이라 쓰지 않는다 — GMS 장애는 503 이다.
            raise HTTPException(status_code=503, detail={"code": "GMS_ERROR"}) from exc
        except VerificationFailedError as exc:
            raise HTTPException(status_code=502, detail={"violations": exc.violations}) from exc
        return _serialize(result)

    return app


app = create_app()
