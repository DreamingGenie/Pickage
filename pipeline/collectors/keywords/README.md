# 패키지 keywords 수집기 (ecosyste.ms)

근거: `docs/api & data/검증_keywords_수집가능성_260908.md`. 목적은 **description + keywords로 유사 패키지 3개를 찾는 모델**의 학습 데이터. 데이터는 `/data/keywords/`(gitignore)에 쌓인다.

## 파일

| 파일 | 역할 |
|---|---|
| `collect_keywords.py` | ecosyste.ms 목록 API(`sort=downloads&order=desc`, 1,000개/페이지)를 순위 순으로 호출해 필요한 열만 `part-NNNNN.jsonl.gz`(페이지당 1개)로 저장. 페이지 파일 존재 = 완료(임시파일 → rename)라 재시작 시 없는 페이지만 받는다. 429는 `x-ratelimit-reset`까지 대기, 5xx·연결오류는 지수 백오프 6회. `manifest.json`에 페이지별 첫/끝 downloads·소요를 기록 |
| `start_keywords.cmd` | 시작/재시작(더블클릭). 이미 돌고 있으면 새로 띄우지 않음. 로그 `data/keywords/raw/keywords_<run>.log` |
| `status.py` | 진행 상태 한 화면(실행 여부·진행률 바·순위 도달·페이지/h·ETA·keywords/topics 비율). `--watch`로 60초 갱신. part 파일 mtime과 manifest만 읽어 수집기에 영향 없음 |
| `status_watch.cmd` | 현황 창(더블클릭). 60초 갱신, 닫아도 수집기 영향 없음 |
| `build_package_text.py` | raw + deps.dev `Description` → `data/keywords/package_text/package_text_<run>.parquet`(zstd, 86 MB/100만 행) + `summary_<run>.json`. 중복 제거 → removed·unpublished 제외 → 스팸 표시(`is_spam`) → description coalesce(npm > deps.dev > repo) → keywords_source(npm / github_topics / none). 규칙과 수치는 `docs/api & data/수집결과_keywords_프로파일_260908.md` §4. DuckDB, 약 25초. 산출물 게시는 아래 "게시" 절 |

## 저장 열 (한 줄 = 패키지 1개)

`rank, name, namespace, description, keywords[], downloads_last_month, downloads_period, dependent_packages_count, dependent_repos_count, versions_count, latest_release_number, latest_release_published_at, first_release_published_at, licenses, status, repository_url, homepage, maintainers_count, last_synced_at, repo_metadata_updated_at, repo{full_name, description, topics[], language, stargazers_count, forks_count, archived, fork, pushed_at, default_branch, license}, page, fetched_at`

원본 응답(110 MB/페이지)은 보존하지 않는다. `keywords`는 npm 최신 버전의 keywords와 동일(100개 대조 불일치 0). `repo.topics`는 GitHub 저장소 topics — keywords 결손분(약 40%)의 절반을 채우는 보완 신호.

## 실행

`collect_keywords.py` 는 User-Agent 연락처를 환경변수 `OSS_SHIFT_UA_CONTACT`(이메일 또는 URL)로 받는다. 비어 있으면 시작하지 않는다(`downloads/collect.py` 와 같은 변수).

```bash
# 상위 100만 (1,000페이지, 약 1.5~2시간, 전송 약 60 GB). 중단 후 같은 명령이면 이어감
.venv-bq/Scripts/python.exe pipeline/collectors/keywords/collect_keywords.py --run 2026-09-08 --pages 1000 --out data/keywords/raw

# 스모크 (2페이지 × 100개, run=smoke-<run>)
.venv-bq/Scripts/python.exe pipeline/collectors/keywords/collect_keywords.py --run 2026-09-08 --smoke --out data/keywords/raw

# 팀 분산이 필요할 때 (전수 5,821페이지 등): page % of == worker 만 받는다. 결과 폴더를 그대로 합치면 된다
.venv-bq/Scripts/python.exe pipeline/collectors/keywords/collect_keywords.py --run 2026-09-08 --pages 5821 --worker 2 --of 6 --out data/keywords/raw
```

## 게시

`build_package_text.py` 는 파일을 만들기만 한다. 서버에 올리는 것은 파생 데이터셋 입고기다.
**이 게시가 유사도 배치의 트리거다** — `_current.json` 이 없으면 배치는 1단계에서 멈춘다.

```powershell
# 터널을 먼저 연다 (별도 창, 끝날 때까지 열어 둔다)
ssh -i ~/.ssh/J15A506T.pem -N -L 19000:localhost:9000 ubuntu@j15a506a.p.ssafy.io

$env:PICKAGE_MINIO_ENV=".env.server"
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset package-text --dry-run
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v1
```

- 로컬 파일명은 `package_text_<수집일>.parquet` 그대로 두고 **올릴 때만** `package_text.parquet`
  으로 바뀐다. 배치가 `--package-text /work/in/package_text.parquet` 으로 이름을 고정해 받는다.
- 새 수집일이 생기면 `ingest_derived.py` 의 `DATASETS['package-text']['date']` 와 `--run-id`
  두 값만 바꾼다. 포인터는 **더 나중 수집일로만** 간다 — 과거 실행을 재검증해도 되돌아가지 않는다.
- **실행 ID 에 입고일이 아니라 수집일을 쓴다**(`package-text-20260908-v1`). 다른 입고
  (`keywords-20260909-v1`·`deprecated-replacement-20260914-v1`)와 다른 의도된 예외다. 이 값이
  유사도 산출물 경로 `pickage-vectors/model=vN/corpus=<run_id>` 에 그대로 박히므로, 거기서
  알고 싶은 것이 입고한 날이 아니라 **어느 수집분으로 계산했나** 이기 때문이다.

## 주의

- 순위는 호출 시점의 `downloads`(last-month) 정렬이라 2시간 동안 값이 갱신되면 페이지 경계의 패키지가 **중복되거나 빠질 수 있다.** 적재 시 `name` 기준 중복 제거(최신 `fetched_at` 우선), 누락은 다음 run에서 채운다. manifest의 `page_log`(첫/끝 downloads)가 단조 감소인지로 드리프트를 점검한다.
- 빈 페이지가 오면 레지스트리 끝으로 보고 멈춘다(2026-09-08 기준 5,821페이지).
- ecosyste.ms 데이터는 **CC BY-SA 4.0** — 발표·저장소에 출처 표기.
- Claude Code 세션이 띄운 프로세스는 앱 종료 시 죽을 수 있으니 장시간 실행은 `start_keywords.cmd`로 띄운다. PC 절전 시 멈추고 깨어나면 다음 페이지부터 이어간다(진행 중이던 페이지는 재요청).
