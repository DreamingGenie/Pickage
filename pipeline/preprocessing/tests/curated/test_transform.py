import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import duckdb

from pipeline.preprocessing.curated.transform import ValidationError, transform


SNAPSHOT = "2026-08-31"
SNAPSHOT_TS = datetime(2026, 8, 31, 21, 1, 10)
_MISSING = object()


def _write_parquet(root, name, schema, rows):
    path = Path(root) / f"{name}.parquet"
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE input ({schema})")
        if rows:
            placeholders = ",".join("?" for _ in rows[0])
            con.executemany(f"INSERT INTO input VALUES ({placeholders})", rows)
        con.execute(f"COPY input TO '{path.as_posix()}' (FORMAT PARQUET)")
    finally:
        con.close()
    return path


def _version_file(root, rows):
    return _write_parquet(
        root,
        "versions",
        "Name VARCHAR, Version VARCHAR, published_at TIMESTAMP, is_release BOOLEAN, "
        "ordinal BIGINT, Description VARCHAR, Licenses VARCHAR[], Deprecated VARCHAR, "
        "source_repo VARCHAR, SnapshotAt TIMESTAMP",
        rows,
    )


def _requirements_file(root, rows):
    return _write_parquet(
        root,
        "requirements",
        "Name VARCHAR, Version VARCHAR, Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], "
        "PeerDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], "
        "OptionalDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], SnapshotAt TIMESTAMP",
        rows,
    )


def _version(
    name,
    version,
    ordinal,
    *,
    published_at=SNAPSHOT_TS,
    is_release=True,
    repo=None,
):
    return (
        name,
        version,
        published_at,
        is_release,
        ordinal,
        f"description for {name}@{version}",
        ["MIT"],
        None,
        repo,
        SNAPSHOT_TS,
    )


def _requirement(name, version, *, dependencies=_MISSING, peers=_MISSING, optional=_MISSING, snapshot=SNAPSHOT_TS):
    def array_or_empty(value):
        return [] if value is _MISSING else value

    return (name, version, array_or_empty(dependencies), array_or_empty(peers), array_or_empty(optional), snapshot)


class TransformParquetTests(unittest.TestCase):
    def test_nul_description_is_null_without_removing_version(self):
        row = list(_version('nul-description','1.0.0',1))
        row[5] = 'before\x00after'
        temp,con,output,report = self.run_transform([tuple(row)],[_requirement('nul-description','1.0.0')])
        try:
            values = self.read_rows(con,output,'version/data')
            self.assertEqual(len(values),1)
            self.assertIsNone(values[0][4])
            self.assertEqual(report['nul_descriptions'],1)
            self.assertEqual(self.read_rows(con,output,'quality/metadata_issues'),
                             [('nul-description','1.0.0','description','NUL_IN_DESCRIPTION')])
        finally:
            con.close()
            temp.cleanup()

    def run_transform(self, versions, requirements, previous_ids=None, snapshot=SNAPSHOT):
        temp = tempfile.TemporaryDirectory()
        versions_path = _version_file(temp.name, versions)
        requirements_path = _requirements_file(temp.name, requirements)
        old_path = None
        if previous_ids is not None:
            old_path = _write_parquet(
                temp.name,
                "previous_ids",
                "package_id INTEGER, name VARCHAR",
                previous_ids,
            )
        output = Path(temp.name) / "output"
        con = duckdb.connect()
        try:
            report = transform(
                con,
                [versions_path],
                [requirements_path],
                [old_path] if old_path else None,
                snapshot,
                output,
            )
        except Exception:
            con.close()
            temp.cleanup()
            raise
        return temp, con, output, report

    def read_rows(self, con, output, relation):
        return con.execute(
            f"SELECT * FROM read_parquet('{(output / relation / '*.parquet').as_posix()}', hive_partitioning=false)"
        ).fetchall()

    def test_filters_release_future_and_null_or_equal_published_at(self):
        versions = [
            _version("eligible", "1.0.0", 1),
            _version("null-date", "1.0.0", 1, published_at=None),
            _version("future", "1.0.0", 1, published_at=datetime(2026, 9, 1)),
            _version("nonrelease", "1.0.0", 1, is_release=False),
            _version("unknown", "1.0.0", 1, is_release=None),
        ]
        requirements = [
            _requirement("eligible", "1.0.0"),
            _requirement("null-date", "1.0.0"),
            _requirement("future", "1.0.0"),
            _requirement("nonrelease", "1.0.0"),
            _requirement("unknown", "1.0.0"),
        ]
        temp, con, output, report = self.run_transform(versions, requirements)
        try:
            self.assertEqual(report["input_versions"], 5)
            self.assertEqual(report["release_versions"], 3)
            self.assertEqual(report["nonrelease_versions"], 1)
            self.assertEqual(report["unknown_release_versions"], 1)
            self.assertEqual(report["excluded_future_versions"], 1)
            self.assertEqual(report["versions"], 2)
            names = {row[1] for row in self.read_rows(con, output, "package/data")}
            self.assertEqual(names, {"eligible", "null-date"})
            excluded = self.read_rows(con, output, "quality/excluded_versions")
            self.assertEqual(len(excluded), 1)
            self.assertEqual(excluded[0][-1], "PUBLISHED_AFTER_SNAPSHOT")
        finally:
            con.close()
            temp.cleanup()

    def test_repository_fallback_uses_eligible_ordinal_not_publish_time(self):
        versions = [
            _version("fallback", "3.0.0", 3, published_at=datetime(2026, 8, 1), repo=None),
            _version("fallback", "2.0.0", 2, published_at=datetime(2026, 7, 1), repo="git+https://github.com/a/old.git"),
            _version("fallback", "4.0.0", 4, published_at=datetime(2026, 9, 1), repo="https://gitlab.com/a/future.git"),
            _version("ordinal-wins", "1.0.0", 1, published_at=datetime(2026, 8, 30), repo="https://github.com/a/older.git"),
            _version("ordinal-wins", "2.0.0", 2, published_at=datetime(2026, 8, 1), repo="https://github.com/a/newer.git"),
        ]
        requirements = [_requirement(name, version) for name, version, *_ in versions]
        temp, con, output, _ = self.run_transform(versions, requirements)
        try:
            rows = self.read_rows(con, output, "package/data")
            by_name = {row[1]: row[2] for row in rows}
            self.assertEqual(by_name["fallback"], "https://github.com/a/old")
            self.assertEqual(by_name["ordinal-wins"], "https://github.com/a/newer")
        finally:
            con.close()
            temp.cleanup()

    def test_package_ids_remain_stable_for_new_earlier_and_reappearing_names(self):
        base = [_version("b", "1.0.0", 1), _version("c", "1.0.0", 1)]
        req = [_requirement("b", "1.0.0"), _requirement("c", "1.0.0")]
        temp1, con1, out1, _ = self.run_transform(base, req)
        try:
            ids = self.read_rows(con1, out1, "package_ids/data")
        finally:
            con1.close()
            temp1.cleanup()

        second = [_version("a", "1.0.0", 1), _version("b", "1.0.0", 1)]
        req2 = [_requirement("a", "1.0.0"), _requirement("b", "1.0.0")]
        temp2, con2, out2, _ = self.run_transform(second, req2, ids)
        try:
            second_ids = {row[1]: row[0] for row in self.read_rows(con2, out2, "package_ids/data")}
            self.assertEqual(second_ids, {"a": 3, "b": 1, "c": 2})
        finally:
            con2.close()
            temp2.cleanup()

        third = [_version("c", "2.0.0", 2)]
        temp3, con3, out3, _ = self.run_transform(third, req2[:0] + [_requirement("c", "2.0.0")], ids)
        try:
            third_ids = {row[1]: row[0] for row in self.read_rows(con3, out3, "package_ids/data")}
            self.assertEqual(third_ids, {"b": 1, "c": 2})
        finally:
            con3.close()
            temp3.cleanup()

    def test_dependency_json_distinguishes_missing_empty_duplicate_and_conflict(self):
        versions = [
            _version("empty", "1.0.0", 1),
            _version("missing", "1.0.0", 1),
            _version("duplicate", "1.0.0", 1),
            _version("conflict", "1.0.0", 1),
            _version("null-dep", "1.0.0", 1),
        ]
        dep = [{"Name": "dep", "Requirement": "^1"}]
        requirements = [
            _requirement("empty", "1.0.0"),
            _requirement("duplicate", "1.0.0", dependencies=dep + dep),
            _requirement("conflict", "1.0.0", dependencies=dep + [{"Name": "dep", "Requirement": "^2"}]),
            _requirement("null-dep", "1.0.0", dependencies=[{"Name": "dep", "Requirement": None}]),
        ]
        temp, con, output, report = self.run_transform(versions, requirements)
        try:
            self.assertEqual(report["missing_requirements"], 1)
            self.assertEqual(report["invalid_requirements"], 2)
            rows = con.execute(
                f"SELECT p.name,v.dependency FROM read_parquet('{(output / 'version/data' / '*.parquet').as_posix()}') v "
                f"JOIN read_parquet('{(output / 'package/data' / '*.parquet').as_posix()}') p USING (package_id)"
            ).fetchall()
            dependencies = dict(rows)
            self.assertEqual(dependencies["empty"], '{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}')
            self.assertIsNone(dependencies["missing"])
            self.assertIn('"dep":"^1"', dependencies["duplicate"])
            self.assertIsNone(dependencies["conflict"])
            self.assertIsNone(dependencies["null-dep"])
        finally:
            con.close()
            temp.cleanup()

    def test_output_schema_excludes_is_release(self):
        temp, con, output, _ = self.run_transform(
            [_version("pkg", "1.0.0", 1)], [_requirement("pkg", "1.0.0")]
        )
        try:
            columns = [row[0] for row in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{(output / 'version/data' / '*.parquet').as_posix()}')"
            ).fetchall()]
            self.assertNotIn("is_release", columns)
            self.assertEqual(columns, ["version", "package_id", "published_at", "ordinal", "description", "licenses", "deprecated", "dependency"])
        finally:
            con.close()
            temp.cleanup()

    def test_null_dependency_arrays_and_elements_are_invalid(self):
        versions = [
            _version("null-array", "1.0.0", 1),
            _version("null-element", "1.0.0", 1),
        ]
        requirements = [
            _requirement("null-array", "1.0.0", dependencies=None),
            _requirement("null-element", "1.0.0", dependencies=[None]),
        ]
        temp, con, output, report = self.run_transform(versions, requirements)
        try:
            self.assertEqual(report["invalid_requirements"], 2)
            dependencies = con.execute(
                f"SELECT p.name,v.dependency FROM read_parquet('{(output / 'version/data' / '*.parquet').as_posix()}') v "
                f"JOIN read_parquet('{(output / 'package/data' / '*.parquet').as_posix()}') p USING (package_id)"
            ).fetchall()
            self.assertEqual(dependencies, [("null-array", None), ("null-element", None)])
        finally:
            con.close()
            temp.cleanup()

    def test_duplicate_requirements_rows_are_rejected(self):
        versions = [_version("pkg", "1.0.0", 1)]
        requirements = [
            _requirement("pkg", "1.0.0"),
            _requirement("pkg", "1.0.0"),
        ]
        self.assert_transform_error(versions, requirements, message="Duplicate requirements keys")

    def test_ordinal_ties_have_deterministic_published_and_version_tiebreakers(self):
        versions = [
            _version("published-tie", "1.0.0", 5, published_at=datetime(2026, 8, 1), repo="https://github.com/a/old"),
            _version("published-tie", "2.0.0", 5, published_at=datetime(2026, 8, 2), repo="https://github.com/a/new"),
            _version("version-tie", "2.0.0", 7, published_at=datetime(2026, 8, 2), repo="https://github.com/a/high"),
            _version("version-tie", "1.0.0", 7, published_at=datetime(2026, 8, 2), repo="https://github.com/a/low"),
        ]
        requirements = [_requirement(row[0], row[1]) for row in versions]
        temp, con, output, report = self.run_transform(versions, requirements)
        try:
            self.assertEqual(report["ordinal_tie_groups"], 2)
            rows = self.read_rows(con, output, "package/data")
            by_name = {row[1]: row[2] for row in rows}
            self.assertEqual(by_name["published-tie"], "https://github.com/a/new")
            self.assertEqual(by_name["version-tie"], "https://github.com/a/low")
        finally:
            con.close()
            temp.cleanup()

    def test_null_and_negative_ordinal_are_rejected(self):
        for ordinal in (None, -1):
            with self.subTest(ordinal=ordinal):
                self.assert_transform_error(
                    [_version("pkg", "1.0.0", ordinal)],
                    [_requirement("pkg", "1.0.0")],
                    message="Version required fields/lengths",
                )

    def test_rejects_duplicate_keys_snapshot_mismatch_invalid_mapping_and_int_overflow(self):
        duplicate = [_version("pkg", "1.0.0", 1), _version("pkg", "1.0.0", 2)]
        self.assert_transform_error(duplicate, [_requirement("pkg", "1.0.0")], message="Duplicate version keys")

        mismatch = [_requirement("pkg", "1.0.0", snapshot=datetime(2026, 8, 30))]
        self.assert_transform_error([_version("pkg", "1.0.0", 1)], mismatch, message="snapshot mismatch")

        invalid_ids = [(1, "pkg"), (1, "other")]
        self.assert_transform_error(
            [_version("pkg", "1.0.0", 1)],
            [_requirement("pkg", "1.0.0")],
            previous_ids=invalid_ids,
            message="Duplicate existing package ID mapping",
        )

        overflow_ids = [(2147483647, "old")]
        self.assert_transform_error(
            [_version("new", "1.0.0", 1)],
            [_requirement("new", "1.0.0")],
            previous_ids=overflow_ids,
            message="package_id exceeds PostgreSQL INT capacity",
        )

    def assert_transform_error(self, versions, requirements, previous_ids=None, message=None):
        with self.assertRaises(ValidationError) as raised:
            temp, con, _, _ = self.run_transform(versions, requirements, previous_ids)
            con.close()
            temp.cleanup()
        if message:
            self.assertIn(message, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
