import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from .bridge import NodeSession, discover_runtime, resolve_prepared
from .policy import make_policy, validate_policy


class SemverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = discover_runtime()

    def tearDown(self):
        self.temp.cleanup()

    def session(self):
        return NodeSession(self.runtime, self.root / "node.log")

    def test_ranges_prerelease_and_original_build_tie(self):
        with self.session() as node:
            metadata = node.request({"op": "metadata"})
            self.assertEqual(metadata["options"], {"loose": False, "includePrerelease": False})
            self.assertRegex(metadata["dependency_closure_sha256"], r"^[0-9a-f]{64}$")
            node.request({"op": "start", "name": "@scope/target"})
            rejected = node.request({"op": "candidates", "versions": ["1.2.1", "1.3.0+b", "1.3.0+a", "1.3.0-beta.1", "2.0.0", "1.02.3", "1.2.3-rev.01"]})
            self.assertEqual(len(rejected["rejected"]), 3)
            result = node.request({"op": "resolve", "requirements": ["^1.2.0", "~1.2", "1.2.1", "^3", "1.x || 2.x", "^1.3.0-beta.1"]})
            self.assertEqual([r["target_version"] for r in result], ["1.3.0+a", "1.2.1", "1.2.1", None, "2.0.0", "1.3.0+a"])
            self.assertEqual(result[3]["status"], "NO_SATISFYING_VERSION")

    def test_unsupported_specs_and_no_candidates(self):
        with self.session() as node:
            node.request({"op": "start", "name": "target"})
            values = ["latest", "npm:@scope/real@^1", "git+https://github.com/a/b.git", "file:../x", "https://example.invalid/a.tgz", None, "^1"]
            result = node.request({"op": "resolve", "requirements": values})
            self.assertEqual([r["status"] for r in result], ["UNSUPPORTED_TAG", "UNSUPPORTED_ALIAS", "UNSUPPORTED_GIT", "UNSUPPORTED_FILE", "UNSUPPORTED_URL", "INVALID_SPEC", "NO_ELIGIBLE_TARGET"])
            node.request({"op": "start", "name": "invalid name"})
            self.assertEqual(node.request({"op": "resolve", "requirements": ["*"]})[0]["status"], "INVALID_PACKAGE_NAME")

    def test_candidate_state_is_reset_per_target(self):
        with self.session() as node:
            node.request({"op": "start", "name": "a"})
            node.request({"op": "candidates", "versions": ["1.0.0"]})
            self.assertEqual(node.request({"op": "resolve", "requirements": ["*"]})[0]["target_version"], "1.0.0")
            node.request({"op": "start", "name": "b"})
            self.assertEqual(node.request({"op": "resolve", "requirements": ["*"]})[0]["status"], "NO_ELIGIBLE_TARGET")

    def test_broken_worker_and_bad_json_fail(self):
        for index, content in enumerate(["process.exit(9);", "process.stdout.write('not-json\\n');process.stdin.resume();"]):
            worker = self.root / f"bad-{index}.cjs"
            worker.write_text(content)
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                with NodeSession(self.runtime, self.root / f"bad-{index}.log", worker=worker, timeout=2) as node:
                    node.request({"op": "metadata"})

    def test_explicit_policies_and_no_cross_kind_collapse(self):
        policy = make_policy(kinds=["dependencies"], unknown_published_at="include", unresolved="partial", decision_reference="fixture")
        self.assertEqual(validate_policy(policy)["unknown_published_at"], "include")
        with self.assertRaises(ValueError):
            make_policy(kinds=["dependencies", "peerDependencies"], unknown_published_at="include", unresolved="partial", decision_reference="fixture")
        policy["document"]["unknown_published_at"] = "exclude"
        with self.assertRaises(ValueError):
            validate_policy(policy)

    def test_worker_protocol_error_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, "Start a target package first"):
            with self.session() as node:
                node.request({"op": "resolve", "requirements": ["*"]})

    def test_parquet_bridge_retains_distinct_lookups_and_typed_empty_quality(self):
        prepared = self.root / "prepared"
        for group in ("declarations", "candidates"):
            (prepared / group).mkdir(parents=True)
        with duckdb.connect() as con:
            con.execute("CREATE TABLE d(lookup_id VARCHAR,declared_name VARCHAR,requirement VARCHAR)")
            con.execute("INSERT INTO d VALUES ('a','target','^1'),('a','target','^1'),('b','absent','*'),('c',NULL,NULL)")
            con.execute("COPY d TO ? (FORMAT PARQUET)", [str(prepared / "declarations/part-0.parquet")])
            con.execute("CREATE TABLE c(name VARCHAR,version VARCHAR)")
            con.execute("INSERT INTO c VALUES ('target','1.1.0'),('target','1.2.0'),('unused','8.0.0')")
            con.execute("COPY c TO ? (FORMAT PARQUET)", [str(prepared / "candidates/part-0.parquet")])
        result = resolve_prepared(prepared, self.root / "bridge", self.runtime)
        self.assertEqual(result["lookups"], 3)
        with duckdb.connect() as con:
            rows = con.execute("SELECT lookup_id,status,target_version FROM read_parquet(?) ORDER BY lookup_id",
                               [str(self.root / "bridge/mappings/part-0.parquet")]).fetchall()
            self.assertEqual(rows, [("a", "RESOLVED", "1.2.0"), ("b", "NO_ELIGIBLE_TARGET", None), ("c", "INVALID_PACKAGE_NAME", None)])
            self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [str(self.root / "bridge/target_quality/part-0.parquet")]).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
