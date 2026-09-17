"""Run from repository root: python -m pipeline.orchestration --help."""
import argparse
import json
from pathlib import Path
import sys

from . import runner
from .storage import WaitingInput


def main(argv=None):
    parser = argparse.ArgumentParser(description="MinIO raw → Curated preprocessing; no collection or DB load")
    parser.add_argument("command", choices=("plan", "run", "status", "resume", "weekly"))
    parser.add_argument("--request", type=Path, help="Pinned input request JSON")
    parser.add_argument("--work-dir", type=Path, default=Path("data/orchestration"),
                        help="Persistent local cache and execution evidence; retain for resume")
    parser.add_argument("--snapshot", help="Weekly snapshot date (YYYY-MM-DD)")
    parser.add_argument("--run-id", help="Unique Curated run ID; reuse to resume")
    parser.add_argument("--bronze-run-id", help="Override collector Bronze run ID")
    parser.add_argument("--download-run-id", help="Override collector downloads run ID")
    parser.add_argument("--download-history-run-id", action="append", default=[],
                        help="Additional approved download run; repeat in descending priority order")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--repository-engine", choices=("native", "docker"), default="native")
    args = parser.parse_args(argv)
    if args.command == "weekly" and (not args.snapshot or not args.run_id or args.request):
        parser.error("weekly requires --snapshot and --run-id and generates its own request")
    if args.command != "weekly" and not args.request:
        parser.error("--request is required for plan/run/status/resume")
    try:
        if args.command == "weekly":
            from .contracts import RUN, iso_day
            from .weekly_request import build_request
            from .storage import atomic_json
            from pipeline.minio.ingest_raw import client
            iso_day(args.snapshot)
            if not RUN.fullmatch(args.run_id):
                raise ValueError("Invalid run_id")
            s3 = client()
            request_path = args.work_dir / "requests" / (args.run_id + ".json")
            if request_path.exists():
                request = json.loads(request_path.read_bytes())
                if request["snapshot"] != args.snapshot or request["run_id"] != args.run_id:
                    raise ValueError("Saved weekly request identity differs")
                if args.bronze_run_id and request["bronze_run_id"] != args.bronze_run_id:
                    raise ValueError("Saved weekly Bronze run differs")
                if args.download_run_id and request["raw_refs"]["downloads"]["run_id"] != args.download_run_id:
                    raise ValueError("Saved weekly downloads run differs")
                if args.download_history_run_id and [r["run_id"] for r in request.get("download_history_refs", [])] != args.download_history_run_id:
                    raise ValueError("Saved weekly download history differs")
            else:
                request = build_request(s3, args.snapshot, args.run_id, args.work_dir,
                    bronze_run_id=args.bronze_run_id, download_run_id=args.download_run_id,
                    download_history_run_ids=args.download_history_run_id,
                    options={"workers": 2, "threads": args.threads, "memory_limit": args.memory_limit,
                             "repository_engine": args.repository_engine})
                atomic_json(request_path, request)
            bundle = runner.run(request, s3, args.work_dir)
            print(json.dumps({"status": bundle["status"], "run_id": args.run_id,
                              "prefix": runner.run_prefix(request), "request": str(request_path),
                              "db_loaded": False}, ensure_ascii=False, indent=2))
            return 0
        request = json.loads(args.request.read_text(encoding="utf-8-sig"))
        runner.plan(request)  # Validate before opening any connection.
        if args.command == "plan":
            result = runner.plan(request)
        else:
            from pipeline.minio.ingest_raw import client
            s3 = client()
            if args.command == "status":
                result = runner.status(request, s3)
            else:
                bundle = runner.run(request, s3, args.work_dir, resume=args.command == "resume")
                result = {"status": bundle["status"], "run_id": request["run_id"],
                          "prefix": runner.run_prefix(request), "db_loaded": False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except WaitingInput as error:
        print(json.dumps({"status": "WAITING_INPUT", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
