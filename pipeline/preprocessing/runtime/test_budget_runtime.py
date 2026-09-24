"""Dynamic Docker tests for the bounded workspace supervisor.

These tests use only a uniquely labeled volume and container, and never touch
the repository's application containers or persistent volumes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


IMAGE = "sha256:53f6310b82eb03a05c71c8ebfbc22dc603ce82aeef56a5fcdea0052fdb06cff2"
RUNTIME = Path(__file__).resolve().parent
class BudgetRuntimeFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI is unavailable")
        info = subprocess.run(["docker", "info", "--format", "{{.OSType}}"], text=True, capture_output=True, check=False)
        if info.returncode != 0 or info.stdout.strip() != "linux":
            raise unittest.SkipTest("A Linux Docker engine is required")
        image = subprocess.run(["docker", "image", "inspect", IMAGE], text=True, capture_output=True, check=False)
        if image.returncode != 0:
            raise unittest.SkipTest("the pinned bounded runtime image is not available")

    def setUp(self) -> None:
        token = uuid.uuid4().hex
        self.label_key = "com.pickage.budget-fixture"
        self.label_value = token
        self.volume = f"pickage-budget-fixture-{token}"
        self.container = f"pickage-budget-fixture-{token}"
        self._docker(["volume", "create", "--label", f"{self.label_key}={self.label_value}", self.volume], check=True)

    def tearDown(self) -> None:
        self._remove_owned_container()
        inspect = self._docker(["volume", "inspect", self.volume], check=False)
        if inspect.returncode == 0:
            labels = json.loads(inspect.stdout)[0].get("Labels") or {}
            if labels.get(self.label_key) == self.label_value:
                self._docker(["volume", "rm", self.volume], check=False)

    def _docker(self, args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)

    def _remove_owned_container(self) -> None:
        inspect = self._docker(["container", "inspect", self.container], check=False)
        if inspect.returncode != 0:
            return
        labels = json.loads(inspect.stdout)[0].get("Config", {}).get("Labels") or {}
        if labels.get(self.label_key) == self.label_value:
            self._docker(["rm", "-f", self.container], check=False)

    def _run_supervisor(self, command: str, *, runtime_dir: Path = RUNTIME, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        host_runtime = str(runtime_dir).replace("\\", "/")
        args = [
            "run", "--name", self.container,
            "--label", f"{self.label_key}={self.label_value}",
            "--privileged", "--read-only", "--tmpfs", "/tmp:size=64m", "--tmpfs", "/run:size=16m",
            "--memory=256m", "--memory-swap=256m", "-e", "BOUNDED_TEST_MODE=1", "-e", "BOUNDED_TEST_SIZE_BYTES=67108864",
            *sum((["-e", f"{key}={value}"] for key, value in (env or {}).items()), []),
            "-v", f"{self.volume}:/var/lib/pickage-bounded", "-v", f"{host_runtime}:/source:ro",
            "--entrypoint", "bash", IMAGE, "-c", "source /source/bounded_workspace.sh \"$@\"", "bash", "sh", "-c", command,
        ]
        return self._docker(args, check=False)

    def _volume_listing(self) -> str:
        result = self._docker([
            "run", "--rm", "-v", f"{self.volume}:/var/lib/pickage-bounded:ro",
            "--entrypoint", "sh", IMAGE, "-c",
            "find /var/lib/pickage-bounded -mindepth 1 -maxdepth 1 -printf '%f\\n' | sort",
        ], check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_uid_enospc_cleanup_and_marker_guard(self) -> None:
        result = self._run_supervisor('test "$(id -u)" = 1000 && dd if=/dev/zero of="$BOUNDED_WORKSPACE/fill" bs=1M count=96 status=none')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No space left", result.stderr)
        image_check = self._docker(["run", "--rm", "-v", f"{self.volume}:/var/lib/pickage-bounded:ro", "--entrypoint", "sh", IMAGE, "-c", "test ! -e /var/lib/pickage-bounded/scratch.ext4"], check=False)
        self.assertEqual(image_check.returncode, 0, image_check.stderr)
        marker = self._docker(["run", "--rm", "-v", f"{self.volume}:/var/lib/pickage-bounded", "--entrypoint", "sh", IMAGE, "-c", "printf wrong > /var/lib/pickage-bounded/OWNER_UUID"], check=False)
        self.assertEqual(marker.returncode, 0, marker.stderr)
        self._remove_owned_container()
        guarded = self._run_supervisor("true")
        self.assertNotEqual(guarded.returncode, 0)
        self.assertIn("marker mismatch", guarded.stderr)

    def test_loader_role_file_wins_over_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            for name in ("bounded_workspace.sh", "resource_budget.sh"):
                shutil.copy2(RUNTIME / name, runtime / name)
            (runtime / "workspace.role").write_bytes(b"loader\n")
            result = self._run_supervisor('test "$(id -u)" = 1000 && test "$BOUNDED_SCRATCH_LIMIT_BYTES" = 67108864', runtime_dir=runtime, env={"BOUNDED_WORKSPACE_ROLE": "preprocess"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loader_role_rejects_over_cap_before_volume_effect(self) -> None:
        before = self._volume_listing()
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            for name in ("bounded_workspace.sh", "resource_budget.sh"):
                shutil.copy2(RUNTIME / name, runtime / name)
            (runtime / "workspace.role").write_bytes(b"loader\n")
            result = self._run_supervisor(
                "true",
                runtime_dir=runtime,
                env={"BOUNDED_WORKSPACE_ROLE": "preprocess", "BOUNDED_TEST_SIZE_BYTES": "4000000001"},
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("size must be between 1 and 4000000000 bytes", result.stderr)
        self._remove_owned_container()
        self.assertEqual(self._volume_listing(), before)


if __name__ == "__main__":
    unittest.main()
