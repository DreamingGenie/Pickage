#!/bin/sh
#
# check-branch-name.sh — 브랜치 이름 규칙 검사
#
# 규칙: <part>/<type>/<S15P21A506-번호>-작업내용
#   예) data/feat/S15P21A506-290-downloads-bronze-ingest
#
# 사용: sh scripts/lib/check-branch-name.sh <브랜치명>
# 종료코드: 0 통과 / 1 위반(사유는 stderr) / 2 인자 오류
#
# 이 파일이 규칙의 단일 구현이다. .githooks/pre-push 와 scripts/new-branch.sh 가
# 함께 쓰므로, 규칙을 바꿀 때는 여기만 고친다.

PROJECT_KEY="S15P21A506"
PARTS="frontend api data ai worker infra docs plan"
TYPES="feat fix refactor test chore docs style config"

BRANCH="$1"

if [ -z "$BRANCH" ]; then
  echo "사용법: sh scripts/lib/check-branch-name.sh <브랜치명>" >&2
  exit 2
fi

# 목록을 grep -E 용 대안 패턴으로 바꾼다 (frontend|api|...)
alt() {
  printf '%s' "$1" | tr ' ' '|'
}
PART_ALT=$(alt "$PARTS")
TYPE_ALT=$(alt "$TYPES")
KEY_RE="${PROJECT_KEY}-[0-9][0-9]*"

FULL_RE="^(${PART_ALT})/(${TYPE_ALT})/${KEY_RE}-[a-z0-9][a-z0-9-]*$"

if printf '%s' "$BRANCH" | grep -qE "$FULL_RE"; then
  exit 0
fi

# --- 여기부터는 위반. 어디가 틀렸는지 짚어 준다 -------------------------------
echo "" >&2
echo "브랜치명이 팀 규칙과 다릅니다." >&2
echo "" >&2
echo "  현재: $BRANCH" >&2
echo "  규칙: <part>/<type>/<${PROJECT_KEY}-번호>-작업내용" >&2
echo "  예시: data/feat/${PROJECT_KEY}-290-downloads-bronze-ingest" >&2
echo "" >&2

FIELD1=$(printf '%s' "$BRANCH" | cut -d/ -f1)
SLASHES=$(printf '%s' "$BRANCH" | tr -cd '/' | wc -c | tr -d ' ')

if [ "$SLASHES" -lt 2 ]; then
  echo "  · 슬래시로 구분된 세 자리가 필요합니다 (part / type / 이슈키-설명)." >&2
  if printf '%s' "$FIELD1" | grep -qE "^(${TYPE_ALT})$"; then
    echo "    첫 자리가 type('${FIELD1}') 입니다 — 앞에 담당 part 가 빠졌습니다." >&2
    echo "    2026-09-09 이전 브랜치가 모두 이 형태이므로, 기존 이름을 따라 만들지 마세요." >&2
  fi
elif [ "$SLASHES" -gt 2 ]; then
  echo "  · 슬래시가 너무 많습니다. 세 자리만 씁니다." >&2
fi

if ! printf '%s' "$FIELD1" | grep -qE "^(${PART_ALT})$"; then
  echo "  · part 가 '${FIELD1}' 입니다. 허용: ${PARTS}" >&2
  echo "    part 는 폴더명이 아니라 담당 파트입니다 (api=backend, data=pipeline, infra=deploy)." >&2
fi

if [ "$SLASHES" -ge 2 ]; then
  FIELD2=$(printf '%s' "$BRANCH" | cut -d/ -f2)
  REST=$(printf '%s' "$BRANCH" | cut -d/ -f3-)

  if ! printf '%s' "$FIELD2" | grep -qE "^(${TYPE_ALT})$"; then
    echo "  · type 이 '${FIELD2}' 입니다. 허용: ${TYPES}" >&2
  fi

  if ! printf '%s' "$REST" | grep -qE "^${KEY_RE}-"; then
    if printf '%s' "$REST" | grep -qE "^[0-9]+-"; then
      echo "  · 이슈 번호만 썼습니다. 프로젝트 키까지 붙입니다 → ${PROJECT_KEY}-<번호>" >&2
    else
      echo "  · Jira 이슈 키가 없습니다. '${PROJECT_KEY}-<번호>-설명' 형태여야 합니다." >&2
    fi
  elif ! printf '%s' "$REST" | grep -qE "^${KEY_RE}-[a-z0-9][a-z0-9-]*$"; then
    echo "  · 설명 부분은 영문 소문자·숫자·하이픈만 씁니다 (한글·공백·대문자·밑줄 불가)." >&2
  fi
fi

echo "" >&2
echo "  헬퍼를 쓰면 규칙을 외우지 않아도 됩니다:" >&2
echo "    sh scripts/new-branch.sh <part> <type> <번호> <설명>" >&2
echo "" >&2
exit 1
