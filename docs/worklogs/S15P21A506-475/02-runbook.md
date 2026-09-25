# S15P21A506-475 운영 절차서 — P1(6-A)·P3·P4(6-B)와 롤백

계획·관문은 `01-plan-v2.md`. 이 문서는 **그대로 따라 칠 명령**이다. 각 단계 앞의 `[ ]` 를 채우며 진행하고,
출력은 `~/rollback-475/` (서버)와 `evidence/phase6/` (로컬)에 남긴다.

## 0. 먼저 알아둘 운영 사실 (2026-09-25 조회로 확인)

| 사실 | 근거 |
| --- | --- |
| data 노드 compose 경로 `~/S15P21A506/deploy/prod/data`, `.env` → `/srv/pickage/data.env` | minio 컨테이너 라벨 |
| **app 노드 compose 경로 `/srv/pickage/repo/deploy/prod/app`** (gitlab-runner 빌드 디렉터리 링크). `~/S15P21A506/deploy/prod/app` 에서 compose 를 치면 **다른 프로젝트로 인식돼 컨테이너가 중복으로 뜬다** | 컨테이너 라벨 |
| 유사도 배치 타이머 없음 — 배치는 사람이 `run-similarity-batch.sh` 로 돈다 | `systemctl list-timers` |
| 상주 로더(`similarity-loader`)는 `--allow-gate-skip` 없이 돈다. 채점 게이트가 `SKIPPED` 인 회차는 **자동 게시되지 않는다**(load.py 가 거부). 09-19 회차도 수동 `--once --allow-gate-skip` 으로 게시된 것으로 보인다(execution_id 형식) | load.py·watch.py, `etl_load_execution` |
| README 의 `docker compose run --rm similarity-loader --once` 는 **그대로 치면 실패**한다 — run 이 command 를 통째로 바꿔 필수 인자 `--psql`·`--database` 가 빠진다. 아래 명령은 인자를 모두 준다 | watch.py argparse |
| 로더의 "이미 게시함" 판정은 DB `etl_dataset_current` 의 manifest SHA 다. 수동 롤백 후 결과 포인터를 되돌리지 않으면 다음 `--once` 가 새 회차를 다시 게시한다 | watch.py `published()` |
| Spark master UI 는 사설 IP `172.26.8.249:8080` 에만 열린다 | `ss -ltn` |
| 운영 compose `ai-similarity` 상한 2g 로는 배치가 끝나지 않는다(09-17 2g·4g, 09-19 2g OOM) | `journalctl -k` |

공통 변수 (로컬 Git Bash):

```bash
KEY=~/Downloads/J15A506T.pem
DATA="ssh -i $KEY ubuntu@j15a506a.p.ssafy.io"
APP="ssh -i $KEY ubuntu@j15a506.p.ssafy.io"
MC='docker exec pickage-data-minio-1 sh -c '"'"'export MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000"; '
```

## 1. 공통 사전 점검 (배치 전마다) — 전부 읽기 전용

```bash
$DATA 'mkdir -p ~/rollback-475; cd ~/S15P21A506/deploy/prod/data
  echo "[ ] 상한 8g:";        grep -n -A1 "mem_limit: 8g" compose.yaml | grep -n memswap
  echo "[ ] Spark 앱 0:";     curl -fsS -m 5 http://172.26.8.249:8080/json/ | python3 -c "import sys,json;d=json.load(sys.stdin);print(\"activeapps\",len(d[\"activeapps\"]))"
  echo "[ ] 주간 수집 비활성:"; systemctl is-active pickage-weekly.service
  echo "[ ] 메모리 10GiB+:";   free -g | awk "/Mem/{print \$7\" GiB available\"}"
  echo "[ ] 이미지:";          grep ^AI_TAG= .env; docker images pickage-ai-similarity --format "{{.Tag}}" | head -3
  echo "[ ] git 깨끗:";        git -C ~/S15P21A506 status --short | grep -v ledger.jsonl'
```

통과 기준: 8g 가 짝으로 보인다 · `activeapps 0` · `inactive` · available ≥ 10 · AI_TAG 가 이미지 목록에 있다 · 추적 파일 변경 없음.

**이전 상태 저장** (쓰기 전 필수. 이 파일이 없으면 롤백이 불가능하다):

```bash
$DATA "cd ~/rollback-475 && ${MC}mc cat l/pickage-vectors/_current.json'"' > vectors_current_before_$(date -u +%Y%m%dT%H%MZ).json && ${MC}mc cat l/pickage-curated/ecosystems-keywords/v1/package-text/_current.json'"' > corpus_current_before_$(date -u +%Y%m%dT%H%MZ).json && ls -la && cat vectors_current_before_*.json"
$APP "docker exec -i pickage-app-postgres-1 sh -c 'PGOPTIONS=\"-c default_transaction_read_only=on\" psql -X -At -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'" \
  <<< "SELECT execution_id, manifest_sha256 FROM etl_dataset_current WHERE dataset='similar-package';" \
  | tee -a docs/worklogs/S15P21A506-475/evidence/phase6/published_before.txt
```

2026-09-25 시험 결과: `similar-package-modelv2-corpuspackage-text-20260908-v2-a453075856e9|a4530758…` — 이것이 R-A 의 `<이전 execution_id>`, run_path 는 `model=v2/corpus=package-text-20260908-v2`.
1절 점검 블록도 같은 날 시험했다 — 상한 항목만 불통과(2g), 나머지 통과(Spark 앱 0 · weekly inactive · 13 GiB · f416bde3 · 추적 파일 변경 없음. `ledger.jsonl` 의 변경은 수집기 장부라 제외).

## 2. P1 — 6-A 인지도 관문 반영

### 2-1. 코퍼스 v3 게시 (로컬 PC, 402 때와 같은 방법)

```bash
# [ ] 로컬 파일이 운영 v2 와 바이트 동일
sha256sum data/keywords/package_text/package_text_2026-09-08.parquet   # 8b9b1f58e666…d860
# [ ] 드라이런
PICKAGE_MINIO_ENV=.env.server python -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v3 --dry-run
# [ ] 게시 — 포인터가 v2 → v3 (같은 수집일이라 advanced)
PICKAGE_MINIO_ENV=.env.server python -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v3
```

코퍼스 포인터만 바뀌고 **아무것도 자동으로 돌지 않는다**(타이머 없음).

### 2-2. 배치 (data 노드, 1절 사전 점검 통과 직후)

```bash
$DATA 'cd ~/S15P21A506/deploy/prod/data && (docker stats --format "{{.Name}},{{.MemUsage}}" > ~/rollback-475/stats_P1.log 2>&1 &) ; sh run-similarity-batch.sh 2>&1 | tee ~/rollback-475/batch_P1.log; echo EXIT=$?; pkill -f "docker stats --format" ; journalctl -k --since "-1h" | grep -i oom-kill'
```

- `[1/6]` run_id=`package-text-20260908-v3` · `[3/6]` `model=v2/corpus=package-text-20260908-v3` · `[6/6]` 포인터 갱신
- 통과: EXIT=0 · OOM 줄 없음 · 로그의 `인지도 관문` 분포가 리허설 R1 과 같은 규모(50만 단계 ≈ 14,000)
- **이 시점에 서비스는 아직 바뀌지 않았다**(상주 로더는 SKIPPED 회차를 게시하지 않는다)

### 2-3. 게시 전 검토 (로컬)

```bash
mkdir -p docs/worklogs/S15P21A506-475/evidence/phase6
$DATA "${MC}mc cat l/pickage-vectors/model=v2/corpus=package-text-20260908-v3/candidates.parquet'" > data/rehearsal475/prod_P1_candidates.parquet
python docs/worklogs/S15P21A506-475/phase3_compare.py data/rehearsal475/runs/R1/out/result/candidates.parquet data/rehearsal475/prod_P1_candidates.parquet > docs/worklogs/S15P21A506-475/evidence/phase6/P1-vs-R1.json
```

통과: `top3_identical_set` 비율 ≥ 90% · `bases_B` 16,000~16,500 · ws·express·zod·js-yaml·yaml 의 top-3 가 R1 과 같다.

### 2-4. 게시 (app 노드)

```bash
$APP 'cd /srv/pickage/repo/deploy/prod/app && docker compose run --rm similarity-loader --once --dry-run --psql psql --database pickage --db-user pickage'
# 무엇을 게시할지 확인한 뒤
$APP 'cd /srv/pickage/repo/deploy/prod/app && docker compose run --rm similarity-loader --once --allow-gate-skip --psql psql --database pickage --db-user pickage 2>&1 | tee ~/rollback-475-P1-publish.log'
curl -s "https://j15a506.p.ssafy.io/api/packages/similar?name=ws&limit=3"
```

통과: 게시 완료 로그 · API 의 `model_ver` 동일, ws top-3 = pusher·partysocket·rpc-websockets · 30분 관찰(5xx·메모리).

## 3. P3 — available_package 교체 (455 완료 통보 뒤)

```bash
# 스크립트를 서버로 (app 노드 홈)
scp -i $KEY docs/worklogs/S15P21A506-475/ops/available_package_*.sql ubuntu@j15a506.p.ssafy.io:~/rollback-475/
# [ ] 1차: 계산만 (범위는 넓게 — 결과를 보고 2차 범위를 정한다)
$APP 'docker exec -i pickage-app-postgres-1 sh -c '"'"'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v verify_only=on -v expect_min=50000 -v expect_max=150000 -v min_keep_pct=60 -v backup_table=available_package_bak_475'"'"' < ~/rollback-475/available_package_swap.sql | tee ~/rollback-475/avail_verify.log'
# [ ] 사람 검토: new_rows ≈ 91,700 전후, kept/removed/added, dropped_no_downloads
# [ ] 2차: 실제 교체 — new_rows ±1% 로 좁혀서
$APP 'docker exec -i pickage-app-postgres-1 sh -c '"'"'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v verify_only=off -v expect_min=<new_rows*0.99> -v expect_max=<new_rows*1.01> -v min_keep_pct=60 -v backup_table=available_package_bak_475'"'"' < ~/rollback-475/available_package_swap.sql | tee ~/rollback-475/avail_swap.log'
curl -s "https://j15a506.p.ssafy.io/api/packages/search?keyword=websocket&limit=5"
```

통과: `교체 완료 — COMMIT` · 백업 표 행 수 = 교체 전 행 수 · 검색 정상 · 기존 10만에서 빠진 패키지(예: `@deepseek-ai/dsh-base`)는 검색에 안 나온다.

## 4. P4 — 6-B 보고서 가능 코퍼스 (P1·P3 통과 뒤)

```bash
# 4-1. 운영 available_package 로 순위 목록 (재정렬 10만의 rank 를 붙인다)
$APP 'docker exec -i pickage-app-postgres-1 sh -c '"'"'psql -X -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT package_name FROM available_package ORDER BY 1"'"'"'' > data/rehearsal475/prod_available_names.txt
python - <<'EOF'
import csv
names=set(open('data/rehearsal475/prod_available_names.txt',encoding='utf-8').read().split())
rr=list(csv.DictReader(open('datasets/targets/rerank_100k_20260922.csv',encoding='utf-8')))
rows=[r for r in rr if r['name'] in names]
print('available',len(names),'rerank 매칭',len(rows),'rerank 에 없는 이름',len(names-{r['name'] for r in rr}))
w=csv.writer(open('data/rehearsal475/reportable_prod.csv','w',encoding='utf-8',newline=''),lineterminator='\n'); w.writerow(['rank','name'])
[w.writerow([r['rank'],r['name']]) for r in rows]
EOF
# [ ] rerank 에 없는 이름 = 0 이어야 한다 (아니면 멈추고 원인 확인)
# 4-2. 재부착 → 게시 파일 자리에 놓기 (원본은 옆에 보존)
cp data/keywords/package_text/package_text_2026-09-08.parquet data/rehearsal475/package_text_v2_backup.parquet
python pipeline/collectors/keywords/backfill_download_rank.py --in data/rehearsal475/package_text_v2_backup.parquet --out data/rehearsal475/package_text_v4.parquet --rank-list data/rehearsal475/reportable_prod.csv --overwrite-existing-column
cp data/rehearsal475/package_text_v4.parquet data/keywords/package_text/package_text_2026-09-08.parquet
PICKAGE_MINIO_ENV=.env.server python -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v4 --dry-run
PICKAGE_MINIO_ENV=.env.server python -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v4
cp data/rehearsal475/package_text_v2_backup.parquet data/keywords/package_text/package_text_2026-09-08.parquet   # 로컬 원복
```

그다음 1절 점검 → 2-2(로그 이름 `_P4`) → 2-3(비교 대상 R2, 통과: 기준 ≈ 26,000~27,000 · **범위 밖 후보 0**: `--available data/rehearsal475/reportable_prod.csv`) → 2-4.

## 5. 롤백

### R-A. 유사 후보를 이전 회차로 (P1·P4 공통)

```bash
# 1) 이전 회차 재적재 — execution_id 는 1절에서 저장한 값 그대로
$APP 'cd /srv/pickage/repo/deploy/prod/app && docker compose run --rm --entrypoint python similarity-loader -m pipeline.similar_package.load --run <이전 run_path> --execution-id <이전 execution_id> --psql psql --database pickage --db-user pickage --allow-gate-skip'
# 2) 결과 포인터 복원 — 이걸 안 하면 다음 --once 가 새 회차를 다시 게시한다
$DATA "cd ~/rollback-475 && ${MC}mc pipe l/pickage-vectors/_current.json'"' < vectors_current_before_<시각>.json"
# 3) 확인
curl -s "https://j15a506.p.ssafy.io/api/packages/similar?name=ws&limit=3"
$APP 'cd /srv/pickage/repo/deploy/prod/app && docker compose run --rm similarity-loader --once --dry-run --psql psql --database pickage --db-user pickage'   # "할 일 없음" 이어야 한다
```

코퍼스 포인터도 되돌리려면(다음 배치가 v3/v4 를 다시 집지 않게) 저장해 둔 코퍼스 run 을 `ingest_derived --run-id <이전>` 으로 재게시한다 — 같은 수집일이라 허용되고, 이미 완료된 run 이라 객체는 다시 올리지 않는다.

리허설: 스크래치 DB 에서 교체 9초·롤백 6초, 롤백 후 내용 지문 동일 (`evidence/phase5/`).

### R-B. available_package 를 백업으로

```bash
$APP 'docker exec -i pickage-app-postgres-1 sh -c '"'"'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v verify_only=off -v backup_table=available_package_bak_475'"'"' < ~/rollback-475/available_package_rollback.sql'
```

리허설: 7종 시험 통과, 롤백 후 내용 지문이 교체 전과 동일 (`evidence/phase5/available_swap/summary.txt`).

## 6. 중단 조건 (어느 단계든)

- 사전 점검 하나라도 불통과 · 배치 OOM · 검토 비율 < 90% · API 5xx 증가 · 게시 로그 오류 · 설명 안 되는 차이
- 중단하면 **다음 단계로 넘어가지 않고** 그 단계의 롤백만 한다. 원인 분석은 로컬 리허설 환경에서.
