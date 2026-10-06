#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/resource_budget.sh"
[[ $(bounded_budget_bytes preprocess) = 28000000000 ]]
[[ $(bounded_budget_bytes postgres) = 17000000000 ]]
[[ $(bounded_budget_bytes loader) = 4000000000 ]]
(( $(bounded_budget_bytes preprocess) + $(bounded_budget_bytes postgres) + $(bounded_budget_bytes loader) + 500000000 <= 50000000000 ))
for role in preprocess postgres loader; do
  maximum=$(bounded_budget_bytes "$role")
  [[ $(bounded_budget_bytes "$role" "$maximum") = "$maximum" ]]
  [[ $(bounded_budget_bytes "$role" 67108864) = 67108864 ]]
  for invalid in 0 -1 +1 01 '1GB' '1+1' 99999999999999999999999 "$((maximum+1))"; do
    if bounded_budget_bytes "$role" "$invalid" >/dev/null 2>&1; then
      echo "unexpected accepted limit: $role $invalid" >&2; exit 1
    fi
  done
done
if bounded_budget_bytes unknown >/dev/null 2>&1; then exit 1; fi
echo 'resource budget: defaults, sum, role limits and malformed values PASS'
