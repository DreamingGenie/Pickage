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
