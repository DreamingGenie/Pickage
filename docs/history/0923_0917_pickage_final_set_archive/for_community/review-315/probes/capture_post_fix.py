"""최종 정규 Gradle XML과 community 소스 목록을 보존한다. baseline 증거는 덮어쓰지 않는다."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "docs/history/0923_0917_pickage_final_set_archive/for_community/review-315/evidence/post-fix-results.json"
result = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
result["commands"] = ["gradlew.bat test build integrationTest --console=plain", "npm.cmd run typecheck", "npm.cmd run build"]
result["suites"] = {}
for source_set in ("test", "integrationTest"):
    cases = []
    for xml in sorted((ROOT / "backend/build/test-results" / source_set).glob("TEST-*.xml")):
        for case in ET.parse(xml).getroot().findall("testcase"):
            status = "FAIL" if case.find("failure") is not None or case.find("error") is not None else "SKIP" if case.find("skipped") is not None else "PASS"
            cases.append({"class": case.get("classname"), "test": case.get("name"), "status": status})
    assert cases, source_set
    assert all(c["status"] != "FAIL" for c in cases), source_set
    result["suites"][source_set] = {"counts": {s: sum(c["status"] == s for c in cases) for s in ("PASS", "FAIL", "SKIP")}, "cases": cases}
result["files"] = []
for source_set in ("main", "test", "integrationTest"):
    for path in sorted((ROOT / "backend/src" / source_set / "java/com/ssafy/pickage/domain/community").rglob("*.java")):
        content = path.read_text(encoding="utf-8")
        result["files"].append({"path": path.relative_to(ROOT).as_posix(), "sha256_lf": hashlib.sha256(content.encode()).hexdigest(), "lines": len(content.splitlines())})
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k:v["counts"] for k,v in result["suites"].items()}))
