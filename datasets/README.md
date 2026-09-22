# datasets — 팀 공유용 파생 데이터 (git 추적)

`data/`(gitignore)의 로컬 원본에서 `pipeline/duckdb/build_*.py`로 만든 **작은 파생 데이터**를 둔다. 팀원이 clone만 하면 바로 열어 볼 수 있어야 하는 것만 넣는다. 원본·중간 결과(수십 MB 이상, 재생성 가능)는 `data/`에 두고 GCS로 공유한다.

| 폴더 | 내용 | 생성 | 설명 |
|---|---|---|---|
| `dependent_transitions_260917/` | 패키지별 **유지·유입·이탈·관측 불가** — 상위 10만 대상 × `regular`/`peer`/`optional` × `1y`/`3y`/`5y`. "X 를 쓰던 사람들이 이 구간에 어떻게 움직였나"(기능-08) | `pipeline/duckdb/build_dependent_transitions.py` | 폴더 README. 본체 899,964행은 `data/dependent_transitions/*.parquet`(git 미추적), 여기 CSV 는 **상위 5,000 대상 표본**이라 합계를 내면 안 된다. **관측 불가를 유지로 세지 말 것** — 1년 구간에서 75.3%가 움직일 기회조차 없었다 |
| `dependent_transitions_exp460k_260922/` | 같은 계산의 **확장 대상 468,519개** 회차. 상위 10만에 묶여 있어 확장 목록의 신규 36.9만에서 화면이 비던 것을 넓혔다 (S15P21A506-454) | `build_dependent_transitions.py --targets … --label exp460k_260922` | 폴더 README. 열 구성은 위와 같고 **차이는 대상 목록뿐**. 겹치는 899,964행이 열 15개 전부 일치함을 확인했다. **이 회차가 운영 `dependent_transition` 을 전량 교체한다** — 위 폴더 §4 의 수치는 상위 10만 기준이라 섞어 쓰지 말 것 |
| `deprecated_replacement_260831/` | 폐기(deprecated) npm 패키지 → 대체 패키지 28,241쌍. CSV(공유용)·JSONL(학습용) | `pipeline/duckdb/build_deprecated_dataset.py` | 폴더 README |
| `feature_candidates_260908/` | AI 학습 보강 변수 후보 3종(이동쌍·dependencies·peerDependencies) 표본 각 100건 | `pipeline/duckdb/build_feature_candidates.py` | 폴더 README |
| `migration_pairs_260908/` | 마이그레이션 이동쌍 — **실행용 의존** 기준, npm 전수. strict·recommended·all 3종 + stats.json | `pipeline/duckdb/build_migration_pairs.py` | 폴더 README, 비개발자용 `migration_pairs_all_안내.md` |
| `migration_pairs_dev_260914/` | 같은 계산의 **개발용 의존(devDependencies)** 기준, 상위 10만. 도구 계열 이동(enzyme·tslint·mocha·jest)은 여기에만 있다 | `build_migration_pairs.py --source registry --kind dev` | 폴더 README. **위 폴더와 모집단이 달라 수치를 더하거나 lift를 비교하지 말 것** |
| `package_dependents_260915/` | 패키지별 **dependents(의존자) 이름 목록** — 상위 10만 대상 × `regular`/`peer`/`optional`. 보완재 감점 관문(S15P21A506-173)용 | `pipeline/duckdb/build_package_dependents.py` | 폴더 README. 배열 본체는 `data/package_dependents/*.parquet`(git 미추적), 여기엔 수만 담은 요약 CSV. **devDependencies가 원천에 없어 개발 도구는 과소 계상된다** |
| `package_dependents_candidate_pool_260916/` | 같은 계산의 **AI 후보 풀 29,310개** 대상 회차. 그중 11,297개(38.5%)가 상위 10만 밖이라 위 폴더로는 답할 수 없어 따로 냈다 | `build_package_dependents.py --targets … --label candidate_pool_260916` | 폴더 README. 열 구성은 위와 같고 **차이는 대상 목록뿐**. 겹치는 54,039행의 값이 위 회차와 전부 일치함을 확인했다. 순위 밖 패키지는 `download_rank`·`ecosystems_dependent_count`가 NULL |
| `package_dependents_exp460k_260922/` | 같은 계산의 **확장 대상 468,519개** 회차. 유지·유입·이탈 확장 회차와 짝이다 (S15P21A506-454) | `build_package_dependents.py --targets … --label exp460k_260922` | 폴더 README + `stats.json` 만 추적한다 — **요약 CSV 는 50 MB 라 `.gitignore` 에 있다.** 겹치는 299,988행이 일곱 열 전부 일치함을 확인했다. 대상의 78.7%가 순위 밖이라 분위수가 낮다(regular p50 0) — 위 회차와 분위수를 비교하지 말 것 |
| `peer_similarity_260914/` | 대체 후보 **peer 의존 유사도** — 쌍 1행(양쪽 peer 목록·교집합·Jaccard·판정) 53,155 + 패키지 1행 57,820. "A가 B를 대체할 수 있나"의 호환성 특징. `--scope all` 로 만든 npm 전수 peer 목록(81.4만/53.2만)은 Parquet 만 있고 여기엔 집계 JSON 만 있다(폴더 README §6) | `pipeline/duckdb/build_peer_similarity.py` | 폴더 README. **`peer_jaccard` 의 NULL 을 0 으로 채우지 말 것** — 쌍의 60%가 비교 불가이고 그건 유사도 0이 아니다. **전수는 그대로 쓰지 말 것** — 23.9%가 릴리스 1개짜리다. 2026-09-15 정정으로 가짜 노드 219,299행을 뺐다(폴더 README §6-2) |
| `targets/rank_top100k_20260902.csv` | ecosyste.ms 다운로드 순위 상위 10만. **2026-09-22 이전 모든 수집·파생의 대상** | ecosyste.ms 목록 API 100페이지 (`pipeline/collectors/downloads/README.md`) | `targets/README.md` |
| `targets/candidate_pool_260916.csv` | AI 파트가 준 유사 패키지 후보 풀 29,310개 (`name` 한 열) | AI 파트 제공 | `targets/README.md` |
| **`targets/expanded_468k_20260922.csv`** | **확장 대상 정본 468,519개** — 상위 10만 ∪ 순위 100만 내 비스코프 전부 ∪ AI 후보 풀. 2026-09-22 이후 파생·AI 배치·이력 재적재의 대상 | `package_text_2026-09-08.parquet` + 위 두 파일의 합집합 (S15P21A506-451) | `targets/README.md` §3 — 선정 규칙, **스코프 롱테일 431,715개를 왜 뺐는지**, `rank`를 새로 매긴 이유. **BOM 없음(수집기 입력)** |
| `targets/expanded_468k_additions_20260922.csv` | 정본 − 상위 10만 = 368,523개. **수집기 전용** — downloads run `2026-09-22-additions`, registry 재수집 입력 | 위 정본에서 `rank_top100k` 이름을 뺀 것 | `targets/README.md` §3-6. 파생 빌더에는 이 파일이 아니라 정본을 준다 |

규칙

- 폴더 이름 뒤에 원천 스냅샷 또는 생성 날짜(`YYMMDD`)를 붙인다. 같은 데이터를 다시 만들면 새 폴더가 아니라 같은 폴더를 덮어쓴다.
- CSV는 UTF-8 BOM, 배열 열은 `|`로 이어 붙인다(엑셀·구글시트 호환).
- 각 폴더에 README를 두고 열 의미·생성 방법·한계를 적는다.
- ecosyste.ms에서 온 값(`targets/`, keywords)은 CC BY-SA 4.0이므로 발표·저장소에 출처를 표기한다.
