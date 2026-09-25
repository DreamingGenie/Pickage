#!/bin/sh
# S15P21A506-475 1b — data 노드 MinIO·MLflow 읽기 전용 조회.
#
# mc 는 minio 컨테이너 안에서만 돈다. 자격증명은 컨테이너 환경변수로 MC_HOST_l 을 만들어 쓰고
# 출력하지 않는다(alias set 을 쓰지 않아 설정 파일도 남기지 않는다). 쓰기 명령(cp/mv/rm/pipe) 없음.
#
# 실행:
#   ssh -i ~/Downloads/J15A506T.pem -o BatchMode=yes ubuntu@j15a506a.p.ssafy.io 'sh -s' \
#     < docs/worklogs/S15P21A506-475/phase1b-probe-minio-mlflow.sh \
#     > docs/worklogs/S15P21A506-475/evidence/phase1/data-node-probe1b.txt 2>&1
set +e
M=pickage-data-minio-1
mcr() { docker exec "$M" sh -c 'export MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000"; '"$1"; }

echo "### corpus pointer (package-text/_current.json)"
mcr 'mc cat l/pickage-curated/ecosystems-keywords/v1/package-text/_current.json'; echo
echo "### corpus runs"
mcr 'mc ls --recursive l/pickage-curated/ecosystems-keywords/v1/package-text/'

echo "### result pointer (pickage-vectors/_current.json)"
mcr 'mc cat l/pickage-vectors/_current.json'; echo
echo "### result runs"
mcr 'mc ls --recursive l/pickage-vectors/' | grep -vE "/(vectors|chunks)/" | head -60

echo "### current result run_manifest.json"
RUN=$(mcr 'mc cat l/pickage-vectors/_current.json' | sed -n 's/.*"run_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
echo "run_path=$RUN"
[ -n "$RUN" ] && mcr "mc cat l/pickage-vectors/$RUN/run_manifest.json"; echo

echo "### dependents objects"
mcr 'mc ls --recursive l/pickage-curated/depsdev/v1/' | grep -i "package-dependents" | head -30

echo "### mlflow alias"
curl -fsS "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=pickage-similarity&alias=production"; echo
curl -fsS "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/get?name=pickage-similarity" | head -c 3000; echo

echo "### model artifacts"
mcr 'mc ls --recursive l/pickage-mlflow-artifacts/' | head -30
