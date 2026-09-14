"""python -m pipeline.integrity_validation --output <fresh-directory>"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .report import write_bundle
from .runner import load_fixture, validate_fixture


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="9번 검증 사전 준비: 작은 합성 데이터만 검사하며 DB에 연결하지 않습니다.")
    parser.add_argument("--fixture", type=Path, default=Path(__file__).parent / "fixtures" / "normal.json")
    parser.add_argument("--output", type=Path, required=True, help="새 보고서 디렉터리; 기존 결과는 덮어쓰지 않음")
    args = parser.parse_args(argv)
    try:
        # Reject an existing destination before running checks.
        if args.output.exists():
            raise ValueError("Use a fresh output directory; previous reports are preserved")
        document, digest = load_fixture(args.fixture)
        result = validate_fixture(document)
        result["fixture_file_sha256"] = digest
        write_bundle(result, args.output)
    except (ValueError, OSError, TypeError) as error:
        print(f"INPUT/OUTPUT ERROR: {error}", file=sys.stderr)
        return 2
    print(f"{result['validation_status']}: {args.output.resolve() / 'report.md'}")
    print("Scope: SYNTHETIC_FIXTURE_ONLY; PostgreSQL NOT_RUN; publication approval: false")
    return 0 if result["validation_status"] == "PASS" else (2 if result["validation_status"] == "ERROR" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
