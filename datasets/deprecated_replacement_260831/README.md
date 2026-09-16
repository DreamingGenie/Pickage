# 폐기(deprecated) npm 패키지 → 대체 패키지 데이터셋

deps.dev BigQuery(`PackageVersions`, System='NPM') 2026-08-31 스냅샷에서, **최신 릴리스가 폐기 표시돼 있고 폐기 문구에서 대체 패키지명이 추출된** 패키지를 모았다.
같은 내용을 CSV(엑셀·공유용)와 JSONL(AI 학습·프로그램 입력용) 두 형식으로 저장했다. 행은 동일하다.

| 파일 | 행 | 용도 |
|---|---|---|
| `deprecated_replacement_20260831.csv` | 28,241 | 엑셀·구글시트. UTF-8 BOM. 배열 열(`licenses`, `keywords`)은 `\|`로 이어 붙임. 불리언은 `true`/`false` |
| `deprecated_replacement_20260831.jsonl` | 28,241 | 한 줄 = 패키지 하나(JSON). 배열·null 그대로. 학습 데이터로 바로 투입 가능 |

생성 스크립트: `pipeline/duckdb/build_deprecated_dataset.py` (입력 `data/raw/versions_full`·`data/raw/pkg_project`, DuckDB, 약 130초). 재생성하면 같은 결과가 나온다.

같은 내용의 Parquet 은 빌더가 `data/deprecated_replacement/` 에 만들고(git 제외),
서버 MinIO `pickage-curated/depsdev/v1/deprecated-replacement/snapshot=2026-08-31/run_id=deprecated-replacement-20260914-v1/`
에 보관한다. 넣는 방법은 [pipeline/minio/README.md](../../pipeline/minio/README.md) 의
"파생 데이터셋 입고 실행" 절에 있다.

## 열 설명

| 열 | 뜻 | 출처 |
|---|---|---|
| `name` | 폐기된 패키지 이름 | PackageVersions.Name |
| `last_version` | 종료 시점 버전. `VersionInfo.Ordinal`이 가장 큰 릴리스(prerelease 제외) | PackageVersions |
| `last_version_published_at` | 그 버전의 발행 시각(UTC). 사실상 "마지막으로 살아 있던 때" | UpstreamPublishedAt |
| `first_published_at` | 첫 버전 발행 시각. 수명 = last − first | UpstreamPublishedAt 최소값 |
| `versions_count` / `releases_count` | 전체 버전 수 / prerelease 제외 릴리스 수 | 집계 |
| `deprecated_versions_count` | 폐기 표시된 버전 수. `versions_count`와 같으면 패키지 전체 폐기, 작으면 일부 버전만 폐기 | Deprecated IS NOT NULL 집계 |
| `description` | 종료 시점 버전의 설명 | Description |
| `keywords` | **비어 있음(null).** deps.dev BigQuery 30개 테이블 어디에도 keyword 열이 없다(2026-09-07 INFORMATION_SCHEMA 확인). 외부 API(ecosyste.ms 또는 npm registry)로 채울 예정 | — |
| `deprecated` | 폐기 문구 원문. 관리자가 `npm deprecate`로 남긴 자유 서술. 줄바꿈·이모지 포함 가능 | Deprecated |
| `replacement` | 폐기 문구에서 정규식으로 뽑은 **대체 패키지명**(소문자). 첫 후보 하나만. "A or B"면 A | 파생 |
| `replacement_alive` | 대체 패키지의 최신 릴리스가 폐기되지 **않았으면** true. false면 대체 대상도 죽은 것(2,325건) | 파생 |
| `replacement_last_version` | 대체 패키지의 최신 릴리스 버전 | PackageVersions |
| `replacement_confidence` | `high`: 이름에 `@ / . - 숫자`가 있거나 문구에서 따옴표·백틱으로 감싸져 있음(25,601). `medium`: 평범한 소문자 단어 하나(2,640). medium은 일반 영단어 오탐 가능성이 남아 있음 | 파생 |
| `replacement_source_repo` | **대체 패키지**의 소스 저장소 URL 원문. `git+ssh://`·`git@host:`·`owner/repo` 약식이 섞여 있다(24,777) | PackageVersions.Links |
| `replacement_repo_url` | **대체 패키지**의 저장소 주소를 `https://호스트/owner/repo`로 정리한 값(24,868 = 88.1%). GitHub 24,440 · GitLab 306 · Bitbucket 122 | PackageVersionToProject |
| `source_repo` | 폐기된 패키지의 소스 저장소 URL(`Links` 중 SOURCE_REPO). 없으면 null | Links |
| `licenses` | 라이선스 목록 | Licenses |
| `snapshot_at` | 원천 스냅샷 날짜 | SnapshotAt |

## 추출 규칙과 정밀도

1. 정규식: `(use|switch to|replaced by|moved to|renamed to|migrate to|in favo(u)r of|superseded by|merged into|successor is|replaced with|now lives at|now)` 뒤에 오는 첫 npm 이름 형태 토큰.
2. 불용어 약 200개 제외(the, it, npm, available, distributed, github …). npm에는 이런 단어 이름의 스쿼팅 패키지가 실제로 있어 "실존 검사"만으로는 못 걸러서 명시 목록이 필요했다.
3. 후보가 npm에 실존하는 패키지여야 하고, 자기 자신은 제외.
4. 무작위 30건 눈검사 기준 정밀도 약 85~90%. `replacement_confidence = 'high'`만 쓰면 더 높다.

## 대체 패키지 저장소 주소를 만든 방법

`replacement_repo_url`은 새로 수집한 값이 아니라 이미 받아 둔 `data/raw/pkg_project`
(deps.dev `PackageVersionToProject`)에서 붙인 것이다. 대체 패키지의 릴리스 중
`ordinal`이 가장 큰 것에 걸린 `RelationType = 'SOURCE_REPO_TYPE'` 매핑을 쓴다.

`versions_full`의 `source_repo` 원문을 직접 파싱하지 않은 이유는 형식이 한 가지가
아니기 때문이다 — `git+https://`, `git://`, `git+ssh://`, `git@github.com:owner/repo.git`,
호스트가 없는 `owner/repo` 약식, 심지어 저장소가 아닌 npm 패키지명까지 들어 있다.
deps.dev는 이것을 이미 `owner/repo`로 정규화해 두었다.

호스트는 `ProjectType`으로 정한다(`GITHUB` → github.com 등). 원문이 함께 있는 2만여
건을 대조했을 때 둘이 어긋나는 행은 없었다. self-hosted GitLab은 `GITLAB`으로 분류되지
않고 매핑 자체가 빠지므로 잘못된 gitlab.com 주소가 만들어지지 않는다.

매핑이 없어 `replacement_repo_url`이 비는 334건은 원문 `replacement_source_repo`만
있다(self-hosted 호스트, monorepo 등). 필요하면 그쪽을 직접 파싱한다.

## 모집단 대비 위치 (2026-08-31, npm 최신 릴리스 기준)

| 구분 | 수 |
|---|---|
| npm 패키지 전체 | 11,081,241 |
| 최신 릴리스가 폐기된 패키지 | 131,665 |
| 그중 npm 운영진 일괄 문구(스팸·계정 삭제, 대체 정보 없음) | 48,423 |
| 정규식이 대체 후보를 잡은 것 | 41,639 |
| **이 데이터셋(불용어·실존·자기제외·npm 이름 규격 통과)** | **28,241** |

## 한계

- **폐기 선언 시각은 없다.** npm 자체에 폐기 시각이 없고 deps.dev도 "지금 폐기 표시가 있나"만 준다. `last_version_published_at`은 마지막 발행 시각이지 폐기 시각이 아니다.
- 대체 대상을 적지 않은 폐기(moment, request 등 유명 사례 다수)는 여기 없다. 그 부류는 의존성 이동 데이터로 봐야 한다.
- 대체 대상이 패키지가 아닌 경우(`String.prototype.padStart()`, GitHub 이슈 URL)는 제외됐다.
