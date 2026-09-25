# S15P21A506-475 진행 장부

유사 후보 코퍼스 46.9만 확장 — 격리 검증 후 운영 반영. 단계 상태·결정·해시를 여기 기록한다.
기억이 아니라 이 장부로 이어간다. 수치는 `evidence/` 의 원문 파일 경로와 함께만 적는다.

## 결정 (2026-09-25, 사용자)

| # | 결정 |
| --- | --- |
| D1 | 455(의존 수 추이 46.9만) 운영 적재를 기다리지 않는다. 새 후보의 추이 그래프가 비는 것은 감수 |
| D2 | 정보를 줄 수 없는 패키지는 후보로 노출하지 않는다. 기존에 막던 방식과 동일하게. `available_package` 가 그 기준이 맞는지, 이번 작업으로 갱신돼야 하는지는 1단계 증거로 확인 후 확정 |
| D3 | 보류. websocket 은 보여야 하지만 방치된 패키지 유입은 우려. 방법 검토 후 확정 |
| D4 | 코드(6-A, 인지도 관문 이미지)와 데이터(6-B, 코퍼스)를 나눠 반영 |
| D5 | 운영 조회는 Claude 가 SSH 로 수행 |

## 단계 상태

| 단계 | 상태 | 비고 |
| --- | --- | --- |
| 0 착수 | 완료 | Jira S15P21A506-475(진행 중), 브랜치 `data/chore/S15P21A506-475-similarity-corpus-468k-rehearsal`, 460 에 공유 코멘트 |
| 1 운영 조회 | 완료 (2026-09-25 01:48~01:50 UTC) | 사용자 권한 허용 후 스크립트 3종 실행. 쓰기 0건. 결과는 아래 "1단계 결과" |

## 접속 확인 (2026-09-25 01:44 UTC)

- data `j15a506a.p.ssafy.io` = `ip-172-26-8-249`, app `j15a506.p.ssafy.io` = `ip-172-26-6-235`, 사용자 `ubuntu`
- 양 노드 레포 `~/S15P21A506` develop `766615b`
- data 노드 로그인 세션 4개(다른 작업자 가능성) — 무거운 명령 금지

## 1단계 결과 (증거: `evidence/phase1/`)

| # | 항목 | 확인값 | 증거 |
| --- | --- | --- | --- |
| F1 | 운영 `ai-similarity` 상한 | `mem_limit 2g` = `memswap_limit 2g`, 서버 compose 는 레포와 동일(diff 없음) | data-node-probe1.txt |
| F2 | data 노드 자원 | 4 vCPU, 15,785 MiB, available 13,386 MiB, swap 2 GiB. Spark worker① 상한 10 GiB(조회 시 303 MiB 사용) | data-node-probe1.txt |
| F3 | `AI_DEPENDENTS_PATH` | `package-dependents-candidate-pool-20260916-v1` (29,310 풀). exp460k 판(`package-dependents-exp460k-20260922-v1`, 109 MiB)도 MinIO 에 존재 | probe1.txt, probe1b.txt |
| F5 | 운영 `available_package` | **97,743행**, 전부 2026-09-22 03:54:31 한 번에 입력. 레포에 이 표를 채우는 적재기 없음(시드만) | app-node-probe1c.txt |
| F5' | 현재 후보 중 범위 밖 | 후보 0행·기준 0개가 `available_package` 밖 — 명시적 필터가 아니라 코퍼스 `max_rank 100000` 이 범위와 겹쳐서 생긴 결과 | app-node-probe1c.txt |
| F7 | 스케줄러 | 유사도 배치 타이머 **없음**. `pickage-weekly.timer`(10분)만 있고 유사도·포인터와 무관(`run-weekly-ingest.sh`). app 노드 `similarity-loader` 는 `pickage-vectors/_current.json` 을 60초 간격 감시 | probe1.txt, probe1c.txt |
| F8 | 운영 이미지 | `AI_TAG=f416bde3`(09-22 빌드). 450 커밋 3개(cef2017·cd3100d·1fe6fa3) 포함. 이후 `ai/similarity` 변경 없음 | probe1.txt + 로컬 git |
| F8' | **현재 서비스 결과** | `model=v2/corpus=package-text-20260908-v2`, **2026-09-19 13:33 생성** — 450 이미지 이전. manifest 에 downloads_floor·complement 없음. 배치는 모델+코퍼스가 같으면 재실행하지 않으므로 450 은 **한 번도 적용되지 않음** | probe1b.txt |
| — | 현재 회차 규모 | 자격 통과 17,883 · 기준 16,402 · 후보 275,192 · 692.3초. 채점 게이트 `SKIPPED`(51K holdout 미정의) | probe1b.txt |
| — | DB `similar_package` | 273,584행 · 기준 16,350 · 106 MB · model_ver `bge-small-v7-v5clean-batch32-step500` | probe1c.txt |
| — | 코퍼스 포인터 | `package-text-20260908-v2`(09-19 게시, `download_rank` 보강판). v1 도 보존 | probe1b.txt |
| — | MLflow | `pickage-similarity` v2 `@production` → `s3://pickage-mlflow-artifacts/v7-v5clean` | probe1b.txt |
| — | app 노드 | available 12,512 MiB, 디스크 95 GB 여유(70% 사용). 이미지 api `6832cac8`, web `c88e20ae`, rag `29153b3c` | probe1c.txt |
| — | websocket | `package`·`available_package` 둘 다 존재. 후보에서 빠진 원인은 12개월 필터뿐 | probe1c.txt |

## 1단계로 바뀐 계획 사항

- 6-A(코드만 반영)는 자동 메커니즘으로 트리거되지 않는다. 배치 재실행에는 코퍼스 run 또는 모델 버전 변경이 필요하다.
- D2: 지금 범위를 막는 것은 필터가 아니라 우연한 일치다. 46.9만 코퍼스를 쓰면 `available_package`(97,743) 밖 후보가 생긴다 → 명시적 제한 또는 범위 확장 결정이 필요하다.
- D3: 12개월 필터는 rank≤10만에서 자격 50,193개 중 32,353개(64%)를 제거한다. 다운로드 예외만으로는 2011년 방치 패키지도 복귀한다 (`evidence/phase1/d3-age-exemption-sim.txt`).
- F6(455 적재 상태)는 D1(감수)로 조회 생략. → 아래 "1d" 로 D1 폐기.

## 1d — 보고서 제공 가능 범위 (2026-09-25, 증거: app-node-probe1d.txt, d2-scope-sim.txt)

- 운영 최신 시점(2026-08-31) `package_version_snapshot` 보유 패키지 = **97,743** = `available_package` 행 수. 기존 범위 기준은 "의존 수 추이 데이터 보유"로 보인다(개수 일치만 확인, 교집합 쿼리는 타임아웃).
- ⚠ 조회 중 4개 쿼리(package_snapshot 전수 2·package_env 전수·교집합)가 60초 statement_timeout 으로 취소됨. 직후 `/actuator/health` 200(0.03초). **이후 운영에서는 전수 스캔 쿼리를 돌리지 않는다** — 교집합·커버리지는 로컬 목록과 리허설 DB 에서 계산한다.
- 455(!269) 대상은 46.9만 → **재정렬 10만**(`rerank_100k_20260922.csv`)으로 변경됨(46.9만×229일은 +113 GB 로 앱 노드 초과). 재정렬 10만은 AI 후보 풀 29,310 전부 포함.
- 재정렬 10만 중 다운로드 시계열(46.9만 목록)이 있는 것 **91,717**, 없는 것 8,283(전부 스코프).
- 자격 통과 코퍼스(기준일 09-25): 기존 10만 17,807 · **재정렬 10만∩다운로드 28,922** · 46.9만 전체 28,922 → 보고서 가능 범위로 제한해도 코퍼스 손실 0.
- 기존 10만에서 빠지는 28,151개는 월 100만 이상 0개, 10만 이상 179개(상위는 `@deepseek-ai/dsh-*` 등 스코프 조각).

## 결정 갱신 (2026-09-25, 사용자)

| # | 결정 |
| --- | --- |
| D1 | **폐기.** "분석 보고서를 줄 수 있는 패키지만 연다"로 대체 — 의존 수 추이 없는 패키지는 열지 않는다 |
| D2 | (나) 서비스 범위를 보고서 가능 패키지로 갱신한 뒤 AI 확장. 후보는 `available_package` 안으로 **명시적으로** 제한 |
| D3 | 12개월 필터 예외를 "최근 신규 채택(dependent_transition 유입)" 기준으로 검증. 규칙 확정은 AI 파트와 |

## 선행 관계 (갱신)

```
455 운영 적재(!269, 재정렬 10만 × 229일)  ─┐
                                          ├→ available_package 갱신(보고서 가능 = 재정렬10만 ∩ 다운로드 ∩ 운영 실측)
                                          │     └→ AI 배치: 코퍼스 ⊂ available_package 명시 필터 + 450 인지도 관문 + (D3 예외)
```

`available_package` 는 레포에 적재기·절차가 없다(09-22 수동 입력). 갱신 절차를 새로 만들어야 한다.

## 2단계 결과 (2026-09-25 02:12 UTC, 로컬 전용 — 운영 쓰기 0)

스크립트 `phase2_build_and_verify.py`, 증거 `evidence/phase2/`. 산출물은 git 밖 `data/rehearsal475/`.

| 항목 | 값 |
| --- | --- |
| 입력 `package_text` | 로컬 사본 SHA `8b9b1f58…` = 운영 v2 manifest SHA (바이트 동일) |
| 입력 `rerank_100k` | 작업 사본은 CRLF(core.autocrlf=true). LF 정규화 SHA `001d6314…` = targets/README §7-5 고정값 |
| 보고서 가능 목록(잠정) | 재정렬 10만 ∩ 46.9만 = 91,717행, SHA `3fb1e814…` (`data/rehearsal475/reportable_rerank_20260925.csv`) |
| 재부착 산출물 | `package_text_reportable.parquet` SHA `74e138ec…`, 86,416,963 B |
| 원본 대비 | 행 수·열 이름·열 타입 동일, **download_rank 외 22개 열 값 완전 동일**, download_rank 91,712 = 기대값, 값 전수 일치 |
| 목록 5건 누락 | 보고서 가능 목록 91,717 중 5개는 package_text 에 이름이 없음(91,712) — 운영 확정 때 확인 |
| 코퍼스(정본 함수, 기준일 09-25) | 현재 v2 17,807 → **28,922** (+11,115, 제거 0). 새 코퍼스 전부 보고서 가능 목록 안 |
| 날짜 드리프트 | 09-19 운영 회차 17,883 → 같은 입력을 09-25 에 돌리면 17,807 (12개월 필터가 실행일 기준) |
| 테스트 | keywords 9 passed · ai/similarity 134 passed + 42 subtests (루트에서 실행, CI 와 동일) |

### D3 — 신규 채택(유입) 기준 예외 시뮬레이션 (`evidence/phase2/d3-inflow-exemption-sim.txt`)

입력: 운영 MinIO `dependent-transitions-exp460k-20260922-v1` 읽기 전용 다운로드, SHA `a1b94b51…` = manifest. 구간 1y(2025-08-31→2026-08-31), kind regular.

- 12개월 필터 탈락 28,823개(보고서 가능 코퍼스 기준), 전부 transitions 행 있음.
- `inflow ≥ 20 & inflow > outflow & repo 미보관`: 복귀 1,739 (2015년 이전 릴리스 37). websocket 복귀(유입 39·이탈 19), chainsaw 제외(유입 0).
- 임계 50 이상이면 websocket 도 제외 — **임계값을 websocket 한 사례에 맞추면 과적합**. 4단계 품질 평가로 정한다.
- ⚠ `fs`·`net`·`https` 등 Node 내장 모듈 이름 선점 패키지가 복귀 목록에 있다(실수 설치로 유입 발생). 내장 모듈 이름 제외 등 보완 규칙 필요.
- 적용 시 코퍼스 약 28,922 + 1,739 = 30,661 (3단계 메모리 실측 대상).
- 보완 규칙 검토(`evidence/phase2/d3-builtin-filter.txt`): Node 내장 모듈 이름 일괄 제외는 과하다 — 복귀 17개 중 `buffer`·`events`·`util`·`url` 등 정상 폴리필과 `sqlite` 까지 빠진다. npm 자리 표시 설명문("not currently in use"·"security holding package")으로 거르는 편이 정확하다. 보고서 가능 범위 안의 자리 표시 패키지는 6개(`fs`·`child_process`·`tty`·`dgram`·`child-process`·보안 선점 1) — 이들은 현재 검색 범위에도 들어 있을 수 있다.

## 3단계 (진행 중, 로컬 Docker)

하네스 `phase3_run.sh`, 비교 `phase3_compare.py`, 증거 `evidence/phase3/<run>/`.

- 이미지 `pickage-ai-similarity:f416bde3-local` — `ai/similarity` 는 f416bde3 과 diff 0. 라이브러리 버전 고정값과 일치(3.11.16 / numpy 2.4.6 / ort 1.30.0 / pyarrow 25.0.1 / transformers 5.17.0).
- 입력 SHA 대조: 운영 MinIO 모델 `model.onnx` `6fe09db5…` = GPU 서버 `onnx_bge_v7_v5clean/model.onnx`. dependents 2종 = 각 run_manifest SHA.
- **로컬은 onnxruntime 스레드 수를 EC2 와 맞출 수 없다.** `--cpus 4` 는 코어 16개를 보이게 두고, `--cpuset-cpus 0-3` 을 줘도 ort 가 16 스레드를 만든다(affinity 설정 실패 로그). 배치 코드에 스레드 설정이 없다. → 로컬 메모리는 **16 스레드 기준 보수적 상한**.
- 2g 두 번 모두 OOM(임베딩 시작 30~40초, cgroup peak 2 GiB). S15P21A506-384(미완)에 "2 GiB 로는 완주 불가, 임베딩만 약 1.7 GiB" 기록과 일치. **운영 compose 2g 로는 배치가 돌지 않는다 — 09-19 회차는 상한을 임시로 올려 돌린 것으로 추정(미확인).**
- R0(현재 코퍼스 v2, floor 0, dependents 없음 = 09-19 운영 조건), 8g: 완주 1,182초, **cgroup peak 4,289,159,168 B (3.99 GiB)**, 자격 17,807, 후보 273,781행.
- **R0 재현도**: 공통 쌍 266,587개 cos 점수 **전부 소수점 6자리까지 운영과 동일**. top-3 순서 일치 93.06%, 불일치 1,132건 전부 분류 — 동점 순서(비결정성, S15P21A506-174) 838 · 날짜 드리프트 275 · 코드 개선 19(`markdown-it` 이 호스트 태그 예외로 더는 플러그인으로 걸리지 않음). **설명 안 되는 차이 0.** (`evidence/phase3/R0/diff-explained.txt`)

- R1(현재 코퍼스 v2 + 새 이미지 기본값: 인지도 관문 on + 운영 dependents = **6-A 결과**), 8g: 완주 1,201초, **cgroup peak 5,026,742,272 B (4.68 GiB)** — R0 대비 +0.69 GiB(dependents 적재로 추정). 보완재 관문 5,136쌍 제거, 인지도 관문 단계 분포 {50만: 14,008 · 10만: 895 · 5만: 165 · 1만: 292 · 0: 956}. 후보 173,782행.
- **6-A 는 순수 개선이 아니다**: 기준 16,316개 중 top-3 동일 24.4%(=75.6% 변경). top-3 평균 cos 0.653 → 0.617, cos<0.55 비율 18.1% → 30.0% (`evidence/phase4/top3-cos-R0-R1.txt`). ws 는 eiows·websocket13 → pusher·partysocket·rpc-websockets 로 좋아지지만 `glob→fflate`, `string-width→sql-formatter/@antv/g2`, `semver→@lezer/lr` 같은 오답도 생긴다. 서비스 recall(in-scope 62쌍) @3 0.242→0.290, @20 0.677→0.565 — 표본이 작아 확정 불가. **AI 파트 판단 사안.** 검수표 `evidence/phase4/review_top3_R0_R1.csv`(203행, 판정 열 비움).

- R2(보고서 가능 코퍼스 + 운영 dependents(29,310 풀) + 새 이미지 기본값 = **6-B, .env 무변경**), 8g: 완주 1,897초, **cgroup peak 5,390,532,608 B (5.02 GiB)**. 자격 28,922, 검색 867,660쌍, 관문 후 598,332, 인지도 관문 후 206,704. 후보 204,752행 · 기준 26,406(+10,090). 보고서 가능 범위 밖 후보 **0**. 기존 기준의 top-3 유지 81.2%. dependents 커버리지 28,922/28,922(100%) — 29,310 풀 파일이 새 코퍼스를 이미 전부 덮는다.
- R2 서비스 recall: 평가 질의 코퍼스 포함 **여전히 33/85** — 평가 패키지 누락 원인은 범위가 아니라 12개월 필터. in-scope @3 0.306, **@20 0.419(R1 0.564)** — 코퍼스가 넓어져 정답이 검색 top-30 밖으로 밀리는 것으로 보임. `--retrieve-k` 재검토 대상(460 세부 항목과 같은 우려).

- R3(보고서 가능 코퍼스 + **46만판 dependents**), 8g: 완주 1,796초, **cgroup peak 5,841,354,752 B (5.44 GiB)**. 결과는 R2 와 **100% 동일**(후보 204,752행 전부, top-20 겹침 1.0). → 46만판 dependents 는 품질 이득 0, 메모리 +0.42 GiB. **운영 `.env` 의 `AI_DEPENDENTS_PATH` 는 바꾸지 않는다.**

### 3단계 요약 (로컬, 16 스레드 기준 보수적 상한)

| 실행 | 코퍼스 | 관문 | 최고 메모리 | 시간 | 후보 행 / 기준 |
| --- | --- | --- | ---: | ---: | --- |
| R0 | v2 17,807 | 인지도 off·dependents 없음(09-19 운영 조건) | 3.99 GiB | 1,182초 | 273,781 / 16,325 |
| R1 | v2 17,807 | 새 이미지 기본값 (= 6-A) | 4.68 GiB | 1,201초 | 173,782 / 16,316 |
| R2 | 보고서 가능 28,922 | 새 이미지 기본값 (= 6-B) | 5.02 GiB | 1,897초 | 204,752 / 26,406 |
| R3 | 보고서 가능 28,922 | + 46만판 dependents | 5.44 GiB | 1,796초 | R2 와 동일 |

- **2 GiB(운영 compose) 로는 어떤 실행도 완주하지 못한다.** 6-A·6-B 모두 S15P21A506-384(상한 조정)가 선행 조건이다. 권장 상한은 R2 최고 5.02 GiB(16 스레드) + 여유 → **6~7 GiB**, 단 EC2(4 스레드) 실측으로 확정 필요. 노드 합계는 Spark worker① 상한 10g 와 겹치므로 배치 시각 분리 또는 worker 상한 조정이 필요(compose 주석).
- 로컬 실행 시간은 EC2 와 다르다(CPU 다름). 참고용.

## 4단계 선행 측정 — 서비스 조건 recall (`phase4_service_recall.py`)

평가 패키지를 코퍼스에 끼워 넣지 않고 배치 산출물 순위를 그대로 채점한다. R0(= 현재 운영과 같은 조건):

- 평가쌍 315 전체: recall@3 **0.048**, recall@20 0.133 — 평가 질의 85개 중 **33개만 코퍼스에 있다**.
- 두 패키지가 모두 코퍼스에 있는 62쌍: recall@3 0.242 (문서의 0.238 과 부합).
- → 서비스 품질은 모델보다 **코퍼스 범위·12개월 필터**에 묶여 있다.

## 5단계 (진행 중, 스크래치 DB)

- 일회용 `postgres:16` 컨테이너 `rehearsal475-pg`(mem 2g, 운영 app postgres 와 같은 상한). 로컬 `pickage` 볼륨 미사용.
- V1~V13 마이그레이션 13개 오류 없이 적용. `package` 922,322행(package_text 이름, **합성 id**), `available_package` 91,712행(보고서 가능 잠정 목록).
- 로더 `pipeline.similar_package.load` 는 한 트랜잭션에서 DELETE→INSERT(SHARE ROW EXCLUSIVE — 읽기는 막지 않음), 이름 미매칭은 버린다. **`available_package` 검사는 없다** → D2 제한은 코퍼스(2단계 순위 목록)에만 걸려 있다. 적재 전 검증 추가를 권고.
- R0 verify-only: 273,781행 전부 매칭(미해결 0). R0 적재 5초, 지문 `36ee9fa105fafa6347ba8e3f7fbb9047`, 포인터 `rehearsal-R0`.
- **교체 R0→R2** (`phase5_swap_rehearsal.sh`): 9초, 204,752행·기준 26,406, 범위 밖 후보 0, 포인터 `rehearsal-R2`. 적재 중 0.2초 간격 조회 24회 — 오류·빈 결과 0, ws 결과가 8행→20행으로 원자 전환. (지연 p99 406ms 는 `docker exec` 기동 비용 포함 — 쿼리 지연 아님)
- **롤백 R2→R0** (같은 execution_id 재적재): 6초, 지문 `36ee9fa1…` **최초 적재와 동일**, 포인터 `rehearsal-R0` 복귀, 조회 19회 오류 0. (증거 파일 `state-after-R0.txt` 는 롤백 결과로 덮였고, 최초 값은 이 장부의 위 줄이 기록)

## 계획 v2·절차서·교체 스크립트 (2026-09-25 오후)

결정 확정(사용자 "전부 제안대로"): `01-plan-v2.md` §0. 순서 P0 메모리 8g → P1 6-A → P2 455 → P3 available_package → P4 6-B → P5 마무리, 다음 회차 N1.

추가로 확인한 운영 사실 (증거 `evidence/phase1/`):
- 커널 OOM: 09-17 05:22(2g)·05:47(4g)·**09-19 13:12(2g)** — 2g 로 완주한 적 없음, 성공 회차는 수동으로 상한을 올려 재실행한 것으로 추정 (`data-node-oom-history.txt`)
- Spark master: 09-09 스모크 4건 이후 등록 앱 0 (`data-node-spark-history.txt`). UI 는 `172.26.8.249:8080`
- 상주 로더 명령에 `--allow-gate-skip` 없음 → SKIPPED 회차는 자동 게시 불가. v2 회차는 09-19 14:32 UTC 게시(execution_id 에 SHA 접미사 — watch 형식, 수동 `--once` 추정) (`app-load-history.txt`, `app-loader-history.txt`)
- README 의 `docker compose run --rm similarity-loader --once` 는 필수 인자 누락으로 실패하는 형태
- 로더 "게시됨" 판정은 DB `etl_dataset_current` → 수동 롤백 시 결과 포인터 복원 필수
- app 노드 compose 경로는 `/srv/pickage/repo/deploy/prod/app`(gitlab-runner 빌드 디렉터리 링크), data 노드는 `~/S15P21A506/deploy/prod/data`
- 자동완성 사전 API `/api/dict-manifest` 는 운영 404 — 검색은 전부 available_package 조회
- 운영 available 97,743 의 최신 기준일 downloads 보유 확인 쿼리는 30초 타임아웃으로 취소(인덱스 계획이었으나 힙 무작위 읽기). 이후 운영 조회는 교체 스크립트의 verify-only 로 대신
- `rank_top100k_20260902.csv` 에 이름 중복 4건(`lavalink-client` 등)

관문 분리 실험 (`evidence/phase4/gate-isolation.txt`, `--state` 로 임베딩 재사용):
- R1a(인지도만) recall@3 0.274 · R1b(보완재만) 0.242 · R1(둘 다) 0.290. 오답(`glob→fflate` 등)은 두 관문 결합에서 나온다
- top-3 에 cos<0.5 후보가 있는 기준 R0 10.8% · R1a 19.6% · R1 20.1%. 유사도 하한 0.5 적용 시 후보 0 개 기준 1,435 → 채택 안 함
- `--state` 재사용 시 최고 메모리 1.29~2.29 GB

D3 임계값별 평가 질의 코퍼스 포함 (`evidence/phase4/d3-threshold-eval-coverage.txt`): 현재 33/85, N=20 이면 46/85. 12개월로 빠진 질의 47개에 moment·async·passport·remark·luxon 포함.

available_package 교체 스크립트 (`ops/`), 스크래치 리허설 7종 전부 통과 (`evidence/phase5/available_swap/summary.txt`):
T1 verify-only 91,618(합성 기대값과 일치)·변경 없음 · T2 범위 가드 · T3 유지비율 가드(72.43%<99%) · T4 교체(조회 11회 무중단, 71→80 원자 전환) · T5 백업 중복 가드 · T6/T7 롤백 후 지문 동일.

운영 절차서 `02-runbook.md` — 사전 점검 블록과 게시 상태 조회는 운영에서 읽기 전용으로 시험함(상한 항목만 불통과, 정상).

Jira: 384 에 OOM 이력·8g 권고, 460 에 다음 회차 항목(평가 재정의·D3·retrieve-k·174·--state) 공유.
