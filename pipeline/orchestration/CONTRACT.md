# raw 인수 및 Curated 소비 계약 v1 / 주간 v2

## 주간 v2 확장

기존 v1 명시적 full 요청을 유지한다. v2는 `raw_refs.versions_full` 대신
`raw_refs.versions_min`을 요구하고 다음 필드를 추가한다.

| 필드 | 계약 |
| --- | --- |
| `parent_bundle` | 직전 **전체 완료** bundle의 run_prefix / manifest_sha256 / snapshot |
| `download_history_refs` | 선택 사항. 추가 downloads run_id / bucket / key / sha256 목록; 순서가 우선순위 |
| `targets.dependents` | raw 또는 `pickage-curated/depsdev/v1/preprocessing-targets/`의 고정 Parquet |

v2 부모는 현재 날짜보다 이전이어야 한다. package/version parent는 해당 bundle 안의
package_version stage와 일치해야 하며, 부모 달력 전체를 수정 없이 이어받는다.
`curated-bundle/_current.json`은 `_SUCCESS` 게시 뒤 ETag 조건부 쓰기로 갱신한다.
중간 단계만 완료된 package-version pointer를 다음 부모로 채택하지 않는다.

weekly CLI는 target CSV 원본 해시와 행 수를 검증한 뒤 이름 중복을 제거한다.
versions_min 필수 컬럼은 full에서 Description / Licenses / source_repo를 제외한 컬럼이다.
메타데이터 보존·상속과 master/changes 산출물 규칙은 README의 주간 절을 따른다.
파생 weekly_versions는 Curated 명세에 등록하며 원천 versions_min의 SHA를 계보로 유지한다.

이하 v1 기본 계약은 v2에서 명시적으로 변경한 필드를 제외하고 공통 적용한다.

## 요청 고정

| 항목 | 의미 |
| --- | --- |
| format_version | 정수 1 |
| run_id | 이번 전처리 식별자, 영문/숫자로 시작, 영문·숫자·`_`·`-`, 최대 64자 |
| snapshot / snapshot_timestamp | ISO 날짜와 동일 날짜의 정확한 UTC `Z` 관측 시각 |
| bronze_run_id | versions_full·requirements·이번 Projects의 기존 수집/검증 run ID |
| raw_refs | versions_full, requirements, projects, downloads의 bucket/key/SHA-256 |
| calendar_refs | 날짜순 Projects raw 명세 목록. 이번 날짜로 끝나며 실제 직전 스냅샷을 포함한다 |
| parent | 현재 완료 package-version `_current.json`의 run_prefix/manifest_sha256/snapshot. 최초 실행만 null |
| targets.dependents | 별도 target 이름 Parquet 객체의 bucket/key/SHA-256 |
| options | workers, threads, memory_limit 및 repository_engine(native/docker) |

달력의 완전성은 생산자 인수 범위에 속한다. 목록 밖의 BigQuery 날짜를 이 실행기가 조회하지 않는다.
직전 날짜를 임의로 7일 전이나 DB의 마지막 적재일로 정하지 않는다. ID 부모가 요청 날짜보다 미래이면 거부한다.
같은 날짜를 새 run ID로 다시 계산할 때는 같은 날짜의 최신 ID 부모도 허용한다. ID 계보와 다운로드의
직전 관측 날짜는 별개이며, 재처리에서도 실제 이전 관측일이 포함된 calendar_refs를 유지한다.

raw 버킷은 기존 `pickage-raw`, 출력은 `pickage-curated` 계약을 사용한다.
자격증명은 요청에 넣지 않고 기존 MinIO 설정 파일에 둔다. 알 수 없는 요청 필드는 거부한다.

## raw 생산자 형식

deps.dev 입력은 기존 MinIO ingest의 형식을 그대로 사용한다.
`depsdev/v1/TABLE/snapshot=S/run_id=R/run_manifest.json`의 `contract_version=1`, `status=PASSED`,
`verification=GET_SHA256_ALL_FILES`, table/snapshot/run_id와 `files[].key/bytes/sha256`를 검사한다.
빈 `_SUCCESS`, `source_manifest.json`의 SHA와 done/ok 수집 receipt도 필요하다.
원본 receipt를 로컬 `_MANIFEST.json`으로 복원하되 원격 원본은 수정하지 않는다.

| 데이터 | 필요한 주요 컬럼 |
| --- | --- |
| versions_full | Name, Version, published_at, is_release, ordinal, Description, Licenses, Deprecated, source_repo, SnapshotAt |
| requirements | Name, Version, Dependencies, PeerDependencies, OptionalDependencies, SnapshotAt |
| projects | Type, project_name, StarsCount, OpenIssuesCount, SnapshotAt |
| dependents 대상 | `name VARCHAR` 한 컬럼. NULL·빈 이름·중복 이름 불허 |

deps.dev Parquet의 TIMESTAMP는 UTC를 나타내는 기존 naive-UTC 계약이다.
각 snapshot의 `SnapshotAt`이 요청 시각과 일치해야 한다. `Dependencies` 등은 기존
`STRUCT(Name VARCHAR, Requirement VARCHAR)[]` 형식을 사용한다.
`versions_full.dependency_error`가 없으면 참조 수 품질에서 unknown으로 기록한다.

downloads 입력은 기존 `npm-downloads/v1/run_id=R/` Bronze 계약이다.
명세 SHA, `_INPUT.json`, SHA와 개행으로 된 `_SUCCESS`, 품질 consistency_checks,
target CSV·status Parquet·daily Parquet의 파일 목록을 검사한다. 수집 API를 호출하지 않는다.

## 결과 묶음과 완료 판단

`depsdev/v1/curated-bundle/snapshot=S/run_id=R/run_manifest.json`은 다음을 고정한다.

- 전체 request 및 생성 코드 계약 SHA
- snapshot/package_version/downloads/repository/package_snapshot/dependents의 정확한 명세와 SHA
- 각 dataset의 완료 marker SHA, 파일 key/bytes/SHA, 품질 정보
- `scope=RAW_TO_CURATED_ONLY`, `status=COMPLETE`, `db_loaded=false`

마지막 `_SUCCESS`는 `{"manifest_sha256":"실제 명세 바이트의 SHA"}`다.
소비자는 먼저 이 marker를 읽고 명세 SHA 및 파일 SHA를 확인한다. 원래 dataset의 `_SUCCESS`나
mutable `status.json`만으로 전체 전처리 완료를 판단하지 않는다. 이 상태는 DB 적재 성공을 뜻하지 않는다.

## 서비스용 Parquet

| 결과 | 컬럼과 타입 | 행 키 |
| --- | --- | --- |
| package | package_id INTEGER, name VARCHAR, repo_url VARCHAR(NULL 허용) | package_id |
| version | version VARCHAR, package_id INTEGER, published_at TIMESTAMP, ordinal BIGINT, description VARCHAR, licenses JSON, deprecated VARCHAR, dependency JSON | package_id + version |
| package_snapshot | package_id INTEGER, snapshot_at DATE, downloads BIGINT, stars INTEGER, open_issues INTEGER | package_id + snapshot_at |
| version_dependents | package_id INTEGER, version VARCHAR, snapshot_at DATE, dependents_count BIGINT(NULL 허용) | package_id + version + snapshot_at |

실제 파일 경로는 bundle의 stage descriptor 및 원래 dataset manifest에 들어 있다.
JSON 컬럼은 Parquet의 기존 JSON 논리 타입/UTF-8 표현을 보존하며 JVM 쪽에서 해당 표현을 해석한다.
기존 version.dependency에는 dependencies/peerDependencies/optionalDependencies 객체가 들어간다.
package_ids·quality·resolution_lookup 및 snapshot 기준 자료는 관리/검증 산출물이며 자동으로 서비스 테이블에 적재하지 않는다.

## 0·NULL·PARTIAL

- 다운로드는 기존 구간 집계 정책을 유지한다. 유효 일자가 있으면 PARTIAL 합계도 보존하고 coverage/이유를 함께 기록한다.
  관측이 없거나 대상 밖이면 해당 사유와 NULL을 유지한다.
- 저장소 지표는 같은 관측 시각·정규화된 저장소 경로의 관측을 사용한다. 매칭되지 않으면 NULL과 품질 사유를 남긴다.
- dependents는 dependencies 종류만 집계하며, 동일 target 버전을 참조한 **서로 다른 source package-version 수**다.
  이전에 출시된 source 버전도 포함한다. 중복 선언은 source별 한 번으로 합친다.
- 선택된 target 이름의 자격 있는 버전은 계산 결과가 없으면 0이다. 선택 밖 또는 target 자격 밖인 Curated 버전은
  NULL이며 quality에 `NOT_SELECTED_TARGET`/`INELIGIBLE_TARGET_VERSION`을 남긴다. 원래 Curated version 행은 모두 보존한다.
- semver 미해석, 누락 요구사항, NULL 목록, 추출 오류/추출 상태 미확인은 `resolution_status=PARTIAL`에 남는다.
  `calculation_status=COMPLETE`와 구분한다. 계산 완료를 모든 관계가 완전하게 해석됐다는 뜻으로 바꾸지 않는다.

Java 인수 범위는 완료 묶음 선택·파일 읽기까지다. DB 타입 변환, 제약조건, 트랜잭션, 적재/게시 이력,
PARTIAL 데이터의 서비스 노출 정책은 후속 적재 구현에서 이 품질 정보와 함께 결정한다.
