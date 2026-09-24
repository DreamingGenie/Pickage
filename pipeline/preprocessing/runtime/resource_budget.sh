#!/usr/bin/env bash
# One preprocessing volume, one DB processing volume, and one loader volume.
# Their physical caps can coexist: 28 + 17 + 4 + 0.5 GB = 49.5 GB.
# The 0.5 GB reserve covers bounded logs/metadata, not another worker volume.
bounded_budget_bytes() {
  local role=$1 requested=${2:-} maximum
  case "$role" in
    preprocess) maximum=28000000000 ;;
    postgres) maximum=17000000000 ;;
    loader) maximum=4000000000 ;;
    *) echo 'bounded-budget: unknown role' >&2; return 2 ;;
  esac
  requested=${requested:-$maximum}
  # Reject signs, leading zeros and arithmetic overflow before bash arithmetic.
  if [[ ! "$requested" =~ ^[1-9][0-9]{0,10}$ ]] || (( requested > maximum )); then
    echo "bounded-budget: $role size must be between 1 and $maximum bytes" >&2
    return 2
  fi
  printf '%s\n' "$requested"
}
