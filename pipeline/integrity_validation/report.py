"""Reviewable reports and deferred PostgreSQL checks; no database execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import TABLES


def markdown(report: dict) -> str:
    lines = ["# 9번 합성 데이터 검증 결과", "",
             f"- 검증 결과: **{report['validation_status']}**",
             f"- 입력: `{report['fixture_id']}`",
             f"- 검사 범위: `{report['scope']}`",
             "- 실행: DuckDB 메모리, 1 thread / 128 MB; PostgreSQL·네트워크 접속 없음",
             "- 운영 게시 승인: **아니오** / 9번 전체 완료: **아니오**", "",
             "정답 fixture와 SQL의 의미를 검사한 결과다. 실제 원천 manifest, 전체 DB의 정합성,",
             "PostgreSQL 구문·실행계획·성능 또는 장애 복구 성공 증거로 사용하지 않는다.", "",
             "## 입력과 검사 코드", ""]
    for key in ("fixture_file_sha256", "fixture_content_sha256", "validator_sha256"):
        if key in report:
            lines.append(f"- {key}: `{report[key]}`")
    lines += ["", "## 검사 결과", "", "| 검사 | 결과 | 위반 수 |", "| --- | --- | ---: |"]
    for check in report["checks"]:
        description = check["description"].replace("|", "\\|").replace("\n", " ")
        count = "—" if check["violations"] is None else str(check["violations"])
        lines.append(f"| `{check['id']}` · {description} | {check['status']} | {count} |")
    lines += ["", "## 원천 품질", "", "PARTIAL은 그대로 표시한다. 성공한 직접 관계 기준 0은 전체 해석 성공을 뜻하지 않는다.", ""]
    for quality in report["quality"]:
        lines.append(f"- {quality['snapshot_at']}: 계산 `{quality['calculation_status']}`, "
                     f"해석 `{quality['resolution_status']}`, 미해석 {quality['unresolved_count']}개")
    lines += ["", "## 후속 실행 — 모두 NOT_RUN", ""]
    lines += [f"- `{check['id']}`" for check in report["deferred_checks"]]
    return "\n".join(lines) + "\n"


def integrity_sql() -> str:
    from .queries import CHECKS

    lines = ["-- 9번 PostgreSQL 검증 준비용 SQL. 이번 단계에서 PostgreSQL 실행은 하지 않았다.",
             "-- public 서비스 데이터와 승인된 동일 범위의 validation.* 근거 테이블/뷰가 필요하다.",
             "-- fixture 값을 운영 근거로 적재하지 않는다. 이 파일은 근거를 생성하지 않는다.",
             "-- 오류 발생 시 모든 나머지 검사는 미실행이다. psql 사용 시 ON_ERROR_STOP을 유지한다.",
             "-- 대량 전체 스캔이므로 현재 성능 실험 중에는 실행하지 않는다.",
             "-- 공통 SELECT 의미 검증만 완료; PK/FK 선언·정확한 타입은 별도 catalog SQL과 비교한다.",
             "\\set ON_ERROR_STOP on", "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;",
             "SET LOCAL statement_timeout = '30s';", "SET LOCAL lock_timeout = '2s';", ""]
    for check in CHECKS:
        # IDs and SQL are repository-owned, never taken from fixture input.
        lines += ["-- " + check["description"],
                  "SELECT '" + check["id"] + "' AS check_id, violations FROM (",
                  "  SELECT (" + check["sql"].strip().removesuffix(";") + ") AS violations",
                  ") result;", ""]
    lines.append("ROLLBACK;")
    return "\n".join(lines) + "\n"


def evidence_contract() -> str:
    lines = ["# PostgreSQL 검증 SQL의 근거 입력", "",
             "아래는 검증용 테이블/뷰의 열 계약이다. 서비스 DDL 변경안이 아니다.",
             "전체 DB 실행 전에 승인된 원천 run과 같은 snapshot·모집단의 근거를 별도 검증 환경에 준비한다.",
             "합성 fixture 값으로 실제 데이터 정답이나 승인 manifest를 대체하지 않는다.", ""]
    for name, columns in TABLES.items():
        if name.startswith("validation."):
            lines += [f"## `{name}`", "", "| 열 | 타입 |", "| --- | --- |"]
            lines += [f"| {column} | {kind} |" for column, kind in columns]
            lines.append("")
    lines += ["## 아직 필요한 연결", "",
              "- package/version: `pipeline.postgresql.input.select_run`와 파일/schema 검증을 통과한 명시적 run.",
              "- snapshot_context: 승인된 calendar의 UTC 원천 시각. DATE 자정이나 현재 시각으로 대체하지 않는다.",
              "- package_population: 각 snapshot의 승인된 전체 패키지 집합. 다운로드 선정 목록으로 축소하지 않는다.",
              "- target_population: 8번 D-22의 선정 패키지에 속한 해당 시각의 전체 유효 target 버전.",
              "- resolved_edges: 정규화된 일반 dependencies의 해석 성공 관계. source는 선정 목록으로 제한하지 않는다.",
              "- source_quality: 날짜별 계산/해석 상태. 이 fixture의 단순 품질 열은 운영 manifest 어댑터가 아니다.",
              "- expected_package_metrics: 별도 원천 대조로 승인한 값. 현재 DB 값을 복사해 정답으로 사용하지 않는다.",
              "- 행 수: 각 승인 manifest의 expected count와 같은 검증 범위의 실제 count를 별도로 연결한다.",
              "- schema fingerprint: V1~V4와 실제 catalog를 비교한다. 아래 catalog 결과 수집만으로 통과하지 않는다.",
              "", "실제 어댑터·전체 원천 검증·장애 복구·성능 실측은 후속 작업이다."]
    return "\n".join(lines) + "\n"


def validator_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for name in ("schema.py", "queries.py", "runner.py", "report.py", "__main__.py",
                 "schema_catalog.sql", "query_plans.sql"):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update((root / name).read_bytes())
    policy = root.parent / "preprocessing" / "snapshot" / "policy.py"
    digest.update(b"preprocessing/snapshot/policy.py\0" + policy.read_bytes())
    return digest.hexdigest()


def write_bundle(report: dict, output: Path) -> None:
    output = Path(output)
    # A fresh directory preserves previous reports on retries and concurrent runs.
    output.mkdir(parents=True, exist_ok=False)
    report["validator_sha256"] = validator_hash()
    files = {
        "report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        "report.md": markdown(report),
        "integrity_checks.sql": integrity_sql(),
        "evidence_contract.md": evidence_contract(),
        "schema_catalog.sql": (Path(__file__).parent / "schema_catalog.sql").read_text(encoding="utf-8"),
        "query_plans.sql": (Path(__file__).parent / "query_plans.sql").read_text(encoding="utf-8"),
    }
    for name, content in files.items():
        with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
