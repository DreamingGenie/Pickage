"""EV2-05 — Subway timetable freshness: compare OA-22522 (2025-09-30, Phase 1)
against a newer data.go.kr file (dataset pk 15098251, file basis 2026-06-16,
downloaded fresh this session) for the 4 Route A corridor station x line
nodes (안국/3, 교대/3, 교대/2, 역삼/2).

Priority-1 check per 10_PHASE2_EVIDENCE_EXECUTION.md EV2-05: "동일 공식
source의 더 최신 파일/공지 존재 여부". A newer file was found (see
EVD-SCHED-002/README.md for provenance) - this script quantifies how much
the schedule itself actually changed between the two snapshots, which is
the real freshness question (a newer *file* with an identical schedule
would resolve the concern; a newer file with a materially different
schedule would confirm staleness was a real risk).

Usage:
    python analyze_timetable_freshness.py
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

OLD_FILE = (
    Path(__file__).resolve().parents[2]
    / "phase1" / "EVD-SCHED-001" / "raw"
    / "OA-22522_#Ub3c4#Uc2dc#Ucca0#Ub3c4#Uc5f4#Ucc28#Uc6b4#Ud589#Uc2dc#Uac01#Ud45c_20250930.csv"
)
NEW_FILE = Path(__file__).resolve().parent.parent / "EVD-SCHED-002" / "raw" / "OA-fresh_20260616.csv"

TARGETS = [
    ("안국", "3"),
    ("교대", "3"),
    ("교대", "2"),
    ("역삼", "2"),
]


def _to_seconds(hhmmss: str) -> int | None:
    if not hhmmss:
        return None
    parts = hhmmss.split(":")
    if len(parts) != 3:
        return None
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s  # NOTE: preserves >=24:00:00 rollover values as-is


def load(path: Path, encoding: str) -> list[dict]:
    rows = []
    with path.open(encoding=encoding, errors="strict") as f:
        r = csv.reader(f)
        header = next(r)
        idx = {name: i for i, name in enumerate(header)}
        # Old file: ROWNUM,LINE,SI_ID,STATION_NM,WEEKTAG,INOUTTAG,GUBHANG,TRAIN_NO,STT,EDT,ST_STT_NM,ED_STT_NM
        # New file: 고유번호,호선,역사코드,역사명,주중주말,방향,급행여부,열차코드,열차도착시간,열차출발시간,출발역,도착역
        name_col = "STATION_NM" if "STATION_NM" in idx else "역사명"
        line_col = "LINE" if "LINE" in idx else "호선"
        week_col = "WEEKTAG" if "WEEKTAG" in idx else "주중주말"
        dir_col = "INOUTTAG" if "INOUTTAG" in idx else "방향"
        stt_col = "STT" if "STT" in idx else "열차도착시간"
        edt_col = "EDT" if "EDT" in idx else "열차출발시간"
        for row in r:
            rows.append(
                {
                    "name": row[idx[name_col]],
                    "line": row[idx[line_col]],
                    "weektag": row[idx[week_col]],
                    "dir": row[idx[dir_col]],
                    "stt": row[idx[stt_col]],
                    "edt": row[idx[edt_col]],
                }
            )
    return rows


def summarize(rows: list[dict]) -> dict:
    by_key: dict[tuple, list[int]] = defaultdict(list)
    for r in rows:
        for name, line in TARGETS:
            if r["name"] == name and r["line"] == line:
                sec = _to_seconds(r["edt"]) if r["edt"] else _to_seconds(r["stt"])
                if sec is not None:
                    by_key[(name, line, r["weektag"], r["dir"])].append(sec)
    out = {}
    for key, secs in by_key.items():
        secs_sorted = sorted(secs)
        headways = [b - a for a, b in zip(secs_sorted, secs_sorted[1:]) if b >= a]
        out["|".join(key)] = {
            "trains": len(secs_sorted),
            "median_headway_sec": (statistics.median(headways) if headways else None),
            "p10_headway_sec": (
                statistics.quantiles(headways, n=10)[0] if len(headways) >= 10 else None
            ),
            "p90_headway_sec": (
                statistics.quantiles(headways, n=10)[8] if len(headways) >= 10 else None
            ),
            "first_departure": secs_sorted[0] if secs_sorted else None,
            "last_departure": secs_sorted[-1] if secs_sorted else None,
        }
    return out


def main() -> None:
    old_rows = load(OLD_FILE, encoding="utf-8-sig")
    new_rows = load(NEW_FILE, encoding="cp949")

    old_summary = summarize(old_rows)
    new_summary = summarize(new_rows)

    comparison = {}
    for key in sorted(set(old_summary) | set(new_summary)):
        o = old_summary.get(key)
        n = new_summary.get(key)
        delta_trains = (n["trains"] - o["trains"]) if (o and n) else None
        delta_median = (
            (n["median_headway_sec"] - o["median_headway_sec"])
            if (o and n and o["median_headway_sec"] is not None and n["median_headway_sec"] is not None)
            else None
        )
        comparison[key] = {
            "old_2025-09-30": o,
            "new_2026-06-16": n,
            "delta_trains": delta_trains,
            "delta_median_headway_sec": delta_median,
        }

    out_dir = Path(__file__).resolve().parent.parent / "EVD-SCHED-002" / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "freshness_comparison.json"
    out_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    for key, c in comparison.items():
        o, n = c["old_2025-09-30"], c["new_2026-06-16"]
        print(
            f"{key}: old_trains={o['trains'] if o else None} new_trains={n['trains'] if n else None} "
            f"delta_trains={c['delta_trains']} delta_median_headway_sec={c['delta_median_headway_sec']}"
        )


if __name__ == "__main__":
    main()
