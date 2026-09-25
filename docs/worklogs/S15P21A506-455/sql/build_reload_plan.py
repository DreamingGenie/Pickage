"""날짜별 파티션 적재 계획(reload plan)을 만든다.

`historical_db_reload` 는 계획 파일을 손으로 주게 되어 있고 만들어 주는 함수가 없다.
이 스크립트가 그 자리를 메운다. 값은 전부 **읽어서** 채우며 손으로 옮겨 적지 않는다.

  - generation : historical_db_reload.contract() 가 돌려주는 코드 지문
  - db_identity: 대상 DB 에 직접 물어본 system_identifier 와 current_database
  - rows_by_date: 계산 회차의 날짜별 품질에서 읽은 target 버전 수
  - dates      : --date 로 준 날짜들. 전체 달력과 같으면 scope=FULL_CALENDAR,
                 일부면 SELECTED_DATES 다. 이 작업은 날짜 단위로 교체하므로 보통 후자다.

이 스크립트는 DuckDB 가 TIMESTAMPTZ 를 파이썬 값으로 바꿀 때 pytz 를 요구한다
(duckdb 1.5.5). 공유 venv 에는 없으므로 별도 경로를 PYTHONPATH 에 얹어 실행한다.
운영에서 적재기를 돌릴 환경에도 같은 요구가 있다.

사용 예 (로컬 리허설, 날짜 하나):

  python docs/worklogs/S15P21A506-455/sql/build_reload_plan.py \
      --run-dir data/vd455/h5b/run-20260923-v1/run \
      --run-manifest-sha256 <SHA> \
      --schema vd193_reload_455_20260922 \
      --container pickage-local-postgres-1 --user postgres --database pickage \
      --date 2026-08-31 \
      --minimum-disk-gib 20 \
      --output data/vd455/reload/rehearsal-01

운영에서는 --container 와 --database 만 바꾼다. 이 스크립트는 DB 를 **읽기만** 한다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from pipeline.version_dependents.historical_db_reload import contract
from pipeline.version_dependents.historical_db_source import FullSource
from pipeline.requirements_resolution.input import file_sha256


def db_identity(command: list[str]) -> dict:
    """대상 DB 의 클러스터 ID 와 DB 이름을 읽는다. 쓰기는 하지 않는다."""
    sql = ("SELECT system_identifier::text FROM pg_control_system(); "
           "SELECT current_database();")
    done = subprocess.run(command + ["-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
                          check=True, capture_output=True, text=True, timeout=60)
    values = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    if len(values) < 2:
        raise SystemExit("DB identity 를 읽지 못했습니다: " + done.stdout)
    return {"system_identifier": values[-2], "current_database": values[-1]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="계산 회차의 run 폴더")
    ap.add_argument("--run-manifest-sha256", required=True)
    ap.add_argument("--schema", required=True, help="vd193_reload_ 로 시작하는 스테이징 스키마")
    ap.add_argument("--container", required=True)
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--database", required=True)
    ap.add_argument("--date", action="append", dest="dates",
                    help="적재할 기준일. 반복 지정. 생략하면 달력 전체")
    ap.add_argument("--execution-prefix", default="vd455")
    ap.add_argument("--minimum-disk-gib", type=int, default=20)
    ap.add_argument("--output", required=True, help="job 폴더. 새 경로여야 한다")
    args = ap.parse_args()

    command = ["docker", "exec", "-i", args.container,
               "psql", "-U", args.user, "-d", args.database]

    run_dir = Path(args.run_dir).resolve()
    if file_sha256(run_dir / "run_manifest.json") != args.run_manifest_sha256:
        raise SystemExit("run manifest SHA 가 다릅니다")

    # FullSource 는 아직 없는 작업 폴더를 요구한다(있으면 "fresh" 가 아니라고 거부한다).
    # 그래서 임시 폴더 안의 하위 경로를 만들지 않은 채로 넘긴다. 계획을 만드는 동안만 쓰고 버린다.
    with tempfile.TemporaryDirectory(prefix="vd455-plan-") as scratch:
        source = FullSource(str(run_dir), args.run_manifest_sha256, Path(scratch) / "attempt")
        try:
            # source.calendar 는 {'snapshot_at': ..., 'snapshot_timestamp': ...} 의 목록이다.
            # 계획의 dates 는 날짜 문자열 목록이므로 coordinator 와 같은 방식으로 뽑는다.
            calendar = [row["snapshot_at"] for row in source.calendar]
            dates = sorted(args.dates) if args.dates else list(calendar)
            missing = [day for day in dates if day not in calendar]
            if missing:
                raise SystemExit("달력에 없는 날짜입니다: " + ", ".join(missing))
            rows_by_date = {day: source.quality[day]["target_versions"] for day in dates}
        finally:
            source.close()

    plan = {
        "schema": args.schema,
        "source_run_dir": str(run_dir),
        "source_run_manifest_sha256": args.run_manifest_sha256,
        "db_command": command,
        "db_identity": db_identity(command),
        "dates": dates,
        "expected_dates": len(dates),
        "rows_by_date": rows_by_date,
        "expected_rows": sum(rows_by_date.values()),
        "execution_prefix": args.execution_prefix,
        "generation": contract(),
        # 적재기가 받는 값은 FULL_CALENDAR 아니면 SELECTED_DATES 둘뿐이다.
        # (오류 문구에는 "Pilot dates" 라고 나오지만 계획에 쓰는 이름은 SELECTED_DATES 다.)
        "scope": "FULL_CALENDAR" if len(dates) == len(calendar) else "SELECTED_DATES",
        "minimum_disk_gib": args.minimum_disk_gib,
    }

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan_path = output / "reload-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    config_path = output / "config.json"
    config_path.write_text(json.dumps({"output": str(output / "job"), "plan": str(plan_path)},
                                      ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    print(json.dumps({"config": str(config_path), "plan": str(plan_path),
                      "scope": plan["scope"], "dates": len(dates),
                      "expected_rows": plan["expected_rows"],
                      "minimum_disk_gib": plan["minimum_disk_gib"],
                      "db_identity": plan["db_identity"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
