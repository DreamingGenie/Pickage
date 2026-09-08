# 패키지 keywords 수집 결과 · 학습 데이터 결합 전 프로파일

작성 2026-09-08 · 대상 `data/keywords/raw/run=2026-09-08/` (ecosyste.ms 다운로드 순위 상위 100만) · 계획서 `검증_keywords_수집가능성_260908.md`
수치는 전부 **2026-09-08 DuckDB 실측**이다.

---

## 0. 결론

- **수집 완료.** 1,000페이지 · 1,000,000행 · 104분 · 429 0건 · 전송 53.9 GB → 저장 179 MB(jsonl.gz, 필요 열만).
- 학습 표본: **keywords + description 둘 다 있는 패키지 531,014개**, GitHub topics까지 허용하면 **603,045개**. 텍스트 신호가 전혀 없는 건 13,781개(1.4%).
- 결합 전에 반드시 걸러야 할 것 **두 가지**: ① `status` removed·unpublished 약 7.7만 개(7.7%) ② **tea 스팸 농장** — 저장소 하나에 수천 개 패키지가 매달린 자동 생성 군집(`cookiegraves/rarerteat` 8,400개 등). 순위 58~64만 구간의 keywords 보유율 급락(56% → 30%)은 롱테일 특성이 아니라 이 스팸이 원인이다.
- description은 ecosyste.ms 값(91.0%)을 1순위, deps.dev `Description`(87.5%)을 보조로 쓰면 **92.0%**, 저장소 description까지 더하면 93.1%.
- **결합 완료(§4)**: `package_text_2026-09-08.parquet` **86 MB** · 922,322행 · 스팸 표시 23,589 · 학습 핵심 표본 **512,295**(keywords ∧ description) / 확장 **552,650**(topics 포함).

---

## 1. 수집 실행 요약

| 항목 | 값 |
|---|---|
| 기간 | 09-08 10:35 → 12:19 KST, **104분** (페이지당 평균 6.2 s. 상위 100페이지는 110~180 MB라 10~15 s, 깊은 페이지는 15~30 MB라 3~5 s) |
| 호출 | 1,000건 + 재시도 2건(연결 끊김 `ConnectionError` 1 · `ChunkedEncodingError` 1, 자동 복구). 429 **0건**. `x-ratelimit-remaining`은 14,900 위에서 유지 |
| 전송·저장 | 응답 합계 53.9 GB → part 파일 1,000개 179 MB. 원본은 보존하지 않고 `slim()`이 고른 열만 |
| 중복 | 199행(0.02%). 수집 중 downloads 갱신으로 페이지 경계가 밀린 것. `page_log` 역행 2건(49→50, 89→90페이지)과 일치. 적재 시 `name` 기준 최신 `fetched_at` 유지 |
| 최저 순위 | 1,000,000위 = 월 다운로드 **87** |

## 2. 데이터셋 형태

### 2-1. 열 (한 줄 = 패키지 1개)

`rank · name · namespace · description · keywords[] · downloads_last_month · dependent_packages_count · dependent_repos_count · versions_count · latest_release_number · latest_release_published_at · first_release_published_at · licenses · status · repository_url · homepage · maintainers_count · last_synced_at · repo_metadata_updated_at · repo{full_name, description, topics[], language, stargazers_count, forks_count, archived, fork, pushed_at, default_branch, license} · page · fetched_at`

### 2-2. 순위 10만 구간별 보유율

| 순위 구간 | 월 다운로드 | keywords | topics | keywords ∪ topics | description(eco) | removed·unpublished |
|---|---:|---:|---:|---:|---:|---:|
| 1 ~ 10만 | 31억 ~ 11,974 | **62.9%** | 53.0% | **81.2%** | 95.0% | 0.9% |
| 10 ~ 20만 | ~ 2,593 | 56.0% | 34.3% | 67.4% | 92.3% | 2.2% |
| 20 ~ 30만 | ~ 1,146 | 55.5% | 30.2% | 65.3% | 92.9% | 4.7% |
| 30 ~ 40만 | ~ 620 | 56.7% | 26.9% | 64.5% | 92.3% | 5.6% |
| 40 ~ 50만 | ~ 371 | 57.4% | 24.8% | 64.2% | 92.1% | 6.6% |
| 50 ~ 60만 | ~ 253 | 52.5% | 20.0% | 58.2% | 89.3% | 7.5% |
| **60 ~ 70만** | ~ 210 | **37.0%** | **10.4%** | **39.8%** | 82.8% | 13.6% |
| 70 ~ 80만 | ~ 150 | 52.6% | 19.3% | 57.8% | 91.2% | 12.9% |
| 80 ~ 90만 | ~ 110 | 54.8% | 19.3% | 59.9% | 90.8% | 9.5% |
| 90 ~ 100만 | ~ 87 | 51.7% | 17.3% | 56.2% | 91.3% | 14.0% |

keywords는 상위 10만 밖에서 **55% 안팎으로 평탄**하다(사전 실측 57%와 일치). topics는 순위가 내려가며 53% → 17%로 빠르게 준다 — 롱테일은 GitHub 저장소 연결 자체가 드물기 때문. 60~70만 구간의 급락은 §3-2 스팸이다.

### 2-3. description 결손 — deps.dev와 대조

| 항목 | 개수 | 비율 |
|---|---:|---:|
| 수집 | 1,000,000 | |
| deps.dev `PackageVersions`(08-31 스냅샷)에 존재 | 946,865 | 94.7% |
| description — ecosyste.ms | 909,988 | 91.0% |
| description — deps.dev 최신 버전 | 874,842 | 87.5% |
| **둘 중 하나** | **920,117** | **92.0%** |
| + 저장소 description(`repo.description`) | 931,089 | 93.1% |
| description·keywords·topics·repo.description 전부 없음 | 13,781 | 1.4% |
| **keywords ∧ description** (핵심 학습 표본) | **531,014** | 53.1% |
| (keywords ∨ topics) ∧ description | **603,045** | 60.3% |

- 두 원천에 모두 description이 있을 때 **99.3% 동일**(상위 7만 표본 65,451개 중 471개만 상이 — 버전 동기화 시차). ecosyste.ms 값이 keywords와 같은 스냅샷이므로 1순위로 쓴다.
- deps.dev에 없는 53,135개(5.3%)는 removed·unpublished와 08-31 이후 신규 패키지다.
- 결손의 실체는 **모노레포 내부 패키지**(`@jest/*`, `@wix/*` 200개, `@tamagui/*`, `@teambit/*`, `@parcel/*`)다. 저자가 package.json에 description을 쓰지 않은 것이라 어느 원천에도 없다. `repo.description`으로 절반이 채워진다.

---

## 3. 결합 전에 알아야 할 것

### 3-1. status — 0이 아니라 없음

`status` 표시 110,094개(11.0%): deprecated 32,605 · **removed·unpublished 약 77,500**. removed·unpublished는 npm에서 사라진 이름이라 유사 패키지 추천 대상이 될 수 없다 → 학습·후보 양쪽에서 제외. deprecated는 남긴다(폐기 패키지의 대체품 찾기가 서비스 기능이므로 오히려 필요하다).

### 3-2. tea 스팸 농장 — 저장소 하나에 수천 패키지

| 저장소 | 패키지 수 | keywords 보유 |
|---|---:|---:|
| `cookiegraves/rarerteat` | 8,400 | 2.5% |
| `Adamittem/pubteahy` | 6,796 | 0.0% |
| `an-node/npmteanodess` | 2,661 | 8.7% |
| `blockReal/asjustmeteai` | 1,267 | — |
| `anitashuh/bearteamorph` | 1,225 | — |
| (정상 대조) `DefinitelyTyped/DefinitelyTyped` | 7,444 | 0% (topics로 대체) |
| (정상 대조) `fontsource/font-files` | 2,377 | 100% |

이름에 `tea`가 들어가는 저장소들은 tea 프로토콜 보상 노림용 자동 생성 패키지다. 순위 58~64만 구간에 몰려 있고(§2-2 급락 구간), 이 구간의 서로 다른 저장소 수가 5,300 → 2,600으로 반토막 나는 것이 그 흔적이다. **저장소 단위로 걸러야 한다**: 같은 `repo.full_name`에 패키지 100개 이상이면서 keywords 보유율 15% 미만이면 스팸으로 표시. DefinitelyTyped처럼 keywords 0%지만 정상인 경우는 `@types/` 접두로 예외 처리.

### 3-3. 모노레포 — 저장소 단위 신호의 희석

| 같은 저장소의 패키지 수 | 저장소 | 패키지 |
|---|---:|---:|
| 1~3 | 367,262 | 397,154 |
| 4~20 | 12,795 | 95,606 |
| >20 | 1,807 | **141,878** |

패키지 14만 개(14%)가 20개 이상 묶인 모노레포에 속한다. 이들의 `repo.topics`·`repo.description`은 패키지가 아니라 저장소를 설명하므로, `검증_keywords_수집가능성_260908.md` §4-3 감쇠 규칙(>20이면 topics 버림)을 그대로 적용한다.

### 3-4. keywords 어휘

토큰 5,167,995개 · 고유 325,377개. 상위: `typescript` 56,680 · `react` 55,684 · `cli` 30,594 · `ai` 22,469 · `javascript` 21,787 · `mcp` 20,685 · `plugin` 20,535 · `api` 17,088 · `css` 16,375 · `vue` 15,361. `ai`·`mcp`·`claude`(11,953)가 상위 15에 든 것은 2025~26년 발행 편향이다. 유사도 모델에서 `typescript`·`javascript`·`node`처럼 변별력 없는 상위 토큰은 IDF가 자연히 눌러 주지만, TF-IDF 대신 임베딩을 쓴다면 불용어로 빼는 편이 안전하다.

### 3-5. 신선도

`last_synced_at`이 2026-06 이전인 패키지 92,610개(9.3%). keywords는 자주 바뀌지 않으므로 학습용으로는 무시하되, 서비스에서 최신 버전 번호를 보여줄 때는 npm registry `/latest`로 재확인한다.

---

## 4. 결합 결과 — `package_text_2026-09-08.parquet` (`pipeline/collectors/keywords/build_package_text.py`, 09-08 13:05 실행)

### 4-1. 규칙

```
1) 중복 제거: name 기준 최신 fetched_at                                  1,000,000 → 999,801
2) 제외: status IN ('removed','unpublished')                              → 922,322
3) 스팸 표시(행은 남기고 is_spam만): 같은 repo.full_name에 패키지 ≥ 100
   AND keywords 보유율 < 15% AND 저장소 최대 dependents < 20
   AND (저장소 별 < 10 OR 전 패키지 발행 기간 < 90일) AND name NOT LIKE '@types/%'   → is_spam 23,589 (23개 저장소)
4) description = coalesce(ecosyste.ms, deps.dev 최신 버전 Description, repo.description) + description_source
5) keywords_source = npm (keywords 있음) / github_topics (topics 있고 저장소 패키지 ≤ 20) / none
   topics: 소문자·공백 제거, 불용어 27개 제거(hacktoberfest·javascript·typescript·nodejs·library·framework …), 중복 제거
6) 출력 zstd Parquet 22열: name, rank, downloads_last_month, dependent_packages_count, status, description,
   description_source, keywords[], topics[], keywords_source, repo_full_name, repo_pkg_count, repo_language,
   repo_stars, repo_archived, is_spam, latest_release_number, latest_release_published_at, licenses,
   repository_url, last_synced_at, fetched_at
```

스팸 규칙을 처음엔 "패키지 ≥ 100 · keywords < 15%"만으로 잡았더니 `aws/aws-sdk-js-v3`(675개) · `expo/google-fonts`(951개) · `adobe/react-spectrum` · `microsoft/fluentui` · `parcel-bundler/parcel` 같은 정상 모노레포 33곳 7,368개가 함께 걸렸다. 스팸 농장은 **아무도 의존하지 않고(dependents 0) · 별 0 · 전 패키지가 1~3개월 안에 발행**된다는 점이 다르다. 그 셋을 더하자 23곳 23,864개만 남고 정상 모노레포는 전부 풀렸다. 유일한 예외 `deepseek-ai/deepseek-harness`(1,153개, 별 20만)는 저장소 메타데이터가 유명 저장소를 가리키지만 24일 안에 전부 발행·dependents 0이라 스팸으로 유지된다.

저장소 연결이 없는 스코프형 스팸(`@ffras4vnpm/exercitationem-officia-id-ea`처럼 라틴어 무작위 이름)은 이 규칙에 안 잡히지만, description·keywords·topics가 전부 없어 아래 "텍스트 없음" 그룹으로 빠지므로 학습 셋에는 들어오지 않는다.

### 4-2. 결과

| 구분 | 개수 |
|---|---:|
| 행 (removed·unpublished 제외 후) | 922,322 |
| `keywords_source` = npm / github_topics / none | 516,008 / 40,441 / 365,873 |
| `description_source` = npm / depsdev / repo / none | 840,467 / 10,062 / 10,568 / 61,225 |
| `is_spam` | 23,589 |
| **학습 핵심: keywords ∧ description, 스팸 아님** | **512,295** |
| **학습 확장: (keywords ∨ topics) ∧ description, 스팸 아님** | **552,650** |
| 평가 층: description만 (keywords·topics 없음), 스팸 아님 | 284,981 |
| 텍스트 없음 (description·keywords·topics 전부 없음) | 57,882 |

파일: `data/keywords/package_text/package_text_2026-09-08.parquet` **86.2 MB** (zstd, 93 B/행) + `summary_2026-09-08.json`. 같은 데이터가 snappy면 148 MB, 비압축 jsonl 371 MB, CSV(최소 6열) 168 MB. description 평균 69자, keywords 평균 5.1개(76자), topics 평균 3.0개.

AI 파트 전달 시 권고: `WHERE NOT is_spam AND description IS NOT NULL AND keywords_source <> 'none'`으로 55만 행을 학습에, `keywords_source = 'none'` 28만 행은 description만으로 추론하는 평가 층으로 쓴다. `topics`는 `keywords`보다 낮은 가중치(저장소 단위 신호). 순위 컷은 두지 않았다 — 스팸을 걸러내면 롱테일의 keywords 보유율(52~55%)이 상위 구간과 다르지 않아 컷의 근거가 없다.

---

## 부록 — 재현

프로파일 쿼리는 세션 스크래치 `final_profile.py`(DuckDB, `read_json` + `versions_full` Parquet 조인, 약 1분). 상태 확인은 `pipeline/collectors/keywords/status.py --run 2026-09-08`.
