# Pickage package·version Curated 전처리

MinIO에 보존한 deps.dev npm 원본에서 **PostgreSQL의 `package`·`version`에 넣을 데이터**를 만드는 전처리다.
Bronze는 수집한 원본, Curated는 아래 규칙을 적용한 정제 결과를 뜻한다.
결과는 행과 컬럼을 가진 Parquet 파일로 저장하며, 이 작업 자체가 PostgreSQL에 테이블을 만들거나 데이터를 넣지는 않는다.

2026-09-07 기준 로컬 전체 데이터 실행과 MinIO 저장·재검증을 완료했다.
완료 실행은 `curated-20260907-v2`이며, **package 11,080,940행, version 54,188,349행**을 생성했다.

## 1. 작업 범위와 처리 흐름

### 입력과 출력

| 구분 | 데이터 | 역할 |
| --- | --- | --- |
| 입력: `pickage-raw` | `versions_full` | 패키지명·버전·배포일·릴리스 여부·ordinal·설명·라이선스·폐기 안내·버전별 저장소 주소 |
| 입력: `pickage-raw` | `requirements` | 각 버전에 선언된 일반·peer·optional 의존성 이름과 버전 범위 |
| 출력: `pickage-curated` | `package/data`, `version/data` | PostgreSQL 적재용 데이터 |
| 출력: `pickage-curated` | `package_ids/data`, `quality/*` | ID 유지와 결과 추적을 위한 내부 관리용 데이터 |

현재 구현은 Python과 **로컬 DuckDB**로 실행한다. DuckDB는 전처리용 라이브러리로 사용하며 별도 서버를 띄우지 않는다.
MinIO 원본은 변경하지 않고, 승인된 파일을 로컬 캐시에 받아 처리한다.
BigQuery·npm API를 다시 호출하지 않는다.

다음 항목은 이번 구현 범위에 포함하지 않는다.

- PostgreSQL 실제 적재 및 테이블 생성
- `snapshot`, `package_snapshot`, `package_version_snapshot` 생성 및 `dependents_count` 계산
- semver 범위를 실제 버전으로 해석하거나 설치된 의존성 그래프를 만드는 작업
- Spark 분산 실행, 서버 배포, 자동 스케줄링
- `pkg_project` 후보 병합, `projects` 통계 가공, 저장소의 실제 접속·리디렉션 확인

### 처리 순서

1. **입력 확인**: Bronze 완료 표시와 manifest(파일 목록·검증 정보)를 확인하고 파일의 크기·체크섬을 검증한다.
2. **버전 선별**: 릴리스 여부와 원본 스냅샷 시각으로 처리할 버전을 정한다.
3. **패키지 구성**: 패키지 ID를 유지·부여하고, ordinal 기준으로 대표 저장소를 선택한다.
4. **버전 구성**: 같은 패키지·버전의 requirements를 연결해 표시용 JSON을 만들고 메타데이터 예외를 처리한다.
5. **결과 검증**: 기본키·외래키·건수를 검사하고, Parquet를 만든 뒤 다시 읽어 건수를 비교한다.
6. **완료 결과 게시**: MinIO에 업로드한 모든 파일의 체크섬을 다시 확인한 뒤에만 완료 표시와 최신 결과 경로를 갱신한다.

## 2. 전처리 규칙

### 2.1. 처리할 버전: 최신 하나가 아니라 모든 릴리스 버전

**패키지별 최신 버전만 남기는 것이 아니다.** 다음 조건을 만족하는 모든 버전을 `version`에 넣는다.

```sql
WHERE is_release = TRUE
  AND (published_at IS NULL OR published_at <= SnapshotAt)
```

| 원본 상태 | 처리 |
| --- | --- |
| `is_release=true`, 배포일이 스냅샷 시각 이전 또는 동일 | 포함 |
| `is_release=true`, `published_at=NULL` | 포함하고 배포일 NULL 유지 |
| `is_release=true`, `published_at > SnapshotAt` | 버전 제외, `PUBLISHED_AFTER_SNAPSHOT` 기록 |
| `is_release=false` 또는 NULL | 포함하지 않고 report에 유형별 건수 기록 |

- 날짜 비교에는 폴더 이름의 날짜가 아니라 **원본 행의 실제 `SnapshotAt` 시각**을 사용한다. 자정이나 일말로 바꾸지 않는다.
- 두 입력에 존재하는 행들의 실제 `SnapshotAt`은 같아야 하며, 날짜도 실행 인자의 `--snapshot`과 일치해야 한다.
- 스냅샷 이후 배포 버전은 합의한 정책상 데이터 오류로 간주한다. 업스트림에서 오류가 발생한 원인까지 확인했다는 뜻은 아니다.
- 제외는 패키지 목록과 대표 저장소를 만들기 전에 적용한다. 제외된 버전의 저장소·의존성은 결과에 사용하지 않는다.
- 유효한 버전이 하나도 남지 않은 패키지는 이번 `package`에 넣지 않는다. 과거 ID 매핑은 유지한다.
- `published_at=NULL`은 다른 날짜로 채우지 않는다. 해당 버전도 대표 저장소 후보에 포함한다.
- 배포일이 없는데 Curated에 저장됐다는 이유로 특정 과거 시점에 이미 배포됐다고 가정하지 않는다. 향후 dependents 계산에서의 처리는 별도로 정한다.
- `is_release`는 필터에만 사용한다. 현재 ERD의 `version`에는 해당 컬럼이 없으므로 출력하지 않는다.

### 2.2. package_id: 이름을 기준으로 한 번 부여하고 유지

`package_id`는 **Pickage가 패키지명에 부여하는 내부 식별자**다. 버전 순번이나 npm의 외부 식별자가 아니다.

1. 최초 실행은 대상 패키지명을 중복 제거하고 이름순으로 정렬해 1부터 ID를 부여한다.
2. 다음 실행은 직전 완료 실행의 `name → package_id` 매핑을 읽어 기존 ID를 재사용한다.
3. 새 패키지만 이름순으로 정렬해 전체 보존 매핑의 최대 ID 다음부터 부여한다.
4. 입력에서 사라진 패키지의 매핑도 보존한다. 재등장하면 같은 ID를 쓰며, 다른 패키지에 ID를 재사용하지 않는다.

예를 들어 기존에 `b-package → 1`, `c-package → 2`가 있으면,
새로 들어온 `a-package`는 이름이 앞서더라도 `a-package → 3`이 된다.
매번 전체 이름을 다시 정렬해서 기존 ID를 바꾸지 않는다.

전체 매핑은 `package_ids/data`에 저장한다. `_current.json`이 가리키는 직전 완료 결과를 이어받으며,
동시 실행으로 ID가 충돌하지 않도록 전역 writer lock(실행 잠금)을 사용한다.
완료 실행이 있는데 `_current.json`이 사라졌으면 ID를 1부터 다시 만들지 않고 실패한다.

### 2.3. 대표 저장소: ordinal 내림차순으로 유효한 주소 선택

저장소 후보는 **`versions_full.source_repo`**에서 가져온다. `pkg_project`에서 추가 후보를 가져오지 않는다.

1. 필터를 통과한 버전을 패키지별 `ordinal DESC` 순서로 확인한다.
2. 사용할 수 있는 GitHub·GitLab 주소를 처음 찾으면 `package.repo_url`로 선택한다.
3. 주소가 없거나 형식이 유효하지 않으면 다음 순위 버전을 확인한다.
4. 끝까지 유효한 주소가 없으면 `repo_url=NULL`로 둔다. 패키지를 제거하지 않는다.

여기서 다음 순위는 배포일 순서가 아니라 **ordinal 순서**다.
ordinal이 같으면 `published_at DESC NULLS LAST`, 그 값도 같으면 `Version ASC`로 결정한다.
이는 동률에서의 재현성을 위한 보조 기준이며, 배포일이 우선 기준이 되는 것은 아니다.

주소는 브라우저에서 사용할 수 있는 다음 형식으로 정규화한다.

```text
https://github.com/{owner}/{project}
https://gitlab.com/{group}/{subgroup...}/{project}
```

- 지원하는 Git transport·축약 표기를 HTTPS로 정리하고 `.git`, query, fragment 등을 제거한다.
- GitHub의 명확한 `tree`·`blob` 등 UI 경로와 GitLab의 `/-/` 경로는 저장소 루트로 정리한다.
- GitLab 하위 그룹은 유지한다. 경계가 모호한 경로는 임의로 추측하지 않는다.
- GitHub·GitLab 외 호스트, 비정상 경로·제어문자·인증정보 포함 주소 등은 후보에서 제외한다. SSH transport의 `git@` 표기는 지원한다.
- 정규화 후 200자를 넘으면 자르지 않고 다음 순위 버전을 확인한다.
- **URL 형식이 유효하다는 것과 실제로 존재하거나 공개된 저장소라는 것은 다르다.** HTTP 접속·공개 여부·리디렉션은 검사하지 않는다.

### 2.4. dependency: 선언된 범위를 보존하는 표시용 JSON

버전과 requirements를 **`(Name, Version, SnapshotAt)`**으로 연결한다.
`Name`은 그 의존성을 선언한 패키지의 이름이고, 배열 안의 `Name`은 의존 대상 패키지의 이름이다.

| 원본 배열 | 출력 JSON 키 |
| --- | --- |
| `Dependencies` | `dependencies` |
| `PeerDependencies` | `peerDependencies` |
| `OptionalDependencies` | `optionalDependencies` |

각 원소의 `Name`을 객체 키, `Requirement`를 값으로 사용한다. 다음은 구조를 보여주기 위한 예시다.

```json
{
  "dependencies": {"loose-envify": "^1.1.0"},
  "peerDependencies": {},
  "optionalDependencies": {}
}
```

범위 문자열과 이름은 원본대로 보존하며, `^1.1.0`을 특정 버전으로 해석하지 않는다.
이 JSON은 사용자에게 선언된 의존성을 보여주는 용도다. dependents 계산의 입력으로 사용하지 않는다.
현재 원본에 없는 devDependencies 등의 정보는 만들어 넣지 않는다.

| 원본 상태 | `dependency` 처리 | 품질 기록 |
| --- | --- | --- |
| requirements 행이 있고 배열이 비어 있음 | 해당 종류를 `{}`로 저장 | 없음 |
| requirements 행 자체가 없음 | 전체 JSON을 SQL NULL로 저장, 버전 유지 | `MISSING_REQUIREMENTS` |
| 같은 배열에서 동일한 이름·Requirement 쌍이 반복됨 | 동일한 쌍을 하나로 합침 | 없음 |
| 같은 배열에서 같은 이름에 서로 다른 Requirement가 있음 | 전체 JSON을 SQL NULL로 저장, 버전 유지 | `INVALID_REQUIREMENTS` |
| 배열·원소·이름·Requirement가 NULL이거나, 이름이 비어 있거나 이름에 NUL이 있음 | 전체 JSON을 SQL NULL로 저장, 버전 유지 | `INVALID_REQUIREMENTS` |
| 같은 대상 버전의 requirements 행이 여러 개 | 임의 선택하지 않고 전체 실행 실패 | 완료 결과 게시 안 함 |

검사는 일반·peer·optional 배열 각각에 적용한다. 하나라도 비정상이면 `dependency` 전체를 NULL로 둔다.
빈 Requirement 문자열은 원본대로 보존한다.
**세 개의 빈 객체는 확인된 빈 의존성이고, SQL NULL은 누락 또는 변환 불가**이므로 같은 의미가 아니다.

### 2.5. 메타데이터와 예외 처리

- `description`은 원본 설명을 유지한다. 다만 NUL 문자(`\u0000`)가 있으면 **그 버전의 description만 SQL NULL**로 바꾼다.
  `quality/metadata_issues`에 `NUL_IN_DESCRIPTION`을 기록하며, 원본 설명은 Bronze에 보존한다.
- `licenses`는 원본 `Licenses`를 JSON으로 직렬화한다. 빈 배열과 SQL NULL을 구분한다.
- `deprecated`는 원본 `Deprecated`의 안내 문자열을 유지한다. Boolean으로 바꾸지 않는다.
- `ordinal`은 원본 값을 유지한다. 새 순번을 계산하거나 누락값을 ERD 기본값 0으로 채우지 않는다.

아래는 행을 조용히 버리거나 값을 임의로 고치는 대신 **전체 실행을 실패시키는 조건**이다.

| 검사 대상 | 실패 조건 |
| --- | --- |
| 입력 | 완료 표시·manifest 누락/불일치, 파일 크기·체크섬·원본 행 수 불일치, 스냅샷 불일치 |
| 대상 버전 키 | 이름·버전 NULL/공백뿐인 값/NUL, 이름 300자 초과, 버전 100자 초과, `(Name, Version)` 중복 |
| 기타 필드 | NULL 또는 음수 ordinal, `Deprecated`에 NUL 포함 |
| requirements | 대상 `(Name, Version)`의 행 중복 |
| ID 매핑 | 이름·ID 중복/잘못된 값, 기존 ID 변경, PostgreSQL INT 범위 초과 |
| 결과 | 대상 버전 0건, 출력 건수 불일치, 기본키 중복·외래키 불일치, Parquet 재조회 건수 불일치 |

실패한 실행은 최신 완료 결과를 대체하지 않는다. Bronze는 어떤 처리에서도 변경하지 않는다.

## 3. 생성하는 Parquet 7종류

아래 경로는 한 완료 실행의 `attempts/{attempt_id}/` 아래 상대 경로다.
**Parquet 종류와 파일 개수는 다르다.** 같은 종류의 여러 파일은 같은 컬럼 구조의 데이터를 나눠 저장한 것이다.
`data_0.parquet` 같은 파일명이나 파일 순서는 패키지·버전 순위를 뜻하지 않는다.

| 경로 | 한 행의 의미 / 연결에 사용하는 키 | 용도 | PostgreSQL 적재 대상 |
| --- | --- | --- | --- |
| `package/data` | 이번 실행의 패키지 하나 / `package_id` | 서비스 패키지 목록과 대표 저장소 | `package` |
| `version/data` | 패키지의 버전 하나 / `(package_id, version)` | 버전별 메타데이터와 표시용 의존성 | `version` |
| `package_ids/data` | 한 번이라도 ID를 부여한 패키지 하나 / `name`과 `package_id` 각각 유일 | 다음 실행의 ID 유지 | 아니오 |
| `quality/repository_selection` | 대표 저장소를 선택한 패키지 하나 / `package_id` | 어느 버전의 주소를 선택했는지 추적 | 아니오 |
| `quality/excluded_versions` | 배포일 정책으로 제외한 릴리스 버전 하나 / `(Name, Version)` | 버전 제외 사유 확인 | 아니오 |
| `quality/dependency_issues` | 표시용 의존성을 NULL 처리한 버전 하나 / `(Name, Version)` | 의존성 누락·변환 불가 사유 확인 | 아니오 |
| `quality/metadata_issues` | 메타데이터 필드를 NULL 처리한 사유 하나 / `(Name, Version, field)` | 필드 단위 처리 사유 확인 | 아니오 |

`package_ids`와 `quality` 때문에 PostgreSQL 테이블을 추가하는 것은 아니다.
품질 파일도 `pickage-curated`에 저장하며, 원본을 `pickage-quarantine`으로 이동하지 않는다.
스냅샷과 실행 문맥은 경로와 manifest로 구분한다. `package`·`version` 등에 별도 snapshot 컬럼을 추가하지 않는다.
`package_ids`에는 과거 이름도 보존되므로, 매핑에 있다는 사실만으로 이번 입력에도 그 패키지가 존재한다고 판단하지 않는다.

### 3.1. package/data — 서비스 패키지 목록

| 컬럼 | 대상 타입 | 저장 데이터 |
| --- | --- | --- |
| `package_id` | INT, 필수 | 패키지명에 부여한 Pickage ID |
| `name` | VARCHAR(300), 필수 | 원본 `Name` |
| `repo_url` | VARCHAR(200), NULL 허용 | ordinal 기준으로 선택·정규화한 대표 저장소 URL |

유효한 대상 버전이 하나 이상 있는 패키지만 포함한다. 주소가 없다는 이유로 패키지를 제거하지 않는다.

### 3.2. version/data — 모든 대상 릴리스 버전

| 컬럼 | 대상 타입 | 저장 데이터 |
| --- | --- | --- |
| `version` | VARCHAR(100), 필수 | 원본 `Version` 문자열 |
| `package_id` | INT, 필수 | `package`에 연결하는 ID |
| `published_at` | TIMESTAMP, NULL 허용 | 원본 배포 시각. 누락값은 그대로 유지 |
| `ordinal` | BIGINT, 필수 | 원본 버전 순위 값 |
| `description` | TEXT, NULL 허용 | 원본 설명. NUL 포함 시 이 필드만 NULL |
| `licenses` | JSON, NULL 허용 | 원본 라이선스 배열의 JSON 표현 |
| `deprecated` | TEXT, NULL 허용 | 원본 폐기·사용 중단 안내 문자열 |
| `dependency` | JSON, NULL 허용 | 일반·peer·optional 의존성의 이름과 선언 범위 |

위 타입·길이·필수 여부는 **PostgreSQL 대상 계약**이다. Parquet의 문자열 컬럼은 VARCHAR로 읽히고,
JSON은 JSON 문자열로 저장된다. 실제 로컬 조회에서는 `licenses`·`dependency`의 JSON 타입도 확인했다.
Parquet가 DB의 PK·FK·NOT NULL 제약을 대신 적용하는 것은 아니므로 전처리에서 검증하고, 적재할 때도 대상 제약을 적용해야 한다.
`is_release`, `snapshot_at`, `dependents_count`는 이 파일에 없다.

### 3.3. package_ids/data — 사라진 패키지도 남기는 ID 대장

컬럼은 `package_id`(INT), `name`(문자열)이다.

`package`는 **이번 실행의 서비스 대상**, `package_ids`는 **과거에 발급한 ID를 포함하는 전체 매핑**이다.
최초 실행에서는 두 파일의 패키지 수가 같지만, 이후 입력에서 빠진 패키지는 `package_ids`에만 남을 수 있다.
다음 실행은 이 파일을 읽어 기존 ID를 유지한다.

### 3.4. quality/repository_selection — 대표 저장소 선정 근거

| 컬럼 | 저장 데이터 |
| --- | --- |
| `package_id` | 대표 주소를 선택한 패키지 ID |
| `version` | 그 주소를 가져온 버전 |
| `ordinal` | 선택한 버전의 원본 순위 |
| `repo_url` | 최종 정규화 URL. `package.repo_url`과 연결해 확인 가능 |
| `source_repo_sha256` | 선택한 원본 `source_repo` 문자열의 SHA-256 |

유효한 주소를 선택한 패키지만 기록한다. 주소가 없는 패키지는 `package`에는 남지만 이 파일에는 없다.
최신 순위 버전의 주소가 없어 이전 버전을 선택했는지 조사할 때 사용한다.
원본 URL에는 인증정보가 섞일 수 있어 문자열을 그대로 복제하지 않고 해시로 추적한다.
전체 후보 URL 목록이나 접속 검사 결과를 저장한 파일은 아니다.

### 3.5. quality/excluded_versions — 최종 version에서 빠진 버전

컬럼은 `Name`, `Version`, `SnapshotAt`, `published_at`, `reason`이다.
두 시각은 TIMESTAMP이며, `Name`·`Version`은 제외된 원본 패키지·버전이다.

현재 사유는 `PUBLISHED_AFTER_SNAPSHOT`이다. 해당 버전은 최종 `version`에 없다.
**모든 비릴리스 버전의 목록은 아니다.** `is_release=false`·NULL로 필터링한 건수는 manifest report에서 따로 확인한다.

### 3.6. quality/dependency_issues — 버전은 유지하고 dependency만 NULL

컬럼은 `Name`, `Version`, `reason`이다.
여기서 이름과 버전은 **문제가 있는 의존성을 선언한 쪽의 패키지·버전**이지 의존 대상 이름이 아니다.

- `MISSING_REQUIREMENTS`: 대응하는 requirements 행이 없다.
- `INVALID_REQUIREMENTS`: 대응 행은 있지만 배열·원소·중복 범위 등의 문제로 JSON을 만들 수 없다.

해당 버전은 최종 `version`에 남고 `dependency`만 SQL NULL이다.
잘못된 원본 배열 자체는 이 파일에 복제하지 않으며, 조사할 때 Bronze와 원본 키로 연결한다.

### 3.7. quality/metadata_issues — 필드 단위 NULL 처리 근거

컬럼은 `Name`, `Version`, `field`, `reason`이다.
현재는 `field=description`, `reason=NUL_IN_DESCRIPTION`을 기록한다.

해당 버전은 최종 `version`에 남고 description만 SQL NULL이다.
이 파일에는 원본 설명을 넣지 않으며, 원본은 Bronze에서 확인한다.

## 4. 전체 데이터 전처리 결과

### 4.1. 결과의 기준

| 항목 | 값 |
| --- | --- |
| 확인 기준일 / 실행 환경 | 2026-09-07 / 로컬 Windows, Python 3.12, DuckDB 1.5.5 |
| 입력 Bronze 실행 | `bronze-20260907-v1` |
| 완료 Curated 실행 | `curated-20260907-v2` |
| 스냅샷 날짜 | `2026-08-31` |
| 원본의 실제 스냅샷 시각 | `2026-08-31T21:01:10.517131` |
| 입력 `versions_full` | 78,559,731행, Parquet 362개 |
| 입력 `requirements` | 78,559,731행, Parquet 790개 |
| 전체 입력 파일 | 1,152개 |
| 완료 manifest | `PASSED`, `GET_SHA256_ALL_FILES` |

여기서 **전체 데이터**는 위 스냅샷의 두 입력 데이터셋 전체를 뜻한다.
Bronze의 다른 데이터셋·과거 스냅샷까지 모두 전처리했다는 뜻은 아니다.
아래 수치는 해당 완료 실행의 manifest와 출력 검증 결과를 기준으로 하며, 미래 실행의 예상 건수가 아니다.

### 4.2. 버전이 줄어든 이유

| 구분 | 버전 수 | 처리 |
| --- | ---: | --- |
| 원본 전체 | 78,559,731 | 입력 |
| `is_release=false` | 24,364,309 | 미포함 |
| `is_release=NULL` | 1,538 | 미포함 |
| `is_release=true` 후보 | 54,193,884 | 배포일 조건 확인 |
| 후보 중 스냅샷 이후 배포 | 5,535 | 제외 및 사유 기록 |
| **최종 version** | **54,188,349** | 출력 |

건수 대조: `54,193,884 - 5,535 = 54,188,349`.
설명·의존성 필드의 NULL 처리는 버전을 제거하지 않으므로 이 차감 계산에 포함하지 않는다.

### 4.3. Parquet별 산출 규모

| 경로 | 행 수 | 파일 수 | 파일 크기 합계(bytes) |
| --- | ---: | ---: | ---: |
| `package/data` | 11,080,940 | 4 | 107,429,467 |
| `version/data` | 54,188,349 | 20 | 4,427,189,282 |
| `package_ids/data` | 11,080,940 | 4 | 77,361,207 |
| `quality/repository_selection` | 8,302,621 | 4 | 235,629,297 |
| `quality/excluded_versions` | 5,535 | 4 | 100,032 |
| `quality/dependency_issues` | 25 | 4 | 2,934 |
| `quality/metadata_issues` | 3,412 | 4 | 34,567 |
| **파일 합계** | — | **44** | **4,847,746,786 (약 4.85GB)** |

같은 패키지·버전이 서비스 파일과 관리 파일에 함께 나타나므로 행 수를 합쳐 고유 패키지 수로 해석하면 안 된다.
파일은 ZSTD 압축 Parquet이며, 실행 자원과 데이터에 따라 분할 파일 수가 달라질 수 있다.

### 4.4. 유지·NULL 처리·예외 결과

| 항목 | 건수 | 의미 |
| --- | ---: | --- |
| 대표 저장소 선택 성공 | 8,302,621개 패키지 | 선정 근거 파일에 기록 |
| `repo_url=NULL` | 2,778,319개 패키지 | 선택 가능한 주소가 없어도 패키지 유지 |
| `published_at=NULL` | 7,015,400개 버전 | 배포일을 채우지 않고 유지 |
| NUL 때문에 description을 NULL로 변경 | 3,412개 버전 | `NUL_IN_DESCRIPTION` 기록 |
| 비정상 requirements 때문에 dependency를 NULL로 변경 | 25개 버전 | 모두 `INVALID_REQUIREMENTS` |
| requirements 행 누락 | 0개 버전 | 이번 실행에서 `MISSING_REQUIREMENTS` 없음 |
| 유효하지 않거나 미지원인 원본 저장소 값 | 95,847개 값 | 중복 제거된 `source_repo` 값의 수. 패키지 수가 아님 |
| 같은 패키지의 ordinal 동률 그룹 | 0개 그룹 | 이번 데이터에서는 동률 보조 기준이 필요하지 않았음 |

행 유지·NULL 처리 항목은 서로 겹칠 수 있다. 각 건수를 합쳐 제외 버전 수로 계산하지 않는다.
description 처리 건수는 원본부터 NULL이었던 설명까지 합한 수가 아니라 **NUL 때문에 변경한 수**다.

실제 샘플에서는 `react`·`react-dom`의 대표 주소가 `https://github.com/react/react`,
`express`는 `https://github.com/expressjs/express`로 생성됐다. 이는 정규화 결과 확인이지 HTTP 접속 검사는 아니다.

### 4.5. 확인한 검증과 남은 범위

- 필터 건수 대조, 출력 기본키·외래키 검사, Parquet 재조회 건수 검증을 통과했다.
- 출력 파일을 별도 연결로 읽어 관계별 건수와 컬럼·타입을 확인했다. description에 남은 NUL 문자는 0건이었다.
- 44개 파일을 업로드한 뒤 전체 GET SHA-256 검증을 통과하고 `_SUCCESS`·`_current.json`을 게시했다.
- 동일 실행 ID로 다시 실행해 44개 파일 전체를 재검증했다. 데이터 재생성 없이 current pointer의 내용·ETag가 유지됐고 잠금도 해제됐다.
- Curated 자동 테스트 31건과 기존 MinIO 테스트 3건, Python 컴파일 및 패키지 의존성 검사가 통과했다.
- PostgreSQL 실제 적재, 저장소 URL 접속, Spark 실행과 dependents 계산은 검증하지 않았다.

최초 `curated-20260907-v1`은 NUL 설명 처리 정책 확정 전 검증에서 중단됐다.
완료 결과로 게시하지 않았으며, 정책을 반영한 새 실행 ID `v2`로 위 결과를 생성했다.
실패 시도의 작업 파일은 자동 삭제하지 않았다.

## 5. MinIO 저장 경로와 결과를 읽는 방법

버킷은 `pickage-curated`다. 아래 `request.json`·manifest·완료 표시·잠금 파일은 Parquet가 아니다.

```text
depsdev/v1/package-version/
  _current.json                         # 최신 완료 실행과 manifest 해시
  _writer.lock                          # 동시 실행 방지 잠금; 실행 중에만 존재
  snapshot={date}/run_id={run}/
    request.json                        # 입력 manifest 해시·코드·DuckDB 버전·이전 완료 실행
    run_manifest.json                   # 검증 건수·출력 파일 목록·크기·SHA-256
    _SUCCESS                            # 완료 manifest의 SHA-256
    attempts/{attempt_id}/
      package/data/*.parquet
      version/data/*.parquet
      package_ids/data/*.parquet
      quality/repository_selection/*.parquet
      quality/excluded_versions/*.parquet
      quality/dependency_issues/*.parquet
      quality/metadata_issues/*.parquet
```

확인 시점의 최신 결과와 이번 완료 실행의 manifest 위치는 다음과 같다.
`_current.json`은 다음 실행이 완료되면 바뀔 수 있으므로 특정 실행 재현에는 고정된 run ID를 사용한다.

```text
s3://pickage-curated/depsdev/v1/package-version/_current.json
s3://pickage-curated/depsdev/v1/package-version/snapshot=2026-08-31/run_id=curated-20260907-v2/run_manifest.json
```

후속 적재기는 다음 순서로 읽는다.

1. `_current.json`에서 사용할 완료 실행 경로와 manifest 해시를 읽는다.
2. 해당 실행의 `_SUCCESS`와 `run_manifest.json`을 확인하고 해시를 대조한다.
3. manifest의 **정확한 파일 목록**에서 필요한 종류를 골라 읽는다. 각 파일의 크기·SHA-256도 확인한다.
4. PostgreSQL 적재에는 `package/data`와 `version/data`를 사용하고, 내부 관리용 파일을 서비스 테이블에 섞지 않는다.

**모든 snapshot·attempt 경로를 한꺼번에 glob으로 읽으면 안 된다.** 실패 시도나 과거 결과까지 중복으로 읽을 수 있다.
이 완료 게시 규칙은 Curated 파일과 ID 계보를 위한 것이며 PostgreSQL 트랜잭션·운영 백업을 대신하지 않는다.

## 6. 팀원용 설치·실행

모든 명령은 프로젝트 루트에서 실행한다. Python 3.10 이상이 필요하며 실제 검증 환경은 Windows/Python 3.12다.
로컬 MinIO를 실행하려면 Linux 컨테이너를 지원하는 Docker/Compose가 필요하다.
DuckDB는 결과 재현을 위해 requirements에서 1.5.5로 고정한다.

### 가상환경과 테스트

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

활성화 후 공통 명령:

```bash
python -m pip install -r pipeline/preprocessing/curated/requirements.txt
python -m unittest discover -s pipeline/preprocessing/tests/curated -t . -p "test_*.py" -v
python -m unittest discover -s pipeline/minio -p "test_*.py" -v
```

PowerShell에서 활성화가 차단되면 `python` 대신 `.\.venv\Scripts\python.exe`를 사용한다.
테스트는 합성 Parquet와 Fake S3를 사용하므로 원본 데이터·MinIO·`.env` 없이 실행할 수 있다.
기존 가상환경을 사용해도 된다. macOS/Linux에서의 실제 실행 검증은 별도로 필요하다.

### 전체 데이터 실행

1. [MinIO 안내](../../minio/README.md)에 따라 로컬 `.env`와 MinIO를 준비한다. 실제 자격증명과 원본 파일은 Git에 없다.
2. `pickage-raw`에 두 입력 데이터셋의 승인된 Bronze 실행이 있어야 한다.
3. 원본 `run_manifest.json`, `source_manifest.json`, `_SUCCESS`를 준비해야 한다. 로컬 `data/raw`만으로 검증을 우회하지 않는다.

```bash
docker compose -f docker-compose.local.yaml up -d
python -m pipeline.preprocessing.curated.build --snapshot 2026-08-31 --bronze-run-id bronze-20260907-v1 --run-id curated-20260907-v2 --memory-limit 12GB --threads 4 --workers 4
```

MinIO 접속은 기존 입고 스크립트의 `client()`와 접속 설정을 재사용한다.
위 완료 run ID가 이미 존재하고 입력·코드가 같으면 **재처리하지 않고 기존 결과를 재검증**한다.
입력 manifest·코드·DuckDB 버전이 바뀌면 새 run ID가 필요하며, ID 매핑은 직전 완료 실행에서 이어받는다.

| 인자 | 의미 |
| --- | --- |
| `--snapshot` | 입력 스냅샷 날짜 |
| `--bronze-run-id` | 읽을 승인 Bronze 실행 |
| `--run-id` | 이번 Curated 실행 식별자 |
| `--work-dir` | 로컬 캐시·작업 DB·출력 위치. 기본 `data/curated` |
| `--threads` | DuckDB 처리 스레드 수 |
| `--workers` | MinIO 파일 전송·검증 작업의 병렬 수 |
| `--memory-limit` | DuckDB 메모리 한도. Python·운영체제까지 포함한 전체 사용량 한도는 아님 |

### 자원과 진행 로그

전체 데이터는 작은 테스트보다 훨씬 많은 메모리·디스크·시간을 사용한다.
입력 캐시뿐 아니라 중간 테이블을 담는 작업 DB와 최종 파일도 저장하므로 입력 크기만큼의 공간만 확보해서는 부족하다.
`data/curated`는 Git에서 제외되며, 실패한 로컬 시도도 자동 삭제하지 않는다.

현재 로그는 큰 단계 단위다. `assembling declared dependency JSON` 구간에는 requirements 연결,
중복 검사, JSON 생성, 최종 version 구성과 검증이 포함된다.
행 단위 처리율이나 신뢰할 만한 예상 남은 시간은 제공하지 않는다.
상세 진행 계측과 대규모 반복 실행의 성능 최적화는 별도 개선 대상이다.

## 7. 재실행·실패 처리 원칙

- 입력은 manifest에 나열된 파일만 읽는다. 최초 다운로드는 크기·SHA-256을 확인하고, 캐시 재사용은 로컬 SHA-256과 원격 객체 존재·크기를 확인한다.
- 업로드와 전체 GET 검증 후 **manifest → `_SUCCESS` → `_current.json`** 순서로 게시한다.
- 업로드 도중 실패하면 기존 최신 결과는 유지한다. 재시도는 새 attempt에 기록하고 부분 업로드를 덮어쓰지 않는다.
- 실패 attempt는 완료 manifest에서 참조하지 않는다. 파일이 있다는 이유만으로 완료 결과로 취급하지 않는다.
- manifest 작성 후 완료 표시 직전에 중단되면 기존 출력 파일을 재검증하고 게시를 마친다.
- 과거 완료 실행을 재검증해도 current pointer를 과거로 되돌리지 않는다.
- 강제 종료 시 잠금이 남을 수 있다. 자동 만료·강제 해제하지 않으며, 실제 실행 프로세스가 없음을 확인한 뒤 해당 잠금만 정리해야 한다.
- 현재 pointer가 유실됐는데 다른 완료 실행이 있으면 기존 ID 계보를 복구해야 한다. 새 ID 체계로 조용히 초기화하지 않는다.

## 8. 코드와 자동 검증 위치

| 파일 | 책임 |
| --- | --- |
| [build.py](build.py) | 입력·이전 ID 계보 확인, 실행 조율, 완료 결과 게시 |
| [transform.py](transform.py) | 필터, ID 부여, 대표 저장소 선택, JSON 변환, 출력·품질 검증 |
| [repository.py](repository.py) | 네트워크 호출 없는 GitHub·GitLab 주소 정규화 |
| [storage.py](storage.py) | 체크섬 캐시, 덮어쓰기 방지, 전송 검증, 잠금과 조건부 pointer 갱신 |
| [test_transform.py](../tests/curated/test_transform.py) | 버전 필터·ID 유지·JSON 및 메타데이터 예외·출력 스키마 |
| [test_repository.py](../tests/curated/test_repository.py) | URL 정규화와 비정상·인증정보 포함 주소 거부 |
| [test_storage.py](../tests/curated/test_storage.py) | 체크섬·객체 불일치·잠금·조건부 갱신 |
| [test_build.py](../tests/curated/test_build.py) | 합성 원본의 전체 흐름, 재실행·실패 복구·ID 계보 유지 |

자동 테스트에는 배포일 경계·누락, ordinal 동률·이전 버전 주소 선택, 신규·재등장 패키지의 ID 유지,
NULL 배열·원소·동일/충돌 중복, NUL 설명, 잘못된 키·ID·ordinal·스냅샷,
불완전 입력·체크섬 불일치·재실행·실패 후 이전 결과 유지 등의 시나리오가 포함된다.
테스트 통과를 PostgreSQL 실제 적재나 URL 접속까지 검증했다는 의미로 확대하지 않는다.
