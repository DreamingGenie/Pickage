"""수집한 Bronze를 운행일 단위로 묶어 내보낸다.

    # 오늘 운행일 수집 현황만 확인 (묶지 않음)
    python -m collector.export_bronze --summary

    # 오늘 운행일을 zip으로 묶기
    python -m collector.export_bronze

    # 특정 운행일 / 전체
    python -m collector.export_bronze --service-date 2026-08-27
    python -m collector.export_bronze --all

산출물은 `data/exports/bronze_<운행일>.zip`이며 안에 `MANIFEST.json`이 함께 들어간다.

**묶기 전에 원문의 sha256을 메타에 기록된 값과 대조한다.** 파일이 조용히 손상된
채 넘어가면 Silver 적재에서 원인을 찾기 어렵고, 실시간 데이터는 다시 받을 수
없어 손상 사실 자체를 늦게 아는 것이 가장 나쁘다. 불일치가 있으면 매니페스트에
기록하고 종료 코드 1을 반환한다(묶기는 계속한다 — 손상된 파일도 증거다).

원문을 지우지 않는다. 내보내기는 복사이며 Bronze는 그대로 남는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .common import console, service_day, storage

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPORT_DIR = _REPO_ROOT / "data" / "exports"


def service_dates(bronze_dir: Path) -> list[str]:
    """Bronze에 존재하는 운행일 목록."""
    dates = {
        p.name.split("=", 1)[1]
        for p in bronze_dir.glob("*/service_date=*")
        if p.is_dir() and "=" in p.name
    }
    return sorted(dates)


def collect_pairs(bronze_dir: Path, svc_date: str) -> list[tuple[Path, dict]]:
    """(메타 경로, 메타 내용) 목록. 메타가 깨진 파일은 건너뛰고 경고한다."""
    pairs = []
    for meta_path in sorted(bronze_dir.glob(f"*/service_date={svc_date}/*.meta.json")):
        try:
            pairs.append((meta_path, json.loads(meta_path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [경고] 메타를 읽을 수 없어 제외합니다: {meta_path.name} ({exc})")
    return pairs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_report(bronze_dir: Path, svc_date: str, *, verify: bool = True) -> dict:
    """운행일 하나의 수집 현황과 무결성 검사 결과."""
    pairs = collect_pairs(bronze_dir, svc_date)
    per_source: dict[str, dict] = defaultdict(
        lambda: {
            "records": 0, "ok": 0, "business_error": 0, "http_error": 0,
            "transport_error": 0, "rows": 0, "payload_bytes": 0,
            "first_at": None, "last_at": None,
        }
    )
    mismatched: list[str] = []
    missing_payload: list[str] = []
    key_ids: set[str] = set()
    versions: set[str] = set()

    for meta_path, meta in pairs:
        src = per_source[meta.get("source_key") or "unknown"]
        src["records"] += 1
        outcome = (meta.get("outcome") or "").lower()
        if outcome in ("ok", "business_error", "http_error", "transport_error"):
            src[outcome if outcome != "ok" else "ok"] += 1
        src["rows"] += meta.get("row_count") or 0
        src["payload_bytes"] += meta.get("payload_bytes") or 0
        at = meta.get("requested_at")
        if at:
            src["first_at"] = min(src["first_at"] or at, at)
            src["last_at"] = max(src["last_at"] or at, at)
        if meta.get("key_id"):
            key_ids.add(meta["key_id"])
        if meta.get("collector_version"):
            versions.add(meta["collector_version"])

        name = meta.get("payload_file")
        if not name:
            continue  # TRANSPORT_ERROR는 원문이 없다. 정상이다.
        payload = meta_path.parent / name
        if not payload.exists():
            missing_payload.append(name)
            continue
        if verify and meta.get("payload_sha256") and _sha256(payload) != meta["payload_sha256"]:
            mismatched.append(name)

    return {
        "service_date": svc_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(pairs),
        "per_source": {k: dict(v) for k, v in sorted(per_source.items())},
        "total_payload_bytes": sum(v["payload_bytes"] for v in per_source.values()),
        "key_ids": sorted(key_ids),
        "collector_versions": sorted(versions),
        "integrity": {
            "verified": verify,
            "sha256_mismatch": mismatched,
            "missing_payload_file": missing_payload,
        },
    }


def print_report(report: dict) -> None:
    print(f"\n운행일 {report['service_date']} — 기록 {report['record_count']}건, "
          f"{report['total_payload_bytes'] / 1024 / 1024:.1f} MB")
    if not report["per_source"]:
        print("  (수집된 기록이 없습니다)")
        return
    print(f"  {'source_key':24} {'기록':>6} {'성공':>6} {'실패':>6} {'행':>9} {'MB':>8}  수집 구간")
    for src, s in report["per_source"].items():
        fail = s["business_error"] + s["http_error"] + s["transport_error"]
        span = ""
        if s["first_at"] and s["last_at"]:
            span = f"{s['first_at'][11:16]}~{s['last_at'][11:16]} UTC"
        print(f"  {src:24} {s['records']:>6} {s['ok']:>6} {fail:>6} {s['rows']:>9} "
              f"{s['payload_bytes'] / 1024 / 1024:>8.1f}  {span}")

    ident = report["key_ids"]
    if "sample" in ident:
        print(f"  [주의] 샘플키 기록이 섞여 있습니다(key_id={ident}). "
              f"샘플키 응답은 행 수가 제한된 잘린 데이터입니다.")
    integ = report["integrity"]
    if integ["sha256_mismatch"]:
        print(f"  [오류] sha256 불일치 {len(integ['sha256_mismatch'])}건: "
              f"{integ['sha256_mismatch'][:3]}")
    if integ["missing_payload_file"]:
        print(f"  [오류] 원문 파일 없음 {len(integ['missing_payload_file'])}건: "
              f"{integ['missing_payload_file'][:3]}")


def export(bronze_dir: Path, svc_date: str, out_dir: Path, *, verify: bool = True) -> tuple[Path, dict]:
    """운행일 하나를 zip으로 묶고 (경로, 매니페스트)를 반환한다."""
    report = build_report(bronze_dir, svc_date, verify=verify)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"bronze_{svc_date}.zip"

    # XML/JSON은 압축률이 높다. 저장 공간과 전송량을 줄이려고 DEFLATE를 쓴다.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for meta_path, meta in collect_pairs(bronze_dir, svc_date):
            rel_dir = f"{meta_path.parent.parent.name}/{meta_path.parent.name}"
            zf.write(meta_path, f"{rel_dir}/{meta_path.name}")
            name = meta.get("payload_file")
            if name and (meta_path.parent / name).exists():
                zf.write(meta_path.parent / name, f"{rel_dir}/{name}")
        zf.writestr("MANIFEST.json", json.dumps(report, ensure_ascii=False, indent=2))
    return archive, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bronze를 운행일 단위로 내보낸다")
    parser.add_argument("--service-date", help="운행일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--all", action="store_true", help="Bronze에 있는 모든 운행일")
    parser.add_argument("--summary", action="store_true", help="묶지 않고 현황만 출력")
    parser.add_argument("--out", type=Path, default=DEFAULT_EXPORT_DIR, help="출력 디렉터리")
    parser.add_argument("--no-verify", action="store_true", help="sha256 대조 생략(빠름)")
    args = parser.parse_args(argv)
    console.use_utf8()

    bronze = storage.BRONZE_DIR
    if not bronze.exists():
        print(f"Bronze 디렉터리가 없습니다: {bronze}", file=sys.stderr)
        return 2

    if args.all:
        dates = service_dates(bronze)
    elif args.service_date:
        dates = [args.service_date]
    else:
        dates = [service_day.service_date(datetime.now(timezone.utc))]
    if not dates:
        print("내보낼 운행일이 없습니다.", file=sys.stderr)
        return 2

    bad = False
    for svc_date in dates:
        if args.summary:
            report = build_report(bronze, svc_date, verify=not args.no_verify)
            print_report(report)
        else:
            archive, report = export(bronze, svc_date, args.out, verify=not args.no_verify)
            print_report(report)
            size = archive.stat().st_size
            ratio = (size / report["total_payload_bytes"]) if report["total_payload_bytes"] else 0
            print(f"  -> {archive}  ({size / 1024 / 1024:.1f} MB"
                  f"{f', 압축률 {ratio:.0%}' if ratio else ''})")
        integ = report["integrity"]
        bad = bad or bool(integ["sha256_mismatch"] or integ["missing_payload_file"])

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
