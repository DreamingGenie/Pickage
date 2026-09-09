#!/bin/sh
#
# new-branch.sh — 팀 규칙에 맞는 작업 브랜치를 origin/develop 에서 만든다
#
# 사용: sh scripts/new-branch.sh <part> <type> <이슈번호> <설명...>
#   예) sh scripts/new-branch.sh data feat 290 downloads bronze ingest
#       → data/feat/S15P21A506-290-downloads-bronze-ingest
#
#   이슈번호는 290 / S15P21A506-290 둘 다 됩니다.
#   설명은 여러 단어로 나눠 써도 하이픈으로 이어 줍니다.
#
# 규칙 정본: AGENTS.md 4번 항목

set -e

PROJECT_KEY="S15P21A506"
PARTS="frontend api data ai worker infra docs"
TYPES="feat fix refactor test chore docs style config"
BASE="origin/develop"

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "git 저장소 안에서 실행해 주세요." >&2
  exit 2
}
cd "$ROOT"

usage() {
  echo "사용: sh scripts/new-branch.sh <part> <type> <이슈번호> <설명...>" >&2
  echo "" >&2
  echo "  part : ${PARTS}" >&2
  echo "  type : ${TYPES}" >&2
  echo "" >&2
  echo "  예) sh scripts/new-branch.sh data feat 290 downloads bronze ingest" >&2
  echo "      → data/feat/${PROJECT_KEY}-290-downloads-bronze-ingest" >&2
  exit 2
}

[ $# -lt 4 ] && usage

PART="$1"; TYPE="$2"; ISSUE="$3"; shift 3

in_list() {
  _needle="$1"; _list="$2"
  for _item in $_list; do
    [ "$_item" = "$_needle" ] && return 0
  done
  return 1
}

if ! in_list "$PART" "$PARTS"; then
  echo "part '${PART}' 는 허용 목록에 없습니다." >&2
  echo "  허용: ${PARTS}" >&2
  echo "  part 는 폴더명이 아니라 담당 파트입니다 (api=backend, data=pipeline, infra=deploy)." >&2
  exit 2
fi

if ! in_list "$TYPE" "$TYPES"; then
  echo "type '${TYPE}' 는 허용 목록에 없습니다." >&2
  echo "  허용: ${TYPES}" >&2
  exit 2
fi

# 이슈번호 정규화: 290 / S15P21A506-290 / s15p21a506-290 → S15P21A506-290
NUM=$(printf '%s' "$ISSUE" | grep -oE '[0-9]+$' || true)
if [ -z "$NUM" ]; then
  echo "이슈번호를 읽을 수 없습니다: '${ISSUE}'" >&2
  echo "  290 또는 ${PROJECT_KEY}-290 형태로 넣어 주세요." >&2
  exit 2
fi
KEY="${PROJECT_KEY}-${NUM}"

# 설명: 남은 인자를 하이픈으로 잇고 소문자·하이픈만 남긴다
DESC=$(printf '%s' "$*" \
  | tr '[:upper:]' '[:lower:]' \
  | tr ' _/.' '-' \
  | sed -e 's/[^a-z0-9-]//g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')

if [ -z "$DESC" ]; then
  echo "설명에서 쓸 수 있는 글자가 없습니다: '$*'" >&2
  echo "  브랜치명의 설명은 영문 소문자·숫자·하이픈만 씁니다 (한글 불가)." >&2
  exit 2
fi

BRANCH="${PART}/${TYPE}/${KEY}-${DESC}"

# 최종 검증 — 훅과 같은 구현을 쓴다
sh "${ROOT}/scripts/lib/check-branch-name.sh" "$BRANCH" || exit 1

if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  echo "이미 있는 브랜치입니다: ${BRANCH}" >&2
  echo "  전환하려면: git switch ${BRANCH}" >&2
  exit 1
fi

echo "origin 최신화 중..."
if ! git fetch origin --quiet; then
  echo "경고: git fetch 실패. 로컬에 있는 ${BASE} 기준으로 만듭니다." >&2
fi

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "${BASE} 를 찾을 수 없습니다." >&2
  exit 1
fi

git switch -c "$BRANCH" "$BASE"

echo ""
echo "브랜치를 만들었습니다: ${BRANCH}"
echo "  기준: ${BASE} ($(git rev-parse --short "$BASE"))"
echo ""
echo "커밋 제목은 'type: subject' 로 씁니다. Jira 키(${KEY})는 훅이 자동으로 붙입니다."
echo "  예) git commit -m \"${TYPE}: 무엇을 바꿨는지\""
