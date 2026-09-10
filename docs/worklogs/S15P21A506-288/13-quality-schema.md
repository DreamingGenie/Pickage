# quality 공통 형식과 기존 파일 호환

## 새로 생성하는 파일

관측·과거 생산자는 모두 manifest의 `quality_schema`에 `package-snapshot-quality-v2`를 기록한다.
두 경로의 quality Parquet는 **같은 이름·순서·자료형을 가진 30개 컬럼**을 사용한다.
정확한 컬럼 계약은 `pipeline/package_snapshot/quality.py`의 `QUALITY_SCHEMA`다.
상위 dataset은 `package-snapshot`, 역할은 `quality`, manifest 형식 버전은 기존 1을 유지한다.

| 정보 | 공통 컬럼 | 의미 |
| --- | --- | --- |
| 대상 | `package_id`, `name`, `snapshot_at` | 승인된 패키지와 기준일 |
| 다운로드 | `previous_snapshot_at`, `download_sum`, `expected_days`, `observed_days`, `valid_days` | 실제 `[P,S)` 구간과 유효 날짜 합계 |
| 다운로드 품질 | `data_status`, `null_reason`, `quality_reasons` | COMPLETE·PARTIAL·UNAVAILABLE 및 사유 |
| 다운로드 산출물 계보 | `input_manifest_sha256`, `policy_sha256`, `aggregation_policy_sha256` | 관측 경로가 소비한 별도 다운로드 구간 산출물의 해시 |
| 저장소 선택 | `repository_version`, `repository_ordinal`, `repository_repo_url` | 선택한 버전·우선순위·저장소 |
| 저장소 경로 | `repository_provider`, `repository_project_path`, `repository_comparison_project_path`, `repository_observed_project_path` | 별도 저장소 선택 산출물에 기록된 매칭 근거 |
| 저장소 시점 | `repository_snapshot`, `repository_snapshot_timestamp`, `repository_observed_timestamp` | 요청 기준일·정확한 시각·실제 관측 시각 |
| 저장소 상태 | `repository_reason`, `repository_mapping_status` | 선택·미관측·충돌 등의 사유와 연결 여부 |
| 저장소 지표 | `stars`, `open_issues` | 서비스 값과 대조하는 실제 지표 |
| 재구성 배포일 | `first_published_at`, `selected_published_at` | 과거 포함 자격과 선택 버전의 배포일 |

`repository_mapping_status`는 `MATCHED`, `NO_SELECTED_REPOSITORY`,
`NO_EXACT_PROVIDER_PATH_MATCH`를 사용한다. MATCHED는 연결 성공이며 지표 유효성을 보장하지 않는다.
충돌한 관측이 연결됐으면 MATCHED와 PROJECT_METRIC_CONFLICT가 함께 기록되고 지표는 NULL이다.

관측 경로는 이번 집계에서 배포일 기반 포함 자격을 계산하지 않으므로 두 배포일 컬럼은 NULL이다.
과거 경로는 별도 다운로드 구간 run을 소비하지 않고 원천 일별 데이터를 직접 집계하므로
그 run에 해당하는 세 해시는 NULL이다. 전체 원천 계보는 기존 history manifest에 보존한다.
과거 quality에서 별도로 보존하지 않던 ordinal·provider·경로 상세도 NULL로 두며 추정값을 채우지 않는다.
저장소 URL·선택 버전·정확한 관측 시각은 기존 값을 보존한다.

## 이미 게시된 파일

기존 `_SUCCESS`, manifest, Parquet와 DB 게시 이력은 수정하지 않는다.
marker가 없는 기존 파일은 호출한 관측·과거 로더와 **정확한 이전 컬럼·자료형**을 함께 확인한다.
알 수 없는 marker, 빠진 컬럼, 다른 자료형은 실패시킨다.

- 관측 이전 형식: 기존 26개 품질 컬럼에 서비스 파일의 stars·open_issues와 NULL 배포일을 연결해 읽는다.
- 과거 이전 형식: 기존 17개 컬럼을 공통 이름으로 읽고, 승인 ID/name 파일과 manifest 구간을 연결한다.
  저장소 연결 상태는 기존 URL·관측 시각으로 판정한다. 파일을 다시 쓰지 않는다.
- 양쪽 로더는 같은 검사 함수로 이름·키·값·날짜·유효 일수·NULL·부분합·저장소 상태를 검증한다.
  과거 로더는 배포일에 따른 포함 자격도 추가 검증한다.

## 재검증과 재생성 구분

기존 관측 산출물의 DB 재검증은 `pipeline.package_snapshot.load`로 실행한다.
관측 `build`는 원천으로부터 산출물을 생성·재현하는 별도 명령이며 기존 코드 계약 검사를 유지한다.
코드가 바뀐 뒤 새 형식 산출물이 필요하면 새 Curated run ID를 사용한다.

과거 `history`는 생성과 DB 적재를 함께 실행하므로, 저장된 산출물이 있으면 승인된 입력·정책·
원천 Projects 참조·구간·파일 SHA를 확인하고 해당 바이트를 그대로 사용한다.
현재 검증 코드 해시는 새 attempt에 남기고 원래 산출물의 생성 코드 해시는 보존한다.
기존 파일을 재검증할 때는 전체 버전 상태를 다시 만들지 않는다. 새 날짜 생성에 필요한 상태는
현재 코드 해시별 캐시에 생성하며 이전 상태 캐시를 덮어쓰지 않는다.

형식이 같아도 집계·포함 대상 정책이 바뀌면 동일한 입력으로 간주하지 않는다.
정책 변경은 별도 승인 정책·입력·run으로 처리한다. 이 호환 처리는 재적재 승인을 뜻하지 않는다.
