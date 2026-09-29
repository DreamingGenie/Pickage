이 문서는 새로운 raw 스냅샷이 들어온 뒤 Curated 결과를 만들고 PostgreSQL에 반영하는 전체 흐름을 설명합니다. 먼저 용어와 전체 여정을 읽고, 필요한 경우 각 단계의 계산 규칙과 운영 절차로 내려가면 됩니다.

이 문서의 예시는 `alpha-kit`, `beta-lib`라는 가상의 npm 패키지로 설명합니다. 예시 숫자는 이해를 위한 값이며 실제 실행 결과가 아닙니다.

## 01. 한눈에 보는 흐름

Pickage의 데이터 흐름은 네 가지 경계를 지나갑니다.

1. 수집 팀이 BigQuery 등에서 raw 데이터를 받아 MinIO `pickage-raw`에 저장합니다.
2. 전처리 실행기가 특정 스냅샷의 raw manifest를 고정하고, 여섯 단계를 계산합니다.
3. 검증된 결과를 MinIO `pickage-curated`의 immutable bundle로 게시합니다.
4. 별도 Spring Boot 배치가 완료 bundle을 읽어 PostgreSQL에 한 스냅샷 단위로 반영합니다.

{{diagram:overview}}

| 경계 | 기준 | 결과 |
| --- | --- | --- |
| raw | 생산자 manifest, 파일 SHA, 실제 스냅샷 시각 | 변경되지 않는 입력 |
| 전처리 | 실행 요청의 snapshot·run_id·코드 계약 | 단계별 Parquet와 품질 기록 |
| Curated | bundle manifest, 단계 manifest, `_SUCCESS` | DB가 소비할 완료 묶음 |
| PostgreSQL | parent bundle, staging receipt, 트랜잭션 | 서비스 테이블과 적재 이력 |

`raw`는 수집 결과이고 `Curated`는 DB 적재에 맞춘 정제 결과입니다. Curated를 만들었다고 DB에 자동으로 들어간 것은 아닙니다. 전처리 실행기는 `pipeline/preprocessing/orchestration`에, Java 적재기는 `backend/src/main/java/com/ssafy/pickage/domain/curatedload`에 있습니다.

전체 실행은 `snapshot → package_version → downloads → repository → package_snapshot → dependents` 순서입니다. 앞 단계의 manifest와 출력이 뒤 단계의 입력이 되므로, 중간 단계 하나만 임의로 최신 파일로 바꾸지 않습니다.

## 02. 누가 무엇을 실행하는가

| 주체 | 하는 일 | 저장소 |
| --- | --- | --- |
| weekly ingest | raw 스냅샷과 producer manifest 수집 | `pickage-raw` |
| Curated dispatcher | 완료 raw 회차 탐색, 순서 확인, 전처리 실행 | `pickage-curated/_ops` |
| Python producers | 단계별 정규화·집계·검증·게시 | 로컬 작업 디렉터리와 MinIO |
| Spring Curated loader | 완료 bundle 검증, COPY/staging, 서비스 테이블 게시 | PostgreSQL |
| timer/flock | 수집과 전처리의 단일 실행 순서 보장 | data 노드 |

구현된 weekly 실행 흐름은 수집이 종료된 뒤 dispatcher를 이어서 호출합니다. `deploy/prod/data/run-weekly-ingest.sh`의 인자 없는 실행이 이 연결을 담당합니다. 수집 명령이 실패해도 dispatcher는 호출되지만, 완료 입력이 확인된 회차만 처리합니다. 수집 종료 코드 0만으로 입고 완료를 판단하지 않습니다. timer의 확인 간격과 새 스냅샷이 생성되는 주기는 서로 다릅니다.

배포 구성에서 전처리는 data 노드의 raw·MinIO 접근 경로에서 실행하고, Spring 적재기는 PostgreSQL에 접근할 수 있는 app 노드의 별도 배치로 실행하는 구성을 전제로 합니다. 두 프로세스의 실제 운영 배치와 timer 등록은 배포 설정에서 확정해야 하며, MR 병합만으로 운영 프로세스가 자동 시작되지는 않습니다.

전처리 실행 명령의 형태는 다음과 같습니다. **명령 설명용 날짜와 run ID**이며, 실제 실행에는 최초 완료 baseline·해당 raw 입고·MinIO 설정이 먼저 필요합니다.

```powershell
python -m pipeline.preprocessing.orchestration weekly `
  --snapshot 2026-09-07 `
  --run-id weekly-20260907 `
  --work-dir C:/pickage-work `
  --repository-engine duckdb
```

DB 적재는 Curated bundle을 정확히 지정합니다. `mode=poll`은 `_current.json`의 parent 연결을 따라 오래된 미적재 bundle을 찾지만, 새 timer를 만드는 기능은 아닙니다. 설정 예시는 `backend/CURATED_LOAD.md`를 기준으로 합니다.

현재 구현과 검증 범위를 구분합니다. 코드와 로컬 회귀 시험은 구현 근거이고, 작업 로그의 별도 DB·MinIO 시험은 검증 근거입니다. 운영 EC2에서 최신 raw를 처음부터 다시 돌린 결과와 운영 자동 배포는 아직 별도 확인 대상입니다.

## 03. 스냅샷 하나의 여정

아래 가상 입력을 하나의 스냅샷으로 추적합니다.

| 패키지 | 버전 | 배포일 | ordinal | 선언 의존성 |
| --- | --- | ---: | ---: | --- |
| `alpha-kit` | `1.0.0` | 2026-08-01 | 1 | `beta-lib: ^2.0.0` |
| `alpha-kit` | `1.1.0` | 2026-09-10 | 2 | `beta-lib: ^2.1.0` |
| `beta-lib` | `2.0.0` | 2026-07-01 | 1 | 없음 |

스냅샷 날짜가 2026-09-07이면 `alpha-kit@1.1.0`은 아직 배포되지 않았으므로 version 결과에서 제외됩니다. `alpha-kit@1.0.0`과 `beta-lib@2.0.0`은 남습니다.

1. raw manifest와 실제 파일 SHA를 확인합니다.
2. Projects에서 실제 관측 시각과 스냅샷 후보를 만듭니다.
3. 유효 릴리스만 골라 package ID와 version 행을 만듭니다.
4. 직전 스냅샷과 현재 날짜 사이의 다운로드를 합산합니다.
5. 버전의 저장소 주소와 projects 통계를 연결합니다.
6. 패키지별 다운로드·stars·open issues를 package snapshot으로 만듭니다.
7. 선언된 범위를 실제 후보 버전에 적용해 dependents snapshot을 만듭니다.
8. 여섯 결과와 품질 파일을 다시 검증하고 Curated bundle을 게시합니다.
9. Spring loader가 bundle을 읽고 초기/주간 경로에 따라 PostgreSQL 트랜잭션을 커밋합니다.

{{diagram:stages}}

작은 예시에서 `alpha-kit@1.0.0`이 `beta-lib`를 선언했다는 것은 “alpha-kit의 이 버전이 beta-lib의 범위를 선언했다”는 뜻입니다. 이것이 곧 모든 프로젝트가 beta-lib를 설치했다는 뜻도, transitive dependency까지 포함한 사용량이라는 뜻도 아닙니다.

## 04. 전처리 단계별 계산

### 4.1 snapshot: 기준 날짜와 관측 시각

- 입력: raw Projects Parquet와 요청의 `snapshot` 날짜.
- 계산: 승인된 Projects 행의 실제 `SnapshotAt`을 사용해 스냅샷 후보와 달력을 만듭니다. 폴더 이름을 임의의 자정 시각으로 바꾸지 않습니다.
- 출력: snapshot candidate, Projects inventory, 날짜 SQL과 단계 manifest. 게시 prefix는 `depsdev/v1/snapshot-reference`입니다.
- 검증: 입력 파일의 SHA·행 수·스냅샷 일치, 완료 marker, 날짜 계약을 확인합니다.

예시에서 `2026-09-07`은 표시용 날짜이고 관측 시각은 `2026-09-07T21:01:10Z`처럼 별도로 보존됩니다. 같은 날짜라도 실제 관측 시각이 다른 입력을 섞지 않습니다.

근거는 `pipeline/preprocessing/orchestration/stages.py`와 `pipeline/preprocessing/common/curated_input.py`입니다.

### 4.2 package_version: 패키지·버전과 ID

- 입력: 최초 full 회차는 `versions_full`, 주간 회차는 `versions_min`과 requirements, 직전 완료 Curated의 ID·메타데이터를 사용합니다.
- 계산: `is_release = true`이고 `published_at`이 NULL이거나 스냅샷 시각 이하인 버전만 남깁니다. `(Name, Version)`을 키로 requirements를 연결하고, 의존성 범위를 JSON으로 만듭니다. 이 마스터 포함 규칙과 dependents 계산의 적격 버전 규칙은 별개입니다.
- 출력: `package/data`, `version/data`, `package_ids/data`, `changes/*`, `quality/*`.
- 검증: 키 중복, NULL·길이·ordinal, 외래키, 출력 행 수와 Parquet 재조회 건수를 검사합니다.

최초 실행은 이름순으로 새 ID를 부여합니다. 이후 실행은 기존 `name → package_id`를 재사용하고, 새 이름만 이전 최대 ID 다음에 추가합니다. 입력에서 사라진 이름도 `package_ids`에는 남을 수 있습니다.

주간 입력에 없는 기존 package의 `repo_url`, 기존 version의 description/licenses는 유지합니다. 기존 패키지의 새 버전은 **직전 완료 Curated에도 있고 현재 min에도 있는 낮은 ordinal 버전 중 가장 가까운 버전**에서 description/licenses를 복사합니다. ordinal은 현재 스냅샷 기준이고 동률이면 버전 문자열 오름차순으로 고정합니다. 같은 회차 신규 버전끼리는 복사하지 않습니다. 후보가 없거나 후보 값이 NULL이면 NULL을 유지합니다. 신규 패키지의 저장소 URL과 신규 버전의 보완할 메타데이터는 비워 둡니다.

`dependencies`, `peerDependencies`, `optionalDependencies`의 범위 문자열은 특정 설치 버전으로 해석하지 않고 JSON으로 보존합니다. requirements 행이 없거나 내용이 충돌하면 version 행은 유지하되 `dependency`만 SQL NULL로 두고 품질 사유를 기록합니다. 빈 객체 `{}`는 확인된 빈 의존성이고 NULL은 누락·변환 불가이므로 서로 다릅니다.

가상 예시에서 9월 7일 기준 `alpha-kit@1.1.0`은 제외되고 `alpha-kit@1.0.0`은 남습니다. `alpha-kit`의 기존 ID가 17이면 새 실행에서도 17입니다.

근거는 `pipeline/preprocessing/curated/build.py`, `pipeline/preprocessing/curated/weekly_metadata.py`, `pipeline/preprocessing/package_snapshot/policy.py`입니다.

### 4.3 downloads: 날짜 구간 합계

- 입력: 다운로드 Bronze의 대상 CSV·상태 Parquet·일별 Parquet, 승인 package 모집단과 snapshot calendar.
- 계산: 달력에서 바로 앞 날짜 P 이상, 현재 날짜 S 미만인 `[P,S)`의 유효 일별 값을 패키지별로 합산합니다. 여러 raw 회차를 명시한 경우 현재 회차를 우선하고 지정 순서로 누락 날짜를 보완합니다.
- 출력: 다운로드 구간 결과와 coverage·중복 품질 기록.
- 검증: 동일 키 중복, 물리 날짜와 partition 날짜 불일치, 입력 manifest·행 수를 확인합니다.

예를 들어 P=8월 31일, S=9월 7일이면 8월 31일~9월 6일의 7일을 계산합니다. 그중 `alpha-kit`의 유효 관측이 9월 1일 10회, 9월 2일 12회뿐이라면 **합계 22, valid_days=2, expected_days=7, PARTIAL**입니다. 누락된 5일을 0으로 채운 완전한 7일 합계가 아닙니다.

| 일별 입력 | 합산 여부 | 의미 |
| --- | --- | --- |
| 숫자이며 `imputed_gap=false` | 포함 | 실제 0도 유효한 관측 |
| NULL 또는 `imputed_gap=true` | 제외 | 관측 없음 또는 보완된 공백 |
| 구간 전체에 유효 일자가 없음 | 결과 NULL | `UNAVAILABLE` |

다운로드 수집 대상 목록은 전체 package 모집단과 다릅니다. 수집 대상 밖의 승인 패키지도 결과에서 삭제하지 않고 다운로드 NULL과 사유를 남깁니다.

근거는 `pipeline/preprocessing/downloads_interval/aggregate.py`와 `pipeline/preprocessing/orchestration/README.md`의 주간 이력 규칙입니다.

### 4.4 repository: 저장소 식별과 지표 연결

- 입력: 승인된 version의 `source_repo`, Projects 통계, package/version 연결 정보.
- 계산: 버전 후보를 `ordinal DESC → published_at DESC NULLS LAST → version ASC`로 정렬해 유효한 저장소 URL을 선택합니다. provider와 전체 project path로 저장소를 식별하고, 현재 스냅샷과 정확히 같은 관측 시각의 Projects 지표를 패키지에 연결합니다.
- 출력: repository 단계의 지표와 선택·충돌·품질 파일.
- 검증: 키와 정확한 timestamp, 승인된 version join, 충돌·중복 집계, 결과 행 수를 확인합니다.

기본 엔진은 DuckDB입니다. `native`와 `docker`는 비교 실험 경로입니다. URL 형식이 유효하다는 것만 검사하며 실제 저장소가 존재하는지 HTTP 접속으로 확인하지 않습니다.

`alpha-kit`의 선택 URL이 `https://github.com/example/alpha`이고 같은 시각의 Projects 값이 stars=31, open issues=4이면 그 값을 사용합니다. 같은 저장소에 연결된 여러 버전의 별 개수를 더하지 않습니다. GitHub 비교 경로는 소문자로 통일하고 GitLab은 대소문자를 유지합니다.

같은 저장소·시각에 값이 충돌하면 두 지표를 NULL로 만들고 충돌 근거를 기록합니다. 완전히 같은 중복은 하나로 합칩니다. 유효한 저장소를 골랐지만 관측이 없으면 URL 선택은 유지하고 지표만 NULL로 둡니다. 주간 입력에서는 보존한 package 단위 URL로 파생 입력을 만들며 과거 version별 URL을 새로 수집한 것은 아닙니다.

근거는 `pipeline/preprocessing/repository_metrics/duckdb_transform.py`, `repository_metrics/transform.py`, `repository_metrics/policy.py`입니다.

### 4.5 package_snapshot: 패키지 단위 스냅샷

- 입력: package/version 결과, downloads 합계, repository 지표.
- 계산: 패키지별 다운로드·stars·open issues를 현재 snapshot 날짜와 결합합니다. package master와 snapshot metric을 분리합니다.
- 출력: package-snapshot 단계의 `data/`와 품질 기록. 한 행의 키는 `(package_id, snapshot_at)`입니다.
- 검증: package ID 존재, snapshot 날짜 일치, 키 중복, 입력 단계와 결과 건수 일치를 확인합니다.

가상 예시의 `alpha-kit`은 22 downloads, stars 31, open issues 4로 `package_snapshot`에 한 행을 갖습니다. 다음 스냅샷에는 같은 package ID로 새 날짜 행이 추가됩니다.

근거는 `pipeline/preprocessing/package_snapshot/build.py`, `quality.py`, `quality_schema.py`입니다.

### 4.6 dependents: 버전별 직접 역의존

- 입력: requirements의 선언 범위, 현재·과거의 적격 version, snapshot calendar.
- 계산: 각 적격 원천 package-version이 선언한 범위를 그 시점의 후보에 적용하고, **조건을 만족하는 가장 높은 정식 semver 버전 하나**를 선택합니다. 이렇게 직접 연결된 원천 버전 수를 대상 버전별로 집계합니다. 원천 패키지의 대표 버전 하나만 골라 세는 방식은 아닙니다.
- 출력: `version_dependents/data`와 `quality`, `version_snapshot`에 사용할 행.
- 검증: 입력 키·정확한 timestamp, 승인된 version join, 범위 해석 결과, 출력 건수와 NULL 사유를 확인합니다.

9월 7일에 후보가 `beta-lib@2.0.0`뿐이면 `alpha-kit@1.0.0`의 `^2.0.0`은 2.0.0으로 해석되어 그 버전의 count에 1을 더합니다. 나중에 적격 2.1.0이 생기면 같은 범위의 선택 결과는 2.1.0으로 바뀔 수 있습니다. 실제 사용자가 설치한 lockfile을 읽은 결과가 아니라 **스냅샷 기준 선언 범위를 해석한 결과**입니다.

같은 원천 패키지의 적격 버전 두 개가 각각 해당 버전으로 해석되면 원천 버전 수는 2가 될 수 있습니다. 프로젝트 수, npm 설치 수, 간접(transitive) 사용량과는 다릅니다. prerelease·잘못된 semver·지원하지 않는 범위 등은 자격과 품질 규칙으로 구분합니다.

해석하지 못한 선언은 별도의 품질 상태에 남깁니다. 서비스 결과에서 NULL은 대표적으로 대상 목록 밖(`NOT_TARGET`) 또는 적격 대상 버전이 아님(`INELIGIBLE_TARGET_VERSION`)을 뜻합니다. 적격 대상 버전은 해석된 연결이 없으면 0이 될 수 있으며, 미해석 선언 때문에 전체 품질이 PARTIAL인 경우도 있어 count와 품질 상태를 함께 읽어야 합니다. “미해석 선언 하나가 있으면 모든 결과를 NULL로 만든다”는 규칙은 아닙니다.

DB 적재 시 `dependents_count IS NULL`인 `package_version_snapshot` 행만 제외하고, 실제 값 0은 저장합니다. package/version master와 Curated 원본은 유지합니다.

기본 경로는 CPU resolver와 `weighted-events-v2` 집계이며 대상 묶음과 작업자 수를 고정합니다. `dependents_engine=legacy`는 비교용 oracle입니다.

근거는 `pipeline/preprocessing/version_dependents/historical_reference.py`, `historical_production.py`, `pipeline/preprocessing/requirements_resolution`입니다.

{{diagram:records}}

## 05. Curated 결과와 데이터 계약

완료 bundle은 `depsdev/v1/curated-bundle/snapshot=S/run_id=R/` 아래에 게시됩니다. 단계별 Parquet와 품질 파일은 attempt 아래에서 만들어지고, 최종 manifest가 승인된 파일 목록과 SHA를 가리킵니다.

| 결과 | 한 행의 의미 | DB 대상 |
| --- | --- | --- |
| `package/data` | 현재 서비스 대상 package 하나 | `package` |
| `version/data` | package의 version 하나 | `version` |
| package-snapshot 단계의 `data/` | package의 한 snapshot metric | `package_snapshot` |
| dependents 단계의 승인 서비스 파일 | version의 직접 dependents 관측 | `package_version_snapshot` |
| `changes/package_upserts` | 신규·변경 package | weekly upsert |
| `changes/version_upserts` | 신규·변경 version | weekly upsert |
| `quality/*` | 제외·NULL·충돌·coverage 근거 | 품질/로그 |

master와 snapshot을 구분합니다. `package/data`, `version/data`는 현재 스냅샷의 적격 모집단이며, `master_package/data`, `master_version/data`는 이전에 있었던 행까지 보존하는 누적 master입니다. snapshot 테이블은 날짜별 관측값입니다. `missing_previous_*`는 현재 입력에서 빠진 행을 알려주는 기록이며 삭제 명령이 아닙니다.

**마스터 변경분을 만드는 것과 계산을 증분화하는 것은 다릅니다.** package/version은 신규·변경 행을 별도 출력하지만 snapshot 지표는 매 회차 대상 모집단을 계산합니다. bundle은 파일을 한 폴더로 모두 복사한 압축 파일이 아니라 여섯 단계의 정확한 위치·SHA를 묶는 명세입니다.

bundle 완료 순서는 모든 파일 업로드 → manifest 게시 → `_SUCCESS` 게시입니다. 소비자는 manifest SHA와 `_SUCCESS`를 모두 확인해야 합니다. `_current.json`은 완료 bundle을 가리키는 pointer이며, pointer만 보고 각 파일을 신뢰하지 않습니다.

<details>
<summary>파일과 manifest의 연결 자세히 보기</summary>

```text
pickage-curated/
  depsdev/v1/curated-bundle/
    _current.json                       ← 현재 완료 bundle 위치·SHA
    snapshot=S/run_id=R/
      [bundle manifest]                 ← 아래 6개 stage의 위치·SHA
      _SUCCESS                          ← 완료된 manifest 승인
  depsdev/v1/snapshot-reference/…
  depsdev/v1/package-version/…
  npm-downloads-interval/v1/…
  depsdev/v1/repository-metrics/…
  depsdev/v1/package-snapshot/…
  depsdev/v1/version-dependents-single/…
```

위 트리는 관계를 보여주는 축약도입니다. 대괄호는 설명 표기이며 실제 파일명으로 입력하지 않습니다. 각 stage의 manifest가 승인하는 파일 경로·행 수·크기·SHA를 읽습니다. 같은 날짜라는 이유만으로 서로 다른 run의 최신 파일을 조합하지 않습니다.

</details>

{{diagram:storage}}

Curated bundle은 `scope=RAW_TO_CURATED_ONLY`, `status=COMPLETE`, `calculation_complete=true`, `db_loaded=false` 계약을 가집니다. 실제 운영 게시 후 파일을 바꾸지 않는 immutable 입력이어야 합니다.

## 06. PostgreSQL 적재

Spring loader는 완료 bundle을 읽고 다음 순서로 처리합니다.

1. bundle manifest SHA, `_SUCCESS`, 여섯 단계 manifest와 승인 파일 목록을 검증합니다.
2. Parquet를 DuckDB로 읽고 DB COPY 입력으로 변환합니다. 초기 적재와 주간 적재는 아래처럼 처리 방식이 다릅니다.
3. 주간 적재는 파일별 staging 행과 receipt를 execution ID로 기록합니다.
4. 현재 DB bundle과 입력의 `parent_bundle`이 정확히 같은지 확인합니다.
5. package/version master, snapshot 날짜, 두 snapshot 테이블을 하나의 트랜잭션으로 게시합니다.
6. 행 수·키·기존 값·NULL 정책을 검증하고 `PUBLISHED` 이력을 커밋합니다.

{{diagram:loading}}

초기 적재는 부모가 없는 full bundle을 빈 DB에 넣습니다. 이미 데이터가 있는 DB는 데이터와 일치하는 full bundle을 `adopt-baseline`으로 검증한 뒤 기준 이력을 등록해야 합니다. 날짜가 같다는 이유만으로 baseline으로 채택하지 않습니다.

주간 적재는 직전 DB bundle이 입력 parent와 같은지 확인합니다. package/version은 변경된 행만 upsert하고, snapshot 행은 현재 날짜를 추가합니다. 중간 날짜를 건너뛰거나 다른 parent를 자동으로 이어 붙이지 않습니다.

`dependents_count`가 NULL인 행은 `package_version_snapshot` 적재에서 제외됩니다. 0은 유효한 계산 결과이므로 저장합니다. description·licenses·dependency 같은 다른 nullable 컬럼에 같은 제외 규칙을 적용하지 않습니다.

동일 bundle 재실행은 완료 이력을 확인해 건너뜁니다. 주간 적재 실패 후 같은 계약으로 재실행하면 검증된 staging receipt를 재사용합니다. 코드 계약이나 입력 SHA가 달라지면 기존 receipt를 억지로 재사용하지 않습니다.

| 구분 | 빈 DB 초기 적재 | 이후 주간 적재 |
| --- | --- | --- |
| 입력 | 부모 없는 full bundle | DB 현재 bundle과 parent가 일치하는 bundle |
| 중간 처리 | 최대 64MiB TSV 묶음 → 임시 테이블 COPY → 서비스 테이블 INSERT | 파일별 영구 staging + receipt |
| 공간 절감 | 처리한 TSV·임시 내용을 비움. 전체 baseline을 staging에 복제하지 않음 | 검증된 파일 staging을 재사용하고 변경된 마스터만 UPDATE |
| 실패 시 | 최종 트랜잭션 rollback, 처음부터 재실행 | 서비스 변경 rollback, 검증된 staging은 재사용 가능 |

64MiB는 전체 로더 메모리 제한이 아니라 **초기 COPY 파일 한 묶음의 크기 제한**입니다. 최초 적재도 마지막 검증까지 성공해야 서비스 데이터와 완료 이력이 함께 확정됩니다. 기존 DB의 baseline 채택은 추가/갱신이 아니라 실제 값 일치 검증입니다.

근거는 `backend/src/main/java/com/ssafy/pickage/domain/curatedload/CuratedBundleReader.java`, `CuratedBundlePublisher.java`, `backend/CURATED_LOAD.md`입니다.

## 07. 자동 실행과 장애 복구

dispatcher는 완료된 baseline 이후의 raw 회차를 날짜순으로 확인하고 한 호출에서 최대 한 회차를 실행합니다. 이전 회차가 끝나지 않으면 다음 회차를 앞질러 처리하지 않습니다.

| 상태 | 의미 | 다음 동작 |
| --- | --- | --- |
| `WAITING_INPUT` | raw·baseline·pointer가 아직 없음 | 실패 횟수 없이 다음 tick에서 재확인 |
| `RUNNING` | 실행 기록이 남아 있음 | 잠금과 프로세스를 확인한 뒤 재개 |
| `FAILED` | 일시 오류로 실행 실패 | 10·20·40·60분, 이후 60분 간격 재시도. 연속 10회면 차단 |
| `BLOCKED` | 입력·계약 손상 또는 반복 실패 | 자동 재시도 중단, 원인 해결 필요 |
| `COMPLETE` | bundle과 raw 참조가 검증됨 | 건너뜀 |

단계마다 `status.json`, `events/*.json`, manifest SHA, 시작·종료 시각과 예외를 기록합니다. 완료 checkpoint는 같은 입력·코드 계약·run_id·work-dir일 때만 파일을 재검증한 뒤 재사용합니다. 옵션이나 코드가 바뀌면 새 run_id가 필요합니다.

{{diagram:recovery}}

원천 manifest가 바뀌거나 완료 bundle 파일이 사라진 경우는 단순한 입력 대기가 아니라 차단 대상입니다. 다른 실행의 잠금을 지우지 않으며, dispatcher 재시도는 같은 원인이 해결된 경우에만 사용합니다. 운영 failover와 여러 호스트의 분산 잠금까지 보장하는 구조는 아닙니다.

Curated 게시가 끝났지만 상태 기록만 실패한 경우 `_SUCCESS`와 manifest가 완료 사실의 기준입니다. 반대로 manifest 게시 전에 프로세스가 끝나면 소비자는 bundle을 완료로 보지 않습니다.

## 08. 성능과 운영 자원

repository 기본 엔진은 DuckDB입니다. 입력을 columnar Parquet로 읽고 조인·그룹 집계를 한 프로세스 안에서 수행하므로 작은 표본에서는 Spark의 executor 시작·직렬화·네트워크 비용을 피할 수 있습니다. Spark 경로는 `native`/`docker` 비교 실험으로 남아 있습니다.

dependents는 대상 입력을 묶음으로 나누고 CPU 작업자에게 배분합니다. `--threads`와 `--memory-limit`은 전체 DuckDB 예산이고, 작업자 수가 늘면 작업자별 예산이 나뉩니다. Python·Node 메모리와 영구 중간 파일은 DuckDB 한도에 포함되지 않으므로 전체 컨테이너 상한을 별도로 잡아야 합니다.

제한된 런타임의 처리용 공간은 전처리 28GB, PostgreSQL staging/WAL/temp 17GB, loader 4GB, 로그 0.5GB 예약으로 합계 49.5GB입니다. **각 역할의 volume/container가 하나씩인 조건**이며, 복수 실행을 추가하면 같은 총합을 보장하지 않습니다. 영구 raw와 최종 Curated·DB 데이터는 이 처리 예산에서 제외합니다. 일반 Python 명령에 이 물리 디스크 제한이 자동으로 적용되는 것은 아닙니다.

메모리는 디스크와 별개의 제한입니다. DuckDB 한도, JVM heap, 컨테이너 전체 한도는 서로 다릅니다. 호스트 swap이 있어도 컨테이너가 swap을 허용하지 않으면 상한 초과를 구제하지 못합니다. 로더는 attempt 임시 작업 정리를 시도하고, 제한된 런타임은 소유한 scratch를 정리합니다. 재시도 증거·DB receipt 보존과 파일 정리를 구분하며 PostgreSQL의 WAL을 임의 삭제하지 않습니다.

과거 로컬 검증에는 8/31 초기 적재 약 3시간 49분, 9/14 주간 적재 약 25분의 측정이 있습니다. 이 수치는 당시 입력·하드웨어·범위의 결과이며 운영 전체 파이프라인 시간이나 최신 EC2 성능을 보장하지 않습니다. 실제 운영 결정을 위해서는 고정 manifest, 같은 CPU·메모리·디스크 조건, 단계별 시간·peak 메모리·spill을 함께 측정해야 합니다.

성능 로그는 단계 시간과 `CURATED_COPY_PROGRESS`, `CURATED_PUBLISH`를 분리해 봅니다. 저장소 지표의 결과 행 수가 최종 지표보다 클 수 있으며, 후보·선택 근거·관측 기록을 모두 검증하기 때문입니다. 전체 행을 다시 읽는 검증은 비용이 크므로 manifest·행 수·키 검증과 표본 검증의 범위를 명확히 기록합니다.

## 09. 운영 확인 순서와 용어

운영에서 처음 확인할 순서는 다음과 같습니다.

1. raw producer manifest와 완료 marker의 snapshot·SHA·행 수를 확인합니다.
2. Curated dispatcher의 `status.json`과 `_ops/preprocessing`을 확인합니다.
3. bundle manifest, 단계 marker, `_SUCCESS`, `_current.json`의 parent 연결을 확인합니다.
4. Spring loader 로그와 DB `etl_load_execution`, `etl_load_attempt`를 확인합니다.
5. snapshot 날짜·행 수·NULL 제외 건수·package/version key를 조회합니다.
6. 실패 시 동일 run_id 재개 조건과 코드 계약 SHA를 비교합니다.

| 확인할 곳 | 답할 수 있는 질문 |
| --- | --- |
| 전처리 `<work-dir>/<run-id>/status.json`, `events/*.json` | 어느 단계가 실행·실패했는가? |
| MinIO `pickage-curated/_ops/preprocessing/<날짜>/status.json` | 재시도 예정인가, 차단됐는가? |
| 로더 작업 경로의 `last-run.json`, `poll-state.json` | 어떤 bundle을 처리하고 있는가? |
| `CURATED_COPY_PROGRESS`, `CURATED_PUBLISH_SQL` 로그 | 읽기와 SQL 중 어디에 시간이 걸리는가? |
| DB `etl_load_execution`의 완료 이력 | 실제 서비스 반영이 커밋됐는가? |

운영 활성화 전에는 V14 staging 마이그레이션, 기존 DB의 baseline 일치, 자격증명과 노드별 자원 설정을 확인합니다. 이 문서 기준 최신 병합에서는 Docker가 꺼져 있어 DB 통합 시험을 다시 실행하지 못했습니다. 과거 로컬 DB 적재 성공과 최신 병합 후 단위 테스트 성공을 별도 증거로 봐야 합니다.

주요 코드 길잡이:

| 목적 | 위치 |
| --- | --- |
| 전체 실행·재개 | `pipeline/preprocessing/orchestration/dispatcher.py`, `runner.py` |
| 단계 연결·manifest | `pipeline/preprocessing/orchestration/stages.py` |
| package/version | `pipeline/preprocessing/curated/build.py` |
| downloads | `pipeline/preprocessing/downloads_interval/aggregate.py` |
| repository | `pipeline/preprocessing/repository_metrics/duckdb_transform.py` |
| requirements | `pipeline/preprocessing/requirements_resolution` |
| dependents | `pipeline/preprocessing/version_dependents` |
| Java 읽기·게시 | `backend/src/main/java/com/ssafy/pickage/domain/curatedload` |

용어를 짧게 정리하면 다음과 같습니다.

- **raw**: 수집된 원천 파일과 producer manifest.
- **Curated**: 정제·집계·검증을 끝낸 DB 소비용 bundle.
- **snapshot**: 특정 관측 날짜 또는 실제 관측 timestamp.
- **master**: package/version처럼 누적해서 유지하는 기준 데이터.
- **snapshot metric**: 날짜별 downloads·stars·open issues·dependents 값.
- **bundle**: 한 스냅샷의 모든 단계 결과와 manifest를 묶은 불변 단위.
- **parent bundle**: 주간 bundle이 이어지는 직전 완료 bundle.
- **receipt**: 특정 파일을 특정 loader 계약으로 staging했다는 DB 기록.
- **direct dependent**: 선언된 requirements 범위로 직접 연결되는 source version.
- **transitive usage**: 다른 의존성을 거쳐 간접으로 사용되는 관계이며 이 집계와 동일하지 않음.

현재 문서에서 “구현됨”은 코드와 계약에 존재한다는 뜻이고, “로컬 검증됨”은 별도 로컬 fixture·DB·MinIO에서 확인했다는 뜻입니다. 운영 서버에서 최신 raw 전체를 성공시켰다는 의미로 확장하지 않습니다. 세부 측정과 검증 범위는 `docs/worklogs/raw-to-curated-pipeline`의 작업 로그에서 확인합니다.

