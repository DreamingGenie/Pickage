"""Run from repository root: python -m pipeline.orchestration --help."""
import argparse
import json
from pathlib import Path
import sys

from . import runner
from .storage import WaitingInput


def main(argv=None):
    parser = argparse.ArgumentParser(description="MinIO raw → Curated preprocessing; no collection or DB load")
    parser.add_argument("command", choices=("plan", "run", "status", "resume"))
    parser.add_argument("--request", required=True, type=Path, help="Pinned input request JSON")
    parser.add_argument("--work-dir", type=Path, default=Path("data/orchestration"),
                        help="Persistent local cache and execution evidence; retain for resume")
    args = parser.parse_args(argv)
    try:
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
