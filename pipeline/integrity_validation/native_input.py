"""python -m pipeline.integrity_validation.native_input --request ... --output ..."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import duckdb

from .local_bundle import LocalMetadataStore, read_bounded, strict_json
from .native_selection import select_metadata
from .native_samples import verify_samples


def _validator_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = ["integrity_validation/" + name + ".py" for name in
             ("native_input", "native_selection", "native_samples", "local_bundle", "runner")]
    paths += ["postgresql/input.py", 'postgresql/package_snapshot/load.py', 'preprocessing/package_snapshot/quality_schema.py',
              'preprocessing/curated/storage.py', 'preprocessing/snapshot/policy.py']
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode() + b"\0" + (root / path).read_bytes() + b"\0")
    return digest.hexdigest()


def inspect_bundle(request_path: Path) -> dict:
    request_path = Path(request_path).absolute()
    body = read_bounded(request_path)
    document = strict_json(body)
    if not isinstance(document, dict):
        raise ValueError("Native request must be a JSON object")
    store = LocalMetadataStore(request_path.parent, document.get("objects"))
    selected = select_metadata(document, store)
    samples = verify_samples(request_path.parent, document["samples"], selected)
    metadata = selected["metadata"]
    manifest = metadata["manifest"]
    return {
        "format_version": 1,
        "scope": "NATIVE_METADATA_AND_EXPLICIT_SMALL_FILES",
        "metadata_status": "MATCH",
        "ready_for_load": False,
        "ready_for_publication": False,
        "task_09_complete": False,
        "synthetic_demo": manifest.get("synthetic_demo") is True,
        "dataset": document["dataset"],
        "snapshot": metadata["snapshot"],
        "snapshot_timestamp": document["snapshot_timestamp"],
        "run_id": metadata["curated_run_id"],
        "manifest_sha256": metadata["manifest_sha256"],
        "expected_counts": document["expected_counts"],
        "producer_declared_status": manifest["status"],
        "producer_declared_contracts": selected["producer_contracts"],
        "producer_generation_contract_verified": False,
        "native_selector": selected["native_selector"],
        "request_file_sha256": hashlib.sha256(body).hexdigest(),
        "validator_sha256": _validator_hash(),
        "duckdb_version": duckdb.__version__,
        "metadata_reads": store.reads,
        "samples": samples,
        "deferred_checks": {check: "NOT_RUN" for check in (
            "independent_approval_of_request_pins_and_generation_contract",
            "all_native_file_hashes_and_upstream_lineage",
            "row_values_keys_references_and_quality_semantics",
            "snapshot_calendar_and_historical_dependents_adapters",
            "full_population_reconciliation_and_synthetic_validator_binding",
            "postgresql_integrity_loader_recovery_and_performance")},
    }


def markdown(report: dict) -> str:
    lines = ["# 명시적 native 입력 연결 검사", "",
             f"- 입력 형식: `{report['dataset']}` / run: `{report['run_id']}`",
             f"- snapshot: `{report['snapshot_timestamp']}`",
             f"- 메타데이터 대조: **{report['metadata_status']}**",
             f"- 작은 파일 대조: **{report['samples']['status']}**",
             f"- 검사 범위: `{report['scope']}`",
             f"- 합성 예제 표식: `{str(report['synthetic_demo']).lower()}`",
             "- DB 적재 승인·운영 게시 승인·9번 전체 완료: **모두 아니오**", "",
             "요청 파일의 pin·기대 건수와 기존 native 선택 함수의 결과를 대조했다. 요청 pin 자체의",
             "외부 승인은 확인하지 않았다. producer의 PASSED 표식은 원문 주장으로 보존하며,",
             "이번 검사가 실제 원천 전체의 생성·품질·정합성을 승인한 것은 아니다.", "",
             "## 실제 읽은 범위", "",
             f"- metadata {len(report['metadata_reads'])}개 / "
             f"{sum(item['bytes'] for item in report['metadata_reads']):,} bytes",
             f"- 선택한 Parquet {len(report['samples']['files'])}개 / "
             f"{report['samples']['bytes_read']:,} bytes / footer {report['samples']['rows']:,}행",
             "- 선택한 파일: 크기·SHA256·열 순서/타입·footer 행 수만 검사. 행 값 검사는 미실행.",
             "- 파일을 따로 잘라 만든 샘플은 원본 파일 SHA와 다르므로 거부한다.", "",
             "| 역할 | 검사 파일 / manifest 파일 | 검사 행 / manifest 행 |", "| --- | ---: | ---: |"]
    for role, coverage in report["samples"]["coverage"].items():
        lines.append(f"| {role} | {coverage['checked_files']} / {coverage['manifest_files']} | "
                     f"{coverage['checked_rows']} / {coverage['manifest_rows']} |")
    lines += ["", "## 근거 식별", "",
              f"- 요청 SHA: `{report['request_file_sha256']}`",
              f"- 원문 manifest SHA: `{report['manifest_sha256']}`",
              f"- 이번 검증 코드 SHA: `{report['validator_sha256']}`",
              "- producer contract 필드는 JSON 보고서에 원문 값으로 보존한다. 현재 코드 해시로 보충하지 않는다.",
              "", "## 후속 검증 — 모두 NOT_RUN", ""]
    lines += [f"- `{name}`" for name in report["deferred_checks"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="명시적으로 복사한 작은 native 입력 검사; 원격/DB 접속 없음")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Use a fresh output directory; previous reports are preserved")
        report = inspect_bundle(args.request)
        args.output.mkdir(parents=True, exist_ok=False)
        for name, content in (("report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                              ("report.md", markdown(report))):
            with (args.output / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
    except (ValueError, OSError, TypeError, duckdb.Error) as error:
        print(f"INPUT/OUTPUT ERROR: {error}", file=sys.stderr)
        return 2
    print(f"METADATA MATCH; SAMPLES {report['samples']['status']}: {args.output.resolve() / 'report.md'}")
    print("Publication approval: false; full native validation: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
