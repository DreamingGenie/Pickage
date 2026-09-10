# 버전별 직접 의존자 수 집계

`aggregate`는 7번 작업이 만든 선언된 버전 간 관계를 이용해 승인된 대상
패키지 버전별 `dependents_count`를 계산합니다. 계산 범위는 직접 간선 하나이며,
연쇄 의존자와 자기 자신 제거는 수행하지 않습니다.

## 입력 계약

호출자가 소유한 DuckDB 연결에 다음 세 테이블을 **정확한 이름과 열 타입**으로
정규화해 준비해야 합니다. ID는 `INTEGER` 또는 `BIGINT`, 버전은 `VARCHAR`,
`snapshot_at`은 `DATE`, `published_at`과 `snapshot_timestamp`는 `TIMESTAMP WITH TIME ZONE`이어야
합니다. 암묵적인 형 변환은 하지 않습니다.

| 테이블 | 열 |
| --- | --- |
| `requirements_edges` | `source_package_id`, `source_version`, `target_package_id`, `target_version`, `snapshot_at`, `snapshot_timestamp` |
| `approved_sources` | `package_id`, `version`, `published_at`, `snapshot_at`, `snapshot_timestamp` |
| `approved_targets` | `package_id`, `version`, `published_at`, `snapshot_at`, `snapshot_timestamp` |

모든 행의 snapshot 값은 호출 인자와 정확히 같아야 합니다. `snapshot_timestamp`는 UTC로
정규화했을 때 `expected_snapshot_at`과 같은 날짜여야 합니다. 모집단은 비어 있지
않고 `(package_id, version)`이 유일해야 하며, ID는 양수이고 INT 범위 안이어야
합니다. 버전은 1~100자이고 공백만으로 구성되거나 NUL을 포함할 수 없습니다.
`published_at`은 NULL일 수 없으며 정확한 `snapshot_timestamp` 이후일 수도 없습니다.
간선은 양쪽 승인 모집단에 모두 존재해야 합니다.
안정 버전 선별은 이 커널의 역할이 아니며, upstream 승인 모집단에서 완료해야 합니다.

호출은 `expected_snapshot_at`(date), `snapshot_timestamp`(timezone-aware datetime),
`resolution_status="COMPLETE"`, `ready_for_dependents=True`를 요구합니다. 두 readiness
값은 upstream guard일 뿐, 운영 manifest·전체 대상 모집단·출력 파일 검증을 증명하지
않습니다. `PARTIAL` 또는 미완료 입력은 0건 결과도 만들지 않고 거부합니다.

## 결과

검증이 모두 끝난 뒤에만 새 `version_dependents` 테이블을 한 번 생성합니다. 기존 결과
또는 내부 scratch 테이블이 이미 있으면 덮어쓰지 않고 거부합니다. 결과 열은
`package_id`, `version`, `snapshot_at`, `snapshot_timestamp`, `dependents_count`이며,
모든 승인 대상 버전을 유지합니다. 간선은 네 개의 복합 키로 중복 제거한 뒤 대상별
서로 다른 source `(package_id, version)` 수를 세므로, 같은 source의 중복 선언은 한 번만
셉니다. 간선이 없어도 유효한 대상 모집단에는 `0`을 기록합니다.

실제 운영 어댑터, 검증된 전체 대상 모집단 연결, Parquet/output manifest 수명주기,
PostgreSQL 적재기는 후속 작업입니다. 이 모듈은 `_SUCCESS`를 만들거나 생산 결과를
publish-ready로 표시하지 않습니다. 실패 시 새 결과 테이블을 만들거나 기존 결과를
덮어쓰지 않습니다. 각 집계 시도는 결과·임시 테이블이 없는 별도 연결에서 실행합니다.

## 검증

기존 Python 환경에서 다음 전용 테스트를 실행합니다. 실제 7번 파일·DB에 접근하지 않고
합성 데이터만 사용합니다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m unittest pipeline.version_dependents.test_aggregate -v
```

실제 실행 결과와 입력 조사 범위는 [8번 작업 기록](../../docs/worklogs/S15P21A506-193/05-results.md)에 있습니다.
