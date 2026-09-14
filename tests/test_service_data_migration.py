import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "service-data-migration" / "transfer.py"
SPEC = importlib.util.spec_from_file_location("service_data_transfer", MODULE_PATH)
transfer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(transfer)


class ServiceDataTransferTests(unittest.TestCase):
    def make_archive(self, root: Path) -> Path:
        archive = root / "archive"
        archive.mkdir()
        (archive / "toc.dat").write_bytes(b"archive")
        manifest = transfer.write_manifest(archive, source_db="source", jobs=4, compression="zstd:1")
        self.assertTrue(manifest.exists())
        return archive

    def test_manifest_round_trip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = self.make_archive(Path(raw))
            transfer.verify_manifest(archive)
            (archive / "toc.dat").write_bytes(b"tampered")
            with self.assertRaises(transfer.TransferError):
                transfer.verify_manifest(archive)

    def test_candidate_name_and_database_guards(self):
        args = type("Args", (), {"candidate_db": "pickage_import_341_run1", "source_db": "pickage", "service_db": "pickage"})()
        transfer.assert_candidate(args)
        args.candidate_db = "pickage"
        with self.assertRaises(transfer.TransferError):
            transfer.assert_candidate(args)
        args.candidate_db = "pickage_import_341_run1"
        args.source_db = args.candidate_db
        with self.assertRaises(transfer.TransferError):
            transfer.assert_candidate(args)
        args.source_db = "postgres://user:secret@example/db"
        with self.assertRaises(transfer.TransferError):
            transfer.assert_candidate(args)

    def test_malformed_and_duplicate_manifest_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = self.make_archive(Path(raw))
            path = transfer.manifest_path(archive)
            original = json.loads(path.read_text(encoding="utf-8"))
            cases = [[None], [original["files"][0], original["files"][0]],
                     [{"path": "../toc.dat", "size": 7, "sha256": "a" * 64}], []]
            for files in cases:
                with self.subTest(files=files):
                    changed = dict(original, files=files)
                    path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaises(transfer.TransferError):
                        transfer.verify_manifest(archive)

    def test_toc_rejects_unknown_table_and_schema(self):
        allowed = "\n".join([
            "1; 2615 2 SCHEMA - public postgres",
            "2; 2615 3 SCHEMA - vd193_reload_20260912_ready01 postgres",
            "3; 1259 2 TABLE public package postgres",
            "4; 1259 3 TABLE public version postgres",
            "5; 1259 4 TABLE public snapshot postgres",
            "6; 1259 5 TABLE public package_snapshot postgres",
            "7; 1259 6 TABLE public package_version_snapshot postgres",
            "8; 1259 7 TABLE DATA public package postgres",
            "9; 1259 8 TABLE DATA public version postgres",
            "10; 1259 9 TABLE DATA public snapshot postgres",
            "11; 1259 10 TABLE DATA public package_snapshot postgres",
            "12; 1259 11 TABLE vd193_reload_20260912_ready01 d20260831 postgres",
            "13; 1259 12 TABLE DATA vd193_reload_20260912_ready01 d20260831 postgres",
        ])
        transfer.expected_toc_lines(allowed)
        with self.assertRaises(transfer.TransferError):
            transfer.expected_toc_lines(allowed + "\n20; 1259 40 INDEX public idx_pvs_pkg_snapshot postgres")
        with self.assertRaises(transfer.TransferError):
            transfer.expected_toc_lines(allowed.replace("TABLE DATA public version", "TABLE DATA public package"))
        with self.assertRaises(transfer.TransferError):
            transfer.expected_toc_lines("1; 1259 2 TABLE public users postgres")
        with self.assertRaises(transfer.TransferError):
            transfer.expected_toc_lines("1; 2615 2 SCHEMA - private postgres")

    @patch.object(transfer, "run_checked")
    def test_dump_command_selects_roots_and_children(self, run_checked):
        run_checked.return_value = type("Result", (), {"stdout": "\n".join([
            "1; 2615 2 SCHEMA - public postgres",
            "2; 2615 3 SCHEMA - vd193_reload_20260912_ready01 postgres",
            "3; 1259 2 TABLE public package postgres",
            "4; 1259 3 TABLE public version postgres",
            "5; 1259 4 TABLE public snapshot postgres",
            "6; 1259 5 TABLE public package_snapshot postgres",
            "7; 1259 6 TABLE public package_version_snapshot postgres",
            "8; 1259 7 TABLE DATA public package postgres",
            "9; 1259 8 TABLE DATA public version postgres",
            "10; 1259 9 TABLE DATA public snapshot postgres",
            "11; 1259 10 TABLE DATA public package_snapshot postgres",
            "12; 1259 11 TABLE vd193_reload_20260912_ready01 d20260831 postgres",
            "13; 1259 12 TABLE DATA vd193_reload_20260912_ready01 d20260831 postgres",
        ])})()
        with tempfile.TemporaryDirectory() as raw:
            args = type("Args", (), {
                "source_db": "source", "archive_dir": Path(raw) / "archive", "jobs": 4,
                "compression": "zstd:1", "container": None, "container_archive_dir": None, "user": "postgres",
            })()
            transfer.dump_archive(args)
            command = run_checked.call_args_list[0].args[0]
            self.assertIn("--table=public.package", command)
            self.assertIn("--table-and-children=public.package_version_snapshot", command)


if __name__ == "__main__":
    unittest.main()
