import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.snapshot.projects import _footer_sha256, inspect_projects


def _make(root: Path, snapshot: str, timestamp: str, *, rows: int = 2,
          manifest_rows: int | None = None, name: str = "part-000.parquet",
          column: str = "SnapshotAt", null: bool = False,
          timestamptz: bool = False) -> None:
    folder = root / f"snapshot={snapshot}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    con = duckdb.connect()
    try:
        if column == "SnapshotAt":
            if null:
                expr = "NULL::TIMESTAMP"
            elif timestamptz:
                expr = f"TIMESTAMPTZ '{timestamp}+00'"
            else:
                expr = f"TIMESTAMP '{timestamp}'"
        else:
            expr = "1::INTEGER"
        con.execute(f"CREATE TABLE fixture AS SELECT {expr} AS \"{column}\", range AS id FROM range(?)", [rows])
        con.execute("COPY fixture TO ? (FORMAT PARQUET, ROW_GROUP_SIZE 1)", [str(path)])
    finally:
        con.close()
    manifest = {"status": "done", "verify": "ok", "table": "projects",
                "snapshot": snapshot, "rows": rows if manifest_rows is None else manifest_rows}
    (folder / "_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")


class ProjectsInventoryTests(unittest.TestCase):
    def test_footer_hash_does_not_use_whole_file_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10")
            parquet = root / "snapshot=2026-08-31" / "part-000.parquet"
            reads = []
            original_open = Path.open

            def tracked_open(path, *args, **kwargs):
                stream = original_open(path, *args, **kwargs)
                original_read = stream.read

                def tracked_read(size=-1):
                    reads.append(size)
                    return original_read(size)

                stream.read = tracked_read
                return stream

            with patch.object(Path, "open", tracked_open):
                self.assertEqual(len(_footer_sha256(parquet)), 64)
            self.assertEqual(reads[0], 8)
            footer_length = int.from_bytes(parquet.read_bytes()[-8:-4], "little")
            self.assertEqual(reads[1], footer_length)

    def test_inventory_is_sorted_and_preserves_timestamp_and_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10.517131", rows=2)
            _make(root, "2026-08-24", "2026-08-24 21:01:10.517131", rows=1)
            result = inspect_projects(root)
            self.assertEqual(result["timestamps"], ["2026-08-24T21:01:10.517131Z", "2026-08-31T21:01:10.517131Z"])
            self.assertEqual(result["first_snapshot"], "2026-08-24")
            self.assertEqual(result["last_snapshot"], "2026-08-31")
            record = result["snapshots"][0]["files"][0]
            self.assertEqual(record["path"], "snapshot=2026-08-24/part-000.parquet")
            self.assertGreater(record["bytes"], 0)
            self.assertEqual(record["bytes"], record["post_stats"]["bytes"])
            self.assertEqual(len(record["parquet_footer_sha256"]), 64)

    def test_accepts_timestamptz_offset_and_maps_utc_date(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10.517131", timestamptz=True)
            result = inspect_projects(root)
            self.assertEqual(result["timestamps"], ["2026-08-31T21:01:10.517131Z"])

    def test_rejects_missing_manifest_and_invalid_partition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "snapshot=2026-08-31").mkdir()
            with self.assertRaises(ValueError):
                inspect_projects(root)
            (root / "snapshot=not-a-date").mkdir()
            with self.assertRaises(ValueError):
                inspect_projects(root)

    def test_rejects_null_mixed_time_partition_and_path_mismatch(self):
        cases = [("null", lambda r: _make(r, "2026-08-31", "2026-08-31 21:01:10", null=True)),
                 ("mismatch", lambda r: _make(r, "2026-08-31", "2026-09-01 21:01:10")),
                 ("count", lambda r: _make(r, "2026-08-31", "2026-08-31 21:01:10", manifest_rows=99))]
        for _, build in cases:
            with self.subTest(_= _), tempfile.TemporaryDirectory() as temp:
                build(Path(temp))
                with self.assertRaises(ValueError):
                    inspect_projects(Path(temp))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10", name="part-a.parquet")
            _make(root, "2026-08-31", "2026-08-31 22:01:10", name="part-b.parquet")
            with self.assertRaises(ValueError):
                inspect_projects(root)

    def test_rejects_missing_snapshot_at_and_invalid_part_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10", column="Other")
            with self.assertRaises(ValueError):
                inspect_projects(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make(root, "2026-08-31", "2026-08-31 21:01:10", name="data.parquet")
            with self.assertRaises(ValueError):
                inspect_projects(root)


if __name__ == "__main__":
    unittest.main()
