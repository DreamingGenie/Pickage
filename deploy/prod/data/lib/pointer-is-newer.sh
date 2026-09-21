#!/bin/sh
#
# pointer-is-newer.sh — 완료 포인터의 run 문자열이 이전보다 최신인지 판정한다
#
# 형식: model=v<정수>/corpus=<문자열>
#
# 모델 버전은 **정수로** 비교한다 (v9 뒤에 v10 이 오면 문자열 비교로는
# '9' > '1' 이라 v10 이 더 오래된 것으로 오판된다 — S15P21A506-376).
# 모델 버전이 같으면 코퍼스 문자열을 사전식으로 비교한다 — 코퍼스 이름에
# 수집일이 들어가 있어 사전식 비교가 곧 시간순이다 (S15P21A506-348 관례).
#
# 사용: sh pointer-is-newer.sh <이전 run> <새 run>
#   이전 run 이 빈 문자열이면 첫 회차로 보고 항상 "최신"이다.
# 종료코드: 0 = 새 run 이 더 최신 / 1 = 아니오(같거나 과거) / 2 = 인자 오류
#
# run-similarity-batch.sh 와 이 파일의 테스트(test-pointer-is-newer.sh)가 함께 쓴다.
# 규칙을 바꿀 때는 여기만 고친다.

set -eu

if [ $# -ne 2 ]; then
  echo "사용: sh pointer-is-newer.sh <이전 run> <새 run>" >&2
  exit 2
fi

PREV="$1"
NEW="$2"

[ -z "$PREV" ] && exit 0   # 첫 회차 — 비교할 이전 값이 없다

extract_model() {
  printf '%s' "$1" | sed -n 's/^model=v\([0-9][0-9]*\)\/corpus=.*/\1/p'
}

PREV_MODEL=$(extract_model "$PREV")
NEW_MODEL=$(extract_model "$NEW")

if [ -z "$PREV_MODEL" ] || [ -z "$NEW_MODEL" ]; then
  # 형식을 못 읽으면 예전처럼 전체 문자열 비교로 물러선다.
  if [ "$NEW" \> "$PREV" ]; then exit 0; else exit 1; fi
fi

if [ "$NEW_MODEL" -gt "$PREV_MODEL" ]; then
  exit 0
elif [ "$NEW_MODEL" -lt "$PREV_MODEL" ]; then
  exit 1
fi

PREV_CORPUS=${PREV#*corpus=}
NEW_CORPUS=${NEW#*corpus=}
if [ "$NEW_CORPUS" \> "$PREV_CORPUS" ]; then
  exit 0
else
  exit 1
fi
