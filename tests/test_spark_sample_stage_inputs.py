import csv
import hashlib
import tempfile
import unittest
import json
from pathlib import Path

import duckdb

from pipeline.spark_experiment.job import verify_manifest
from pipeline.spark_experiment.runtime.sample_stage_inputs import sample_manifest


def _parquet(path: Path, schema: str, rows: list[tuple]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE data ({schema})")
        if rows:
            placeholders = ",".join(["(" + ",".join(["?"] * len(rows[0])) + ")"] * len(rows))
            con.execute(f"INSERT INTO data VALUES {placeholders}", [value for row in rows for value in row])
        con.execute("COPY data TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])
    return str(path)


def _source_manifest(root: Path) -> Path:
    names = [("alpha",), ("beta",), ("gamma",)]
    versions = _parquet(root / "versions.parquet", "Name VARCHAR, version VARCHAR, source_repo VARCHAR", [(n, v, 'https://github.com/' + n[0] + '/' + n[0]) for n in ("alpha", "beta", "gamma") for v in ("1.0.0", "2.0.0")])
    requirements = _parquet(root / "requirements.parquet", "Name VARCHAR, version VARCHAR, dependency VARCHAR", [(n, "1.0.0", "beta") for n, in names])
    previous_ids = _parquet(root / "previous_ids.parquet", "package_id INTEGER, name VARCHAR", [(1, "alpha"), (2, "beta"), (3, "gamma")])
    dep_package = _parquet(root / "dep-package.parquet", "package_id INTEGER, name VARCHAR", [(1, "alpha"), (2, "beta"), (3, "gamma")])
    dep_version = _parquet(root / "dep-version.parquet", "package_id INTEGER, version VARCHAR", [(i, v) for i in (1, 2, 3) for v in ("1.0.0", "2.0.0")])
    dep_targets = _parquet(root / "dependents-targets.parquet", "name VARCHAR", [("alpha",), ("beta",)])
    dl_package = _parquet(root / "download-package.parquet", "package_id INTEGER, name VARCHAR, repo_url VARCHAR", [(1, "alpha", "https://github.com/a/a"), (2, "beta", "https://github.com/b/b"), (3, "gamma", "https://github.com/g/g")])
    status = _parquet(root / "status.parquet", "name VARCHAR, tier VARCHAR, status VARCHAR", [(n, "A", "OK") for n, in names])
    daily = _parquet(root / "daily" / "date=2026-09-01" / "part.parquet", "name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN, tier VARCHAR, fetched_at TIMESTAMP, date DATE, run_id VARCHAR", [(n, 1, False, "A", "2026-09-02", "2026-09-01", "r") for n, in names])
    target_csv = root / "download-targets.csv"
    with target_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["name"])
        writer.writerows(names)
    repo_package = _parquet(root / "repo-package.parquet", "package_id INTEGER, name VARCHAR, repo_url VARCHAR", [(1, "alpha", "https://github.com/a/a"), (2, "beta", "https://github.com/b/b"), (3, "gamma", "https://github.com/g/g")])
    repo_version = _parquet(root / "repo-version.parquet", "version VARCHAR, package_id INTEGER", [("1.0.0", i) for i in (1, 2, 3)])
    projects = _parquet(root / "projects.parquet", "Type VARCHAR, project_name VARCHAR", [("GITHUB", "a/a"), ("GITHUB", "b/b"), ("GITHUB", "unused/x")])
    snap_download = _parquet(root / "snapshot-download.parquet", "package_id INTEGER, value INTEGER", [(1, 1), (2, 2), (3, 3)])
    snap_repo = _parquet(root / "snapshot-repo.parquet", "package_id INTEGER, value INTEGER", [(1, 1), (2, 2), (3, 3)])
    snap_selection = _parquet(root / "snapshot-selection.parquet", "package_id INTEGER, value INTEGER", [(1, 1), (2, 2), (3, 3)])
    manifest = {
        "format_version": 1, "scope": "FIXED_STAGE_INPUT_COMPARISON", "source_request": {"snapshot": "2026-09-01", "snapshot_timestamp":"2026-09-01T00:00:00Z"},
        "stages": {
            "package_version": {"versions": [versions], "requirements": [requirements], "previous_ids": [previous_ids]},
            "downloads": {"package_files": [dl_package], "daily_files": [daily], "target_file": str(target_csv), "status_file": status, "interval": {"start": "2026-08-01", "end": "2026-09-01"}},
            "repository": {"files": {"package": [repo_package], "version": [repo_version], "projects": [projects]}},
            "package_snapshot": {"population_files": [dep_package], "download_files": [snap_download], "repository_files": [snap_repo], "selection_files": [snap_selection]},
            "dependents": {"files": {"package": [dep_package], "version": [dep_version], "targets": dep_targets}},
        },
    }
    manifest['stages']['downloads']['lineage'] = {'policy_sha256':'a'*64,'input_manifest_sha256':'b'*64,'aggregation_policy_sha256':'c'*64}
    manifest['input_files'] = [{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.rglob('*') if p.is_file()]
    path = root / "source-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_sample_manifest_is_deterministic_and_preserves_stage_contracts(tmp_path):
    source = _source_manifest(tmp_path / "source")
    first = sample_manifest(source, tmp_path / "first", "code", limit=2)
    second = sample_manifest(source, tmp_path / "second", "code", limit=2)
    one = json.loads(first.read_text(encoding="utf-8"))
    two = json.loads(second.read_text(encoding="utf-8"))
    assert one["sample"]["package_rows"] == 2
    assert one["sample"]["selection_sha256"] == two["sample"]["selection_sha256"]
    assert one["stages"]["package_version"]["previous_ids"]
    assert one["stages"]["dependents"]["files"]["targets"].endswith(".parquet")
    assert all("date=2026-09-01" in path for path in one["stages"]["downloads"]["daily_files"])
    assert one["stages"]["repository"]["counts"]["package"] == 2
    verify_manifest(one)
    with duckdb.connect() as con:
        names = {row[0] for row in con.execute("SELECT DISTINCT Name FROM read_parquet(?)", [one["stages"]["package_version"]["versions"][0]]).fetchall()}
        assert len(names) == 2
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [one["stages"]["package_version"]["versions"][0]]).fetchone()[0] == 4

class SampleInputTests(unittest.TestCase):
    def test_selection_and_contracts(self):
        with tempfile.TemporaryDirectory() as root:
            test_sample_manifest_is_deterministic_and_preserves_stage_contracts(Path(root))

    def test_changed_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            source = _source_manifest(Path(root)/'src')
            record = json.loads(source.read_text())['input_files'][0]
            Path(record['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Frozen experiment input changed'):
                sample_manifest(source,Path(root)/'out','code',limit=2)
