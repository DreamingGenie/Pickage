"""Run from repository root after the review probes; copy no raw application logs."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "docs/for_community/review-315/evidence"
OUT.mkdir(exist_ok=True)
results = []
for task in ("test", "integrationTest"):
    for path in sorted((ROOT / "backend/build/test-results" / task).glob("TEST-*.xml")):
        tree = ET.parse(path).getroot()
        if not tree.attrib["name"].endswith("ContractReviewTest"):
            continue
        for case in tree.findall("testcase"):
            failure = case.find("failure")
            results.append({"task": task, "class": tree.attrib["name"], "test": case.attrib["name"],
                "result": "FAIL" if failure is not None else "PASS",
                "message": failure.attrib.get("message", "").splitlines()[0] if failure is not None else ""})
summary = {"baseline": "d9193a3744c904963ad13c8c710f0548a9ab8437", "date": "2026-09-11",
    "total": len(results), "passed": sum(r["result"] == "PASS" for r in results),
    "failed": sum(r["result"] == "FAIL" for r in results), "tests": results}
(OUT / "probe-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
inventory = []
for source_set in ("main", "test", "integrationTest"):
    base = ROOT / f"backend/src/{source_set}/java/com/ssafy/pickage/domain/community"
    for path in sorted(base.rglob("*.java")):
        content = path.read_text(encoding="utf-8")
        inventory.append({"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "lines": len(content.splitlines()),
            "source_set": source_set,
            "test_methods": re.findall(r"(?:void|boolean)\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[^\{]+)?\{", content) if source_set != "main" else []})
(OUT / "community-file-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "tests"}, ensure_ascii=False))
print("community files:", len(inventory))
