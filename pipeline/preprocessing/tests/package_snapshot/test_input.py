"""Producer-shaped fixtures exercise real selection and byte verification."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from pipeline.downloads.test_bronze import FakeS3
from pipeline.preprocessing.downloads_interval.policy import policy_document as download_policy
from pipeline.preprocessing.repository_metrics.policy import policy_document as repository_policy
from pipeline.preprocessing.snapshot.policy import policy_sha256 as snapshot_policy_sha256
from pipeline.preprocessing.package_snapshot import input as source
from pipeline.preprocessing.package_snapshot.policy import canonical_bytes

SNAPSHOT = "2026-08-31"
TIMESTAMP = "2026-08-31T21:01:10.517131Z"
INTERVAL = {
    "snapshot_at": SNAPSHOT, "snapshot_timestamp": TIMESTAMP,
    "previous_snapshot_at": "2026-08-24", "previous_snapshot_timestamp": "2026-08-24T21:01:08.477988Z",
    "download_start_inclusive": "2026-08-24", "download_end_exclusive": SNAPSHOT,
    "interval_days": 7, "interval_reason": None, "source_timestamps": [TIMESTAMP],
}


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class Fixture:
    def __init__(self, root):
        self.root, self.s3 = Path(root), FakeS3()
        self.root.mkdir(parents=True, exist_ok=True)
        candidate = {"policy_version": "snapshot-time-v1", "policy_sha256": snapshot_policy_sha256()}
        candidate_path = self.root / "candidate.json"
        candidate_path.write_bytes(canonical_bytes(candidate))
        candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        self.candidate = {"candidate": candidate, "candidate_sha256": candidate_sha,
                          "calendar": [copy.deepcopy(INTERVAL)]}
        self.args = dict(snapshot=SNAPSHOT, population_run_id="population", candidate_path=candidate_path,
                         candidate_sha256=candidate_sha, download_run_id="downloads", repository_run_id="repository")
        self.prefixes = {
            "population": f"depsdev/v1/package-version/snapshot={SNAPSHOT}/run_id=population",
            "downloads": f"npm-downloads-interval/v1/snapshot={SNAPSHOT}/run_id=downloads",
            "repository": f"depsdev/v1/repository-metrics/snapshot={SNAPSHOT}/run_id=repository",
        }
        self.paths = {}
        with duckdb.connect() as con:
            self._parquet(con, "population", "CREATE TABLE population(package_id INTEGER,name VARCHAR,repo_url VARCHAR); "
                          "INSERT INTO population VALUES (1,'alpha','https://github.com/o/a'),"
                          "(2,'beta','https://github.com/o/b'),(3,'gamma',NULL)")
        population_record = self.record("population", "attempts/a/package/data/data.parquet", "population")
        version_record = {"key": self.prefixes["population"] + "/attempts/a/version/data/data.parquet",
                          "bytes": 1, "sha256": "1" * 64}
        self.manifests = {"population": {
            "contract_version": 1, "status": "PASSED", "verification": "GET_SHA256_ALL_FILES",
            "request": {"snapshot": SNAPSHOT, "run_id": "population"},
            "report": {"output_counts": {"package/data": 3, "version/data": 1},
                       "snapshot_timestamp": TIMESTAMP[:-1]},
            "files": [population_record, version_record],
        }}
        self.write("population")
        lineage = {"curated_run_id": "population", "curated_manifest_sha256": self.args["population_manifest_sha256"],
                   "candidate_sha256": candidate_sha, "snapshot": SNAPSHOT,
                   "policy_version": "snapshot-time-v1", "policy_sha256": snapshot_policy_sha256()}
        download_input = {**lineage, "interval": copy.deepcopy(INTERVAL)}
        input_sha, aggregation_sha = digest(download_input), digest(download_policy())
        self.manifests["downloads"] = {
            "dataset": "npm-downloads-interval", "run_id": "downloads", "format_version": 1,
            "status": "PASSED", "required_remote_verification": "GET_SHA256_ALL_FILES",
            "aggregation_policy": download_policy(), "aggregation_policy_sha256": aggregation_sha,
            "contract_sha256": "2" * 64, "input_manifest": download_input,
            "input_manifest_sha256": input_sha, "interval": copy.deepcopy(INTERVAL), "files": [],
        }
        with duckdb.connect() as con:
            self._parquet(con, "downloads", "CREATE TABLE downloads(package_id INTEGER,snapshot_at DATE,"
                          "previous_snapshot_at DATE,download_sum BIGINT,expected_days INTEGER,observed_days INTEGER,"
                          "valid_days INTEGER,data_status VARCHAR,null_reason VARCHAR,quality_reasons VARCHAR[],"
                          "input_manifest_sha256 VARCHAR,policy_sha256 VARCHAR,aggregation_policy_sha256 VARCHAR); "
                          "INSERT INTO downloads VALUES "
                          f"(1,DATE '{SNAPSHOT}',DATE '2026-08-24',0,7,7,7,'COMPLETE',NULL,[],'{input_sha}',"
                          f"'{snapshot_policy_sha256()}','{aggregation_sha}'),"
                          f"(2,DATE '{SNAPSHOT}',DATE '2026-08-24',12,7,6,6,'PARTIAL',NULL,['ROW_MISSING'],'{input_sha}',"
                          f"'{snapshot_policy_sha256()}','{aggregation_sha}'),"
                          f"(3,DATE '{SNAPSHOT}',DATE '2026-08-24',NULL,7,0,0,'UNAVAILABLE','NOT_FOUND',['NOT_FOUND'],"
                          f"'{input_sha}','{snapshot_policy_sha256()}','{aggregation_sha}')")
            self._parquet(con, "daily_quality", "CREATE TABLE daily_quality(package_name VARCHAR,day DATE,reason VARCHAR); "
                          "INSERT INTO daily_quality VALUES ('beta',DATE '2026-08-25','ROW_MISSING')")
            self._parquet(con, "unmatched_packages", "CREATE TABLE unmatched_packages(package_name VARCHAR); "
                          "INSERT INTO unmatched_packages VALUES ('outside')")
            self._parquet(con, "repository", "CREATE TABLE repository(package_id INTEGER,snapshot_at DATE,stars INTEGER,open_issues INTEGER); "
                          f"INSERT INTO repository VALUES (1,DATE '{SNAPSHOT}',0,NULL),"
                          f"(2,DATE '{SNAPSHOT}',100,2),(3,DATE '{SNAPSHOT}',NULL,NULL)")
            self._parquet(con, "selection", "CREATE TABLE selection(package_id INTEGER,version VARCHAR,ordinal BIGINT,"
                          "repo_url VARCHAR,provider VARCHAR,project_path VARCHAR,comparison_project_path VARCHAR,"
                          "observed_project_path VARCHAR,snapshot VARCHAR,snapshot_timestamp VARCHAR,"
                          "observed_timestamp TIMESTAMPTZ,reason VARCHAR,mapping_status VARCHAR); INSERT INTO selection VALUES "
                          f"(1,'1.0.0',1,'https://github.com/o/a','github.com','o/a','o/a','o/a','{SNAPSHOT}','{TIMESTAMP}',"
                          f"TIMESTAMPTZ '{TIMESTAMP}','SELECTED','MATCHED'),"
                          f"(2,'2.0.0',2,'https://github.com/o/b','github.com','o/b','o/b','o/b','{SNAPSHOT}','{TIMESTAMP}',"
                          f"TIMESTAMPTZ '{TIMESTAMP}','SELECTED','MATCHED'),"
                          f"(3,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'{SNAPSHOT}','{TIMESTAMP}',NULL,"
                          "'NO_VALID_REPOSITORY','NO_SELECTED_REPOSITORY')")
        for name, role in (("downloads", "interval_downloads"), ("daily_quality", "daily_quality"),
                           ("unmatched_packages", "unmatched_packages")):
            self.manifests["downloads"]["files"].append(self.record(name, role + ".parquet", "downloads", role))
        self.write("downloads")
        self.manifests["repository"] = {
            "dataset": "repository-metrics", "run_id": "repository", "format_version": 1,
            "status": "PASSED", "verification": "LOCAL_SHA256_PARQUET_RECONCILIATION",
            "snapshot": SNAPSHOT, "snapshot_timestamp": TIMESTAMP,
            "policy": repository_policy(),
            "request": {"policy_sha256": digest(repository_policy()), "code_sha256": "3" * 64,
                        "input_sha256": "4" * 64},
            "input": {**lineage, "snapshot_timestamp": TIMESTAMP, "input_sha256": "4" * 64},
            "files": [self.record("repository", "attempts/a/outputs/metric/data/part.parquet", "repository", "metric/data"),
                      self.record("selection", "attempts/a/outputs/quality/selection/part.parquet", "repository", "quality/selection")],
        }
        self.write("repository")

    def _parquet(self, con, name, sql):
        path = self.root / (name + ".parquet")
        con.execute(sql)
        con.execute(f"COPY {name} TO ? (FORMAT PARQUET)", [str(path)])
        self.paths[name] = path

    def record(self, name, path, producer, role=None):
        body = self.paths[name].read_bytes()
        base = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        if producer == "population":
            key = self.prefixes[producer] + "/" + path
            record = {**base, "key": key}
        else:
            with duckdb.connect() as con:
                count = con.execute("SELECT count(*) FROM read_parquet(?)", [str(self.paths[name])]).fetchone()[0]
            record = {**base, "path": path, ("row_count" if producer == "downloads" else "rows"): count,
                      ("role" if producer == "downloads" else "dataset"): role}
            key = self.prefixes[producer] + ("/data/" if producer == "downloads" else "/") + path
        self.s3.objects[(source.BUCKET, key)] = body
        return record

    def write(self, producer):
        manifest = self.manifests[producer]
        if producer == "downloads":
            manifest["input_manifest_sha256"] = digest(manifest["input_manifest"])
        if producer == "repository":
            manifest["request"]["input_sha256"] = digest(manifest["input"])
        body = canonical_bytes(manifest)
        checksum = hashlib.sha256(body).hexdigest()
        prefix = self.prefixes[producer]
        self.s3.objects[(source.BUCKET, prefix + "/run_manifest.json")] = body
        marker = (checksum + "\n").encode() if producer == "downloads" else canonical_bytes({"manifest_sha256": checksum})
        self.s3.objects[(source.BUCKET, prefix + "/_SUCCESS")] = marker
        if producer == "downloads":
            self.s3.objects[(source.BUCKET, prefix + "/_INPUT.json")] = canonical_bytes({"manifest_sha256": checksum})
        argument = {"population": "population_manifest_sha256", "downloads": "download_manifest_sha256",
                    "repository": "repository_manifest_sha256"}[producer]
        self.args[argument] = checksum

    def prepare(self, cache="cache"):
        with patch.object(source, "read_candidate", return_value=self.candidate):
            return source.prepare(self.s3, **self.args, cache_dir=self.root / cache)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = Fixture(Path(self.temporary.name))

    def test_real_producer_namespaces_and_all_selected_files(self):
        prepared = self.fixture.prepare()
        manifest = prepared["input_manifest"]
        self.assertIn("/data/interval_downloads.parquet", manifest["download_files"][0]["key"])
        self.assertIn("/attempts/a/outputs/metric/data/", manifest["repository_files"][0]["key"])
        self.assertEqual(sum(len(prepared[group]) for group in source.GROUPS), 6)
        self.assertEqual(prepared["population_rows"], 3)
        with patch.object(source, "read_candidate", return_value=self.fixture.candidate):
            source.revalidate(self.fixture.s3, prepared)

    def test_candidate_actual_bytes_rejected(self):
        self.fixture.args["candidate_path"].write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "candidate SHA"):
            self.fixture.prepare()

    def test_markers_manifest_and_input_lock_rejected(self):
        fixture = self.fixture
        for producer in ("population", "downloads", "repository"):
            for suffix in ("/_SUCCESS", "/run_manifest.json"):
                key = (source.BUCKET, fixture.prefixes[producer] + suffix)
                saved = fixture.s3.objects[key]
                fixture.s3.objects[key] = b"{}"
                with self.subTest(producer=producer, suffix=suffix), self.assertRaises(ValueError):
                    fixture.prepare()
                fixture.s3.objects[key] = saved
        fixture.s3.objects[(source.BUCKET, fixture.prefixes["downloads"] + "/_INPUT.json")] = b"{}"
        with self.assertRaisesRegex(ValueError, "input lock"):
            fixture.prepare()

    def test_lineage_policy_and_exact_times_rejected(self):
        fixture = self.fixture
        changes = [
            ("downloads", ("input_manifest", "curated_manifest_sha256"), "f" * 64),
            ("repository", ("input", "candidate_sha256"), "f" * 64),
            ("repository", ("input", "curated_run_id"), "another"),
            ("downloads", ("interval", "previous_snapshot_at"), "2026-08-23"),
            ("repository", ("snapshot_timestamp",), "2026-08-31T21:01:10.517132Z"),
            ("population", ("report", "snapshot_timestamp"), "2026-08-31T21:01:10.517132"),
            ("downloads", ("aggregation_policy", "partial_results"), "discard"),
            ("repository", ("request", "policy_sha256"), "f" * 64),
        ]
        for producer, keys, value in changes:
            original = copy.deepcopy(fixture.manifests[producer])
            target = fixture.manifests[producer]
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            fixture.write(producer)
            with self.subTest(producer=producer, keys=keys), self.assertRaises(ValueError):
                fixture.prepare()
            fixture.manifests[producer] = original
            fixture.write(producer)

    def test_unsafe_duplicate_and_wrong_role_paths_rejected(self):
        original = copy.deepcopy(self.fixture.manifests["repository"])
        for path in ("../metric/data/x.parquet", "attempts/a/outputs/quality/selection/x.parquet",
                     "attempts/a/outputs/metric/data/*.parquet"):
            manifest = copy.deepcopy(original)
            manifest["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                source._records(manifest, "metric/data", "prefix")
        original["files"].append(copy.deepcopy(original["files"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            source._records(original, "metric/data", "prefix")

    def test_manifest_counts_and_remote_bytes_rejected(self):
        fixture = self.fixture
        fixture.manifests["repository"]["files"][0]["rows"] = 2
        fixture.write("repository")
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            fixture.prepare()
        fixture.manifests["repository"]["files"][0]["rows"] = 3
        fixture.write("repository")
        key = fixture.prefixes["downloads"] + "/data/interval_downloads.parquet"
        fixture.s3.objects[(source.BUCKET, key)] += b"changed"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            fixture.prepare()

    def test_revalidate_checks_controls_remote_and_cached_bytes(self):
        prepared = self.fixture.prepare()
        key = (source.BUCKET, self.fixture.prefixes["repository"] + "/_SUCCESS")
        saved = self.fixture.s3.objects[key]
        self.fixture.s3.objects[key] = b"{}"
        with patch.object(source, "read_candidate", return_value=self.fixture.candidate):
            with self.assertRaisesRegex(ValueError, "marker"):
                source.revalidate(self.fixture.s3, prepared)
        self.fixture.s3.objects[key] = saved
        Path(prepared["download_files"][0]).write_bytes(b"changed")
        with patch.object(source, "read_candidate", return_value=self.fixture.candidate):
            with self.assertRaisesRegex(ValueError, "cached input changed"):
                source.revalidate(self.fixture.s3, prepared)


if __name__ == "__main__":
    unittest.main()
