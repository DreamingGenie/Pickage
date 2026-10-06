# 패키지 keywords 수집 가능성 검증 (AI 유사 패키지 학습용)

작성 2026-09-08 · 목적 **패키지 description + keywords로 가장 유사한 3개 패키지를 찾는 모델**의 학습 데이터 조달
수치는 전부 **2026-09-08 라이브 실측**(ecosyste.ms 호출 ~15건, npm registry 호출 ~13,000건). 선행 문서 `수집계획_downloads_npmAPI_260902.md`(속도 한도·순위표·다중 IP 절).

---

## 0. 결론

| 질문 | 답 |
|---|---|
| description은 따로 받아야 하나 | **아니다.** deps.dev `PackageVersions`의 `Description` 열을 이미 로컬(DuckDB/Parquet)에 갖고 있다. 모자란 건 **keywords만**이다 |
| keywords는 어디서 받나 | 둘 다 같은 값이다. 100개 대조에서 **일치 62 · 불일치 0 · 양쪽 모두 없음 38.** ecosyste.ms `keywords_array` = npm 최신 버전의 `keywords` |
| 얼마나 채워지나 | **원천 자체가 약 60%만 keywords를 갖고 있다.** 순위 1천 이내 70% → 10만 58% → 100만 58% → 300만 44%. 수집 속도가 아니라 **원천 결손이 상한**이다 |
| 결손 40%는 어떻게 하나 | ecosyste.ms 응답에만 있는 **GitHub topics**(`repo_metadata.topics`)가 결손 패키지의 **54%**를 채운다. keywords ∪ topics로 커버리지 **≈ 80%**. description(98%)은 거의 전부 있다 |
| 단기간에 얼마나 | **ecosyste.ms 목록 API 한 경로로 하루 안에 전 패키지**(582만 · 5,821페이지 · 8~10시간 · 전송량 약 100 GB). 상위 10만은 **10분**, 상위 100만은 **약 1.5시간** |
| 팀원 6명 분산이 필요한가 | **keywords 목적엔 불필요.** ecosyste.ms 한도(시간당 15,000건)에 걸리지 않고, npm registry도 단일 IP로 초당 30건이 지속돼 435만 개가 40시간이다. 분산은 "npm 원본으로 전수 + 하루 안에"를 원할 때만 의미가 있다(6명 × 7시간) |

**권고**: ecosyste.ms 목록 API로 **다운로드 순위 상위 100만**(월 다운로드 ≥ 87)까지 `name · keywords_array · description · repo_metadata.topics · repo_metadata.description · latest_release_number · downloads`를 받는다(1,000페이지, 약 1.5~2시간, 단일 PC). 학습 표본은 약 **60만(keywords 보유) ~ 80만(topics 포함)**이 나온다. npm registry는 신선도 대조·결손 재확인용 보조 경로로만 쓴다.

---

## 1. 원천별 실측

### 1-1. ecosyste.ms 목록 API — 순위·keywords·topics를 한 번에

`GET packages.ecosyste.ms/api/v1/registries/npmjs.org/packages?sort=downloads&order=desc&per_page=1000&page=N`
UA에 연락처를 넣으면 `x-ratelimit-tier: polite`, **시간당 15,000건**.

| 페이지(순위) | 소요 | 응답 크기 | keywords 보유 | 보유 시 평균 개수 | description 보유 |
|---|---:|---:|---:|---:|---:|
| 1 (1~1,000) | 3.4~8.4 s | 110 MB | **69.6%** | 7.8 | 94.2% |
| 50 (~50,000) | 6.5 s | 123 MB | 62.0% | 7.1 | 95.9% |
| 100 (~100,000) | 5.9 s | 105 MB | 57.5% | 8.2 | 93.5% |
| 300 (~300,000) | 4.2 s | 62 MB | 57.0% | 7.7 | 92.5% |
| 1,000 (~1,000,000) | 3.6 s | 26 MB | 57.5% | 6.5 | 89.1% |
| 3,000 (~3,000,000) | 6.0 s | 13 MB | 43.6% | 4.3 | 80.7% |
| 5,821 (마지막) | — | 200 KB+ | — | — | — |
| 6,000 | — | 빈 배열 | — | — | — |

- 레지스트리 총 **5,820,745개**(removed·unpublished 포함. deps.dev `_all_docs` 435만보다 많음). `keywords_count` 891,347.
- 응답이 큰 이유는 `repo_metadata`·`maintainers`·`rankings` 등 부수 필드다. 상위 300페이지는 100 MB급, 깊어질수록 줄어 전수 전송량은 **약 100~120 GB**로 추정된다(디스크에 남기는 건 필요 열만이라 수 GB).
- **09-02 순위표 수집 때 이 필드가 이미 응답에 있었으나 저장하지 않았다**(CSV 5열만). 상위 10만은 100페이지 재호출로 10분이면 끝난다.
- `last_synced_at`이 2026-06 이전인 패키지: 상위 10만에서 1~3%, 순위 300만 구간에서 10%. 최신 버전 번호가 npm과 다른 비율 **5/100**(수일~수주 지연). keywords는 자주 바뀌는 값이 아니라 학습용으로는 무시 가능.

**GitHub topics 보완 (2페이지 200개 표본, 순위 3천·6만 구간)**

| 항목 | 값 |
|---|---:|
| keywords 있음 | 117 / 200 (58.5%) |
| keywords 없음 | 83 |
| └ `repo_metadata.topics` 있음 | **45 (54%)** |
| └ `repo_metadata.description` 있음 | 70 |
| └ npm description 있음 | 68 |
| keywords·topics·description 중 하나라도 있음 | **197 / 200 (98.5%)** |

예: `@types/sockjs` keywords 없음 → topics `['definition','dts','types','typescript',…]`. `@react-types/shared` → `['accessibility','design-systems','react','ui-components','wai-aria']`. **npm registry엔 없는 값**이라 이 보완은 ecosyste.ms 경로에서만 가능하다.

### 1-2. npm registry — `GET registry.npmjs.org/{name}/latest`

최신 버전 문서 하나만 온다(**3~4.5 KB**, keywords·description 포함). 전체 문서(`/{name}`)는 express 기준 805 KB(readme·전 버전)라 쓰지 않는다. 축약 문서(`Accept: application/vnd.npm.install-v1+json`)엔 keywords·description이 **없다**.

| 실행 방식 | 요청 수 | 처리량 | 429 | 판정 |
|---|---:|---:|---:|---|
| 순차, 대기 없음 | 300 | 4.8 req/s | 0 | 지연 p95 0.27 s |
| 8 스레드 | 400 | 35 req/s | 0 | |
| **16 스레드** | 400 | 81 req/s | **146** | 한도 초과. 직후 수십 초 전부 429, 약 1분 안에 회복 |
| 6 스레드 지속 | 2,400 (81 s) | 29.7 req/s | 0 | |
| **6 스레드 지속** | **9,000 (302 s)** | **29.8 req/s** | **0** | 5분간 흔들림 없음 (블록별 28.5~30.8) |

- 한도 모양: **초당 30~35건은 지속, 80건은 즉시 차단**. `Retry-After` 없음. downloads API(분당 40건)와는 **별개 한도**이고 훨씬 넉넉하다.
- 9,000개 표본(순위 72,400~81,400) keywords 보유 **60.6%**, 404(unpublish) 0.6%. ecosyste.ms 수치와 일치.
- 5분 이상의 시간당·일간 한도는 미확인. 운영 시 **5 스레드(≈25 req/s) + 429 시 60초 휴식**으로 잡는다.

| 대상 | 요청 수 | 단일 IP (25 req/s) | 6명 분산 (rank % 6) |
|---|---:|---:|---:|
| 상위 10만 | 100,000 | **1.1 h** | 11 min |
| 상위 100만 | 1,000,000 | 11 h | 1.9 h |
| deps.dev 전수 435만 | 4,345,252 | **48 h** | **8 h** |

### 1-3. 그 외 경로

| 경로 | 결과 | 용도 |
|---|---|---|
| ecosyste.ms Open Data 덤프 `packages-2026-02-05.tar.gz` | **63.7 GB pg_dump**, 전 생태계 1,311만 패키지, PostgreSQL 복원 필요, 7개월 전 | 전수가 급할 때의 대안. 상위 100만이면 API가 더 싸다 |
| npm search `-/v1/search?text=keywords:react&size=250&from=N` | 250건/페이지, `from` 상한 없음(180,000까지 확인), 0.8 s, keywords·description 포함 | 특정 keyword 군 확장(예: `react` 188,060건). 전수 열거엔 부적합 |
| replicate/skimdb `_changes?include_docs=true` | **400** — 닫혀 있음 | 불가 |
| deps.dev API v3 `GetVersion` / BigQuery `PackageVersions` | Description 있음, **keywords 없음** | description은 여기 것을 그대로 쓴다 |

---

## 2. 데이터 의미 주의

- **keywords 결손 40%는 결손이 아니라 "저자가 안 썼음"이다.** 0개와 미수집을 구분해 `keywords_source ∈ {npm, github_topics, none}`으로 남긴다. 유사도 모델은 `none`에서 description만으로 추론하게 되므로, 평가 셋은 세 그룹을 층화해 뽑아야 한다.
- keywords는 **최신 버전 기준**이다. 버전마다 다를 수 있으나 이력은 필요 없다.
- 스팸 패키지: 순위 밖 롱테일엔 `how-long-should-it-take-to-clear-credit-report-…`류 SEO 스팸이 섞인다(`?keywords=react` 필터 첫 페이지가 그랬다). 상위 100만 컷 + `status` null 조건으로 대부분 걸러진다.
- ecosyste.ms `description`은 npm 것과 100/100 동일했다. 로컬 deps.dev Description과의 일치는 미대조(deps.dev도 npm에서 받으므로 같다고 본다).
- 라이선스: ecosyste.ms 데이터는 **CC BY-SA 4.0** — 발표·저장소에 출처 표기 필요. npm registry 메타데이터는 각 패키지 라이선스와 무관한 공개 메타데이터다.

---

## 3. 실행안

| 단계 | 무엇 | 호출 | 소요 | 산출 |
|---|---|---:|---:|---|
| 1 | ecosyste.ms 상위 100만 (1,000페이지, 필요 열만 jsonl.gz로 저장, 페이지 단위 체크포인트) | 1,000 | 1.5~2 h · 전송 ≈ 60 GB | `keywords/run=2026-09-xx/part-*.jsonl.gz` |
| 2 | DuckDB 조인: deps.dev `Description` + keywords_array + topics → `package_text` Parquet | 0 | 분 단위 | name, description, keywords[], topics[], keywords_source, rank, downloads_last_month |
| 3 (선택) | npm `/latest`로 keywords `none`인 패키지만 재확인(약 40만 건) | 400k | 4.4 h (단일) | 지연 동기화 보정 |
| 4 (선택) | 전수가 필요해지면 ecosyste.ms 1,001~5,821페이지 추가 | 4,821 | +6~8 h | 롱테일 |

팀원 분산 스크립트는 **3단계(npm 재확인)나 4단계 전수를 하루 안에 끝내려 할 때** 만든다. 형태는 `수집계획_downloads_npmAPI_260902.md` §9-5와 같다(`--worker i --of N`, rank 라운드로빈, 캠퍼스 NAT 공유 IP 주의). ecosyste.ms 경로는 시간당 15,000건 한도가 남아돌아 분산해도 얻는 게 없고, 오히려 100 GB 전송을 여러 집 회선에 나누는 효과만 있다.

---

## 4. 결손 보완 — GitHub topics 처리 규칙 (2026-09-08 추가)

수집기 `pipeline/collectors/keywords/collect_keywords.py`가 `repo.topics`를 함께 저장한다. 학습 데이터로 합칠 때의 규칙.

### 4-1. 출처 우선순위와 표기

| `keywords_source` | 조건 | 비율(상위 10만 표본) |
|---|---|---:|
| `npm` | `keywords` 비어 있지 않음 | ≈ 60% |
| `github_topics` | `keywords` 없음, `repo.topics` 있음 | ≈ 22% |
| `none` | 둘 다 없음 → description만 | ≈ 18% |

keywords가 있으면 topics는 **덧붙이지 않는다**(패키지 단위 신호를 저장소 단위 신호로 희석시키지 않기 위해). topics는 결손 패키지에서만 keywords 자리에 들어가며, 출처 열을 반드시 남긴다. 평가 셋은 이 세 그룹을 층화 추출한다 — `none` 그룹 정확도가 별도로 보여야 한다.

### 4-2. topics가 keywords와 다른 점 (그래서 그대로 못 쓴다)

1. **저장소 단위다.** 모노레포(`@babel/*` 150여 개, `@types/*` 는 DefinitelyTyped 한 저장소)의 패키지는 전부 같은 topics를 받는다. 같은 `repo.full_name`을 공유하는 패키지 수가 많을수록 변별력이 없다.
2. **GitHub 관행어가 섞인다.** `hacktoberfest`, `good-first-issue`, `help-wanted`, `javascript`, `nodejs`, `npm`, `typescript`, `npm-package`, `library` 등은 유사도에 기여하지 않는다.
3. **표기가 다르다.** topics는 소문자·하이픈 고정(`react-components`), keywords는 자유 표기(`React Components`, `react_components`, `reactcomponents`).
4. **갱신 시점이 다르다.** `repo_metadata_updated_at`이 오래됐거나 `repo.archived`·`repo.fork`가 true면 신뢰를 낮춘다.

### 4-3. 처리 절차

```
1) 정규화(keywords·topics 공통): lower → 공백·언더스코어 → 하이픈 → 양끝 하이픈 제거 → 중복 제거
2) 불용어 제거(topics만): {hacktoberfest, good-first-issue, help-wanted, javascript, js, nodejs, node, npm,
   npm-package, typescript, library, package, module, open-source, awesome} ∪ 저장소 빈도 상위 20개를 눈으로 확인해 추가
3) 모노레포 감쇠: repo_pkg_count = 같은 repo.full_name을 가진 패키지 수
   - repo_pkg_count ≤ 3  → topics 그대로
   - 4 ~ 20             → topics 가중 0.5 (또는 상위 5개만)
   - > 20 (DefinitelyTyped·babel·aws-sdk 등) → topics 버림 → keywords_source = none, 대신 repo.description 을 description 뒤에 붙임
4) 신뢰도 강등: repo.archived or repo.fork or repo_metadata_updated_at < 1년 전 → 가중 0.5
5) 학습 텍스트 = description + " " + " ".join(keywords or weighted topics)
   임베딩 모델(예: sentence-transformers)로 벡터화 → 코사인 상위 3.
   BM25/TF-IDF를 쓸 경우 topics 토큰에 IDF 외 위 가중을 곱한다.
```

`@types/*`는 별도 규칙이 맞다: 이름에서 원 패키지(`@types/sockjs` → `sockjs`)를 뽑아 **원 패키지의 keywords를 상속**시키는 편이 topics(`definition, dts, types`)보다 훨씬 정확하다. 상위 10만에 `@types/*`가 수천 개라 이 규칙 하나로 `none` 그룹이 눈에 띄게 줄어든다.

### 4-4. 검증 방법

- keywords·topics 둘 다 있는 패키지(≈ 30%)에서 topics만으로 유사 3개를 뽑아 keywords 기준 결과와 겹침(Jaccard)을 잰다. 이 값이 topics 대체의 실제 품질이다.
- `none` 그룹은 description만으로 뽑고, 팀원 5명이 50개 표본을 손으로 채점한다(맞다/그럴듯하다/틀렸다).

---

## 부록 — 재현

```bash
# ecosyste.ms 목록 1페이지 (keywords_array·description·repo_metadata.topics 포함, ~110 MB)
curl -s -A "oss-shift-a506 (contact@email)" "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages?sort=downloads&order=desc&per_page=1000&page=1" | head -c 2000
# npm 최신 버전 문서 (3~4 KB)
curl -s "https://registry.npmjs.org/@babel%2Fcore/latest" | head -c 600
# npm search: keyword 군
curl -s "https://registry.npmjs.org/-/v1/search?text=keywords:react&size=250&from=10000" | head -c 400
```

스크래치 스크립트: `probe_eco.py`·`probe_eco2.py`·`probe_npm.py`·`probe_npm2.py`·`probe_npm3.py`·`probe_npm5min.py`·`probe_consist.py`·`probe_topics.py`·`probe_dump3.py`(세션 임시 폴더, 저장소 미포함). 5분 지속 실측 표본 9,000건은 `kw_5min_sample.jsonl.gz`.
