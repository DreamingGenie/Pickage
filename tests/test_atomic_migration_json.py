import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).parents[1] / "scripts" / "service-data-migration"
sys.path.insert(0, str(SCRIPT_DIR))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


transfer = load("transfer")
prepare = load("prepare_full_dump")


class AtomicMigrationJsonTests(unittest.TestCase):
    def test_replace_failure_keeps_previous_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "status.json"
            path.write_text('{"old": true}\n', encoding="utf-8")

            error = OSError(5, "access denied")
            error.winerror = 5
            with mock.patch.object(transfer.os, "name", "nt"), \
                 mock.patch.object(transfer.os, "replace", side_effect=error), \
                 mock.patch.object(transfer.time, "sleep"):
                with self.assertRaises(OSError):
                    transfer.write_json(path, {"new": True})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"old": true}\n')
            self.assertEqual(list(Path(raw).glob(".*.tmp")), [])

    def test_locked_progress_falls_back_without_aborting(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            status = root / "status.json"
            calls = []
            real_write = transfer.write_json

            def flaky_write(path, payload):
                calls.append(path)
                if path == status:
                    raise OSError(5, "access denied")
                return real_write(path, payload)

            with mock.patch.object(prepare.transfer, "write_json", side_effect=flaky_write):
                saved = prepare.save_progress_status(
                    status, {"status": "RUNNING"}, 0.0, root / "status-fallback"
                )

            self.assertFalse(saved)
            fallback = list((root / "status-fallback").glob("status-*.json"))
            self.assertEqual(len(fallback), 1)
            self.assertEqual(json.loads(fallback[0].read_text(encoding="utf-8"))["status"], "RUNNING")
            self.assertEqual(calls[0], status)

    @unittest.skipUnless(os.name == "nt", "Windows sharing-lock check")
    def test_windows_reader_without_delete_share_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "status.json"
            path.write_text('{"old": true}\n', encoding="utf-8")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel32.CreateFileW(
                str(path), 0xC0000000, 0x00000003, None, 3, 0x80, None
            )
            invalid = ctypes.c_void_p(-1).value
            self.assertNotEqual(handle, invalid)
            try:
                with self.assertRaises(OSError):
                    transfer.write_json(path, {"new": True})
            finally:
                kernel32.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
