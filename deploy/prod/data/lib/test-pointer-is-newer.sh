#!/bin/sh
#
# test-pointer-is-newer.sh — pointer-is-newer.sh 의 최신성 판정을 검증한다
#
# 사용: sh test-pointer-is-newer.sh
# 종료코드: 0 모두 통과 / 1 하나 이상 실패

set -eu
cd "$(dirname "$0")"

FAIL=0

check() {
  # $1=설명 $2=이전run $3=새run $4=기대 종료코드(0=최신/1=아님)
  desc="$1"; prev="$2"; new="$3"; expect="$4"
  set +e
  sh ./pointer-is-newer.sh "$prev" "$new"
  actual=$?
  set -e
  if [ "$actual" -ne "$expect" ]; then
    echo "FAIL: $desc (기대 exit=$expect, 실제 exit=$actual)" >&2
    FAIL=1
  else
    echo "ok: $desc"
  fi
}

check "첫 회차 — 이전 포인터 없음" \
  "" "model=v1/corpus=collected_date=2026-09-01" 0

check "같은 모델, 코퍼스만 최신" \
  "model=v9/corpus=collected_date=2026-09-01" "model=v9/corpus=collected_date=2026-09-10" 0

check "같은 모델, 코퍼스가 과거" \
  "model=v9/corpus=collected_date=2026-09-10" "model=v9/corpus=collected_date=2026-09-01" 1

check "모델 버전 v9 -> v10 (자릿수 증가, 최신으로 판정돼야 함)" \
  "model=v9/corpus=collected_date=2026-09-01" "model=v10/corpus=collected_date=2026-09-01" 0

check "모델 버전 v10 -> v9 (되돌림, 거부)" \
  "model=v10/corpus=collected_date=2026-09-01" "model=v9/corpus=collected_date=2026-09-01" 1

check "완전히 동일한 run (거부)" \
  "model=v9/corpus=collected_date=2026-09-01" "model=v9/corpus=collected_date=2026-09-01" 1

if [ "$FAIL" -ne 0 ]; then
  echo "일부 테스트 실패" >&2
  exit 1
fi
echo "모두 통과"
