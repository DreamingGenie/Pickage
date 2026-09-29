"""Unittest coverage for the shared resource budget shell contract."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "preprocessing" / "runtime"
BUDGET = RUNTIME / "resource_budget.sh"


def _bash() -> str:
    candidates = [r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise unittest.SkipTest("Git Bash is required for shell contract tests")


def _run(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash(), "-c", script, "bash", *args],
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )


class ResourceBudgetTests(unittest.TestCase):
    def test_role_defaults_and_exact_sum_stay_within_495_gb(self) -> None:
        command = f"source {BUDGET.as_posix()!r}; for role in preprocess postgres loader; do printf '%s=%s\\n' \"$role\" \"$(bounded_budget_bytes \"$role\")\"; done"
        result = _run(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines())
        self.assertEqual(values, {"preprocess": "28000000000", "postgres": "17000000000", "loader": "4000000000"})
        self.assertEqual(sum(map(int, values.values())) + 500_000_000, 49_500_000_000)
        self.assertLessEqual(sum(map(int, values.values())) + 500_000_000, 50_000_000_000)

    def test_same_cap_boundary_and_small_test_cap_are_accepted(self) -> None:
        command = f"source {BUDGET.as_posix()!r}; bounded_budget_bytes preprocess 28000000000; bounded_budget_bytes loader 67108864"
        result = _run(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["28000000000", "67108864"])

    def test_invalid_and_over_cap_values_are_rejected(self) -> None:
        command = f"source {BUDGET.as_posix()!r}; for value in 0 -1 +1 01 1GB 1+1 28000000001 99999999999999999999999; do bounded_budget_bytes preprocess \"$value\" >/dev/null || continue; printf 'accepted:%s\\n' \"$value\"; exit 1; done"
        result = _run(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_unknown_role_is_rejected(self) -> None:
        result = _run(f"source {BUDGET.as_posix()!r}; bounded_budget_bytes unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown role", result.stderr)

    def test_wrappers_reject_invalid_size_before_root_or_filesystem_effects(self) -> None:
        for wrapper, variable in ((RUNTIME / "bounded_workspace.sh", "BOUNDED_WORKSPACE_BYTES"), (RUNTIME / "bounded_postgres.sh", "BOUNDED_POSTGRES_BYTES")):
            result = _run(f"bash {wrapper.as_posix()!r}", env={variable: "not-a-number"})
            self.assertNotEqual(result.returncode, 0, wrapper.name)
            self.assertIn("size must be between", result.stderr, wrapper.name)
            self.assertNotIn("supervisor must start as root", result.stderr, wrapper.name)
            self.assertNotIn("mkdir", result.stderr.lower(), wrapper.name)


if __name__ == "__main__":
    unittest.main()
