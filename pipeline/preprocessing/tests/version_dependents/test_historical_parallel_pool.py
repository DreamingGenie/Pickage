"""Windows process-tree tests for the parallel worker pool."""
import os
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from pipeline.preprocessing.version_dependents.historical_parallel_pool import Pool


def _wait_until(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.05)
    return False


def _alive(pid):
    if not pid:
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    try:
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def _init_child(record):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    Path(record).write_text(str(child.pid), encoding="ascii")
    return child


def _handler(task, context):
    if task == "error":
        raise RuntimeError("expected handler failure")
    return {"pid": os.getpid(), "task": task}


def _coordinator_entry(record, ready):
    with Pool(1, _handler, initializer=_init_child, initargs=(record,)) as pool:
        while not pool.idle:
            pool.events(.1)
        Path(ready).write_text(f"{os.getpid()}\n{pool.slots[0]['process'].pid}", encoding="ascii")
        try:
            while True:
                pool.events(.2)
        finally:
            pool.close()


@unittest.skipUnless(os.name == "nt", "Windows Job Object tests")
class ParallelPoolTests(unittest.TestCase):
    def _ready(self, pool):
        return _wait_until(lambda: len(pool.idle) == pool.size or bool(pool.events(.05)) and len(pool.idle) == pool.size)

    def test_two_workers_have_distinct_pids_and_reuse_same_worker(self):
        with Pool(2, _handler) as pool:
            self.assertTrue(self._ready(pool))
            pids = {pool.slots[i]["process"].pid for i in pool.idle}
            self.assertEqual(len(pids), 2)
            for slot in sorted(pool.idle):
                pool.submit(slot, "first")
            events = []
            while len(events) < 2:
                events.extend(e for e in pool.events(.2) if e["kind"] == "RESULT")
            original = {e["slot"]: e["value"]["pid"] for e in events}
            for slot in original:
                pool.submit(slot, "second")
            events = []
            while len(events) < 2:
                events.extend(e for e in pool.events(.2) if e["kind"] == "RESULT")
            self.assertEqual({e["slot"]: e["value"]["pid"] for e in events}, original)

    def test_handler_error_does_not_kill_worker_and_replace_recovers(self):
        with Pool(1, _handler) as pool:
            self.assertTrue(self._ready(pool)); slot = pool.idle[0]
            pool.submit(slot, "error")
            error = next(e for e in pool.events(2) if e["kind"] == "ERROR")
            self.assertEqual(error["error_type"], "RuntimeError")
            pid = pool.slots[slot]["process"].pid
            self.assertIn(slot, pool.idle)
            pool.replace(slot)
            self.assertTrue(self._ready(pool))
            self.assertNotEqual(pool.slots[slot]["process"].pid, pid)

    def test_worker_death_kills_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            record = str(Path(directory) / "grandchild.pid")
            with Pool(1, _handler, initializer=_init_child, initargs=(record,)) as pool:
                self.assertTrue(self._ready(pool))
                self.assertTrue(_wait_until(lambda: Path(record).exists()))
                grandchild = int(Path(record).read_text(encoding="ascii"))
                proc = pool.slots[0]["process"]
                proc.terminate(); proc.join(5)
                self.assertTrue(_wait_until(lambda: any(e["kind"] == "DEAD" for e in pool.events(.1))))
                self.assertTrue(_wait_until(lambda: not _alive(grandchild)))

    def test_coordinator_death_kills_worker_and_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            record = str(Path(directory) / "grandchild.pid"); ready = str(Path(directory) / "ready")
            import multiprocessing as mp
            coordinator = mp.get_context("spawn").Process(target=_coordinator_entry, args=(record, ready))
            coordinator.start()
            self.assertTrue(_wait_until(lambda: Path(ready).exists()))
            self.assertTrue(_wait_until(lambda: Path(record).exists()))
            grandchild = int(Path(record).read_text(encoding="ascii"))
            coordinator_pid, worker_pid = map(int, Path(ready).read_text(encoding="ascii").splitlines())
            coordinator.terminate(); coordinator.join(5)
            self.assertFalse(_alive(coordinator_pid))
            self.assertTrue(_wait_until(lambda: not _alive(worker_pid)))
            self.assertTrue(_wait_until(lambda: not _alive(grandchild)))


def _posix_alive(pid):
    if not pid:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        # The state is the first field after the command name. A zombie has
        # exited already even though kill(pid, 0) still succeeds until reaped.
        state = stat.rsplit(")", 1)[1].split()[0]
        if state == "Z":
            return False
    except (FileNotFoundError, PermissionError, OSError):
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _posix_init_child(record):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    Path(record).write_text(str(child.pid), encoding="ascii")
    return child


def _posix_coordinator_entry(record, ready):
    with Pool(1, _handler, initializer=_posix_init_child, initargs=(record,)) as pool:
        while not pool.idle:
            pool.events(.1)
        Path(ready).write_text(f"{os.getpid()}\n{pool.slots[0]['process'].pid}", encoding="ascii")
        while True:
            pool.events(.2)


@unittest.skipUnless(os.name != "nt", "POSIX process-group tests")
class PosixParallelPoolTests(unittest.TestCase):
    def _ready(self, pool):
        return _wait_until(lambda: len(pool.idle) == pool.size or bool(pool.events(.05)) and len(pool.idle) == pool.size)

    def test_worker_group_shutdown_kills_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            record = str(Path(directory) / "grandchild.pid")
            with Pool(1, _handler, initializer=_posix_init_child, initargs=(record,)) as pool:
                self.assertTrue(self._ready(pool))
                self.assertTrue(_wait_until(lambda: Path(record).exists()))
                grandchild = int(Path(record).read_text(encoding="ascii"))
                worker = pool.slots[0]["process"]
                worker.terminate(); worker.join(5)
                self.assertTrue(_wait_until(lambda: any(e["kind"] == "DEAD" for e in pool.events(.1))))
                self.assertTrue(_wait_until(lambda: not _posix_alive(grandchild)))

    def test_pool_close_keeps_coordinator_alive_after_success_and_error(self):
        with Pool(1, _handler) as pool:
            self.assertTrue(self._ready(pool))
            pool.submit(pool.idle[0], "ok")
            self.assertTrue(any(event["kind"] == "RESULT" for event in pool.events(2)))
        self.assertTrue(_posix_alive(os.getpid()))

        with Pool(1, _handler) as pool:
            self.assertTrue(self._ready(pool))
            pool.submit(pool.idle[0], "error")
            self.assertTrue(any(event["kind"] == "ERROR" for event in pool.events(2)))
        self.assertTrue(_posix_alive(os.getpid()))

    def test_coordinator_death_kills_worker_and_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            record = str(Path(directory) / "grandchild.pid"); ready = str(Path(directory) / "ready")
            import multiprocessing as mp
            coordinator = mp.get_context("spawn").Process(target=_posix_coordinator_entry, args=(record, ready))
            coordinator.start()
            self.assertTrue(_wait_until(lambda: Path(ready).exists()))
            self.assertTrue(_wait_until(lambda: Path(record).exists()))
            grandchild = int(Path(record).read_text(encoding="ascii"))
            coordinator_pid, worker_pid = map(int, Path(ready).read_text(encoding="ascii").splitlines())
            coordinator.terminate(); coordinator.join(5)
            self.assertFalse(_posix_alive(coordinator_pid))
            self.assertTrue(_wait_until(lambda: not _posix_alive(worker_pid)))
            self.assertTrue(_wait_until(lambda: not _posix_alive(grandchild)))


if __name__ == "__main__":
    unittest.main()
