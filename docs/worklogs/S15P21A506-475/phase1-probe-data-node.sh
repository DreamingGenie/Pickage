#!/bin/sh
# S15P21A506-475 1단계 — data 노드(j15a506a) 읽기 전용 조회.
#
# 쓰기 명령 없음. 비밀값을 출력하지 않는다:
#   - `docker compose config` 는 env_file 값을 펼쳐 보여 주므로 쓰지 않는다.
#   - .env 는 키 이름과, 비밀이 아닌 허용 목록 키의 값만 출력한다.
#
# 실행 (로컬 Git Bash, 저장소 루트에서):
#   ssh -i ~/Downloads/J15A506T.pem ubuntu@j15a506a.p.ssafy.io 'sh -s' \
#     < docs/worklogs/S15P21A506-475/phase1-probe-data-node.sh \
#     > docs/worklogs/S15P21A506-475/evidence/phase1/data-node-probe1.txt 2>&1
set +e
echo "### date"; date -u
echo "### resources"; nproc; free -m; swapon --show; df -h / /srv 2>/dev/null
echo "### docker ps"; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"
echo "### docker stats"; docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"
echo "### repo status"; cd ~/S15P21A506 && git status --short | head -30; git log --oneline -1
echo "### data dir"; cd deploy/prod/data && ls -la
echo "### compose mem lines (all compose files)"; grep -n -E "mem_limit|memswap_limit" compose*.y*ml
echo "### git diff compose"; git diff --stat -- . ; git diff -- compose.yaml | head -60
echo "### .env keys"; sed -n "s/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p" .env
echo "### .env allowlisted values"
grep -E "^(AI_TAG|AI_CORPUS_PREFIX|AI_DST_RESULT|AI_MODEL_NAME|AI_MODEL_ALIAS|AI_DEPENDENTS_PATH|MLFLOW_TRACKING_URI|COMPOSE_PROFILES|COMPOSE_FILE)=" .env
echo "### images"; docker images --format "{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}" | grep -iE "ai-similarity|pickage"
echo "### timers"; systemctl list-timers --all --no-pager | head -30
echo "### units"; systemctl list-unit-files --no-pager | grep -iE "pickage|similar|ingest|spark|weekly"
echo "### crontab"; crontab -l 2>&1 | grep -v "^#"
echo "### who"; who
