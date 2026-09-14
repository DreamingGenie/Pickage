"""Full table rollups for actual row/count/value evidence; never writes to the DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .real_db import query, rows


QUERIES = {
    "package": "SELECT jsonb_build_object('rows',count(*),'invalid',count(*) FILTER(WHERE package_id<1 OR btrim(name)='')) FROM public.package",
    "version": "SELECT jsonb_build_object('rows',count(*),'invalid',count(*) FILTER(WHERE package_id<1 OR btrim(version)='' OR ordinal<0),"
               "'null_published_at',count(*) FILTER(WHERE published_at IS NULL)) FROM public.version",
    "package_snapshot": rows("SELECT snapshot_at,count(*) AS rows,count(downloads) AS downloads_nonnull,"
                             "count(stars) AS stars_nonnull,count(open_issues) AS open_issues_nonnull,"
                             "sum(downloads)::text AS downloads_sum,sum(stars)::text AS stars_sum,"
                             "sum(open_issues)::text AS open_issues_sum,"
                             "count(*) FILTER(WHERE downloads<0 OR stars<0 OR open_issues<0) AS invalid "
                             "FROM public.package_snapshot GROUP BY snapshot_at ORDER BY snapshot_at"),
    "package_version_snapshot": rows("SELECT snapshot_at,count(*) AS rows,"
                                     "count(*) FILTER(WHERE dependents_count=0) AS zero_rows,"
                                     "count(*) FILTER(WHERE dependents_count>0) AS positive_rows,"
                                     "sum(dependents_count)::text AS dependents_sum,max(dependents_count) AS max_dependents,"
                                     "count(*) FILTER(WHERE dependents_count<0 OR dependents_count IS NULL) AS invalid "
                                     "FROM public.package_version_snapshot GROUP BY snapshot_at ORDER BY snapshot_at"),
}


def scan(container, database, output, *, timeout=1200):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    state = {"scope": "FULL_DATABASE_ROLLUPS", "started_at": datetime.now(timezone.utc).isoformat(),
             "read_only": True, "parallel_workers": 0, "results": {}}
    def save():
        (output / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    for name, sql in QUERIES.items():
        state["active_query"] = name
        save()
        (output / (name + ".sql")).write_text(sql + ";\n", encoding="utf-8")
        print("Full read-only scan: " + name, flush=True)
        started = time.perf_counter()
        try:
            result, elapsed = query(container, database, sql, timeout=timeout)
            (output / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            state["results"][name] = {"status": "COMPLETE", "elapsed_seconds": elapsed}
        except Exception as error:
            state["results"][name] = {"status": "ERROR", "elapsed_seconds": round(time.perf_counter()-started,3),
                                       "error": str(error)}
        save()
        print(name + ": " + json.dumps(state["results"][name], ensure_ascii=False), flush=True)
    state["active_query"] = None
    state["ended_at"] = datetime.now(timezone.utc).isoformat()
    state["status"] = "COMPLETE" if all(v["status"] == "COMPLETE" for v in state["results"].values()) else "INCOMPLETE"
    save()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = scan(args.container, args.database, args.output)
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
