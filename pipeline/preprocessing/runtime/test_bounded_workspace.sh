#!/usr/bin/env bash
set -Eeuo pipefail

script="$(dirname "$0")/bounded_workspace.sh"
bash -n "$script"
grep -q '^IMAGE=/var/lib/pickage-bounded/scratch.ext4$' "$script"
bash "$(dirname "$0")/test_resource_budget.sh"
grep -q -- '--no-new-privs' "$script"
grep -q 'findmnt -rn -M' "$script"
grep -q 'unmarked nonempty dedicated volume' "$script"
grep -q 'mounted filesystem is not ext4' "$script"
echo 'bounded workspace contract checks passed'

if ! command -v docker >/dev/null 2>&1 || [ "$(docker info --format '{{.OSType}}' 2>/dev/null || true)" != linux ]; then
  echo 'dynamic Docker checks skipped: Linux Docker engine unavailable'
  exit 0
fi

python3 "$(dirname "$0")/test_budget_runtime.py"
