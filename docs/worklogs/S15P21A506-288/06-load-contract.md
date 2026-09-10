# 06. 패키지 스냅샷 통합 적재 계약

상태: **초도 한 기준일의 구현·게시·로컬 DB 적재·전수 검증 완료.**
[범위](01-scope.md) · [계획](02-plan.md) · [입력 기록](evidence/input-handoff.json)

이 문서의 본문은 기존 관측 기반 초도 계약을 보존한다. 사용자 승인에 따른 전체 기간 재구성은
별도 `package-snapshot-history-v1` 정책과 [전체 기간 계약·계획](08-full-history-plan.md)을 따른다.
재구성 입력의 실제 원천 SnapshotAt을 과거 날짜로 바꾸지 않으며, 기준 원천 시점과 대상 지표 시점을
서로 다른 필드로 기록한다. 기존 2026-08-31의 승인 manifest·서비스 값은 변경하지 않는다.

## 승인 입력

| 입력 | 선택 대상 | 역할 |
| --- | --- | --- |
| 패키지 모집단 | `curated-20260907-v2`의 `package/data` | S의 전체 package ID·name 집합. manifest SHA `a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3` |
| 스냅샷 기준 | Projects 후보와 DB `snapshot-reference` 이력 | S·정확한 시각·직전 P 검증. 후보 SHA `d22099ce22031deb47993f5c66b633d3754fd0625dbb1dcbaafc60070f8afaa7` |
| 다운로드 구간 결과 | `downloads-interval-278-20260909-v1` | manifest SHA `7dfc0cb5b76102d35f9baa28e03d7370bbd0d9a241b9c4a58ba3de8a95906377` |
| 저장소 지표 결과 | `repository-metrics-20260909-v3` | manifest SHA `ca92eaa351fcd2ecd7d9355d3b5ee0635d9046ffecdb8fc946d28b226ecc0f30` |

두 지표의 모집단 run·SHA와 S=`2026-08-31`, 원천 시각 `2026-08-31T21:01:10.517131Z`가
일치해야 한다. 다운로드 P=`2026-08-24`는 승인 전체 스냅샷 목록의 직전 날짜다.
`snapshot-time-v1`, `downloads-interval-v1`, `repository-metrics-v2` 정책과 각각의 해시를 보존한다.

선택은 `_current` 포인터나 디렉터리 전체 glob 대신 명시적 run과 manifest 목록으로 한다.
다운로드는 `data/interval_downloads.parquet`, 저장소 지표는 manifest의 `dataset=metric/data`를
주 지표로 소비한다. 품질 근거는 다운로드 품질 컬럼·상세 파일과 저장소 `quality/selection` 등을
역할별로 명시하여 사용한다. 전체 후보·관측 파일을 지표 행으로 함께 읽지 않는다.

다운로드 `_SUCCESS`는 manifest SHA의 텍스트이며, 저장소 지표는 같은 SHA를 담은 JSON이다.
각 생산 모듈의 형식대로 검증한다. 완료 표시·manifest·소비 파일 크기/SHA·schema·행 수를
확인하고, 게시 직전에도 입력 불변성을 재확인한다. 지표값 NULL과 입력 파일/행의 누락은 다르다.
정상 생산 계약상 전체 모집단 행이 있어야 하므로 예상하지 못한 행 누락·중복은 적재 실패다.

## 서비스 행과 품질

승인 `package` 집합을 기준으로 각 지표의 전체 키 집합이 같음을 검증한 뒤
`(package_id, snapshot_at)`으로 결합한다. 누락된 입력 행은 실패이며 지표 값 NULL은 유지한다.
다운로드 수집 대상이나 저장소 매핑 성공 목록을 모집단으로 사용하지 않는다.

| 서비스 컬럼 | 입력 | 검증·보존 |
| --- | --- | --- |
| `package_id INT` | 승인 package ID | 새 ID 없음, name/ID 계보·FK 확인 |
| `snapshot_at DATE` | 승인 기준일 S | snapshot FK와 정확한 원천 시각 이력 확인 |
| `downloads BIGINT NULL` | `download_sum` | COMPLETE와 PARTIAL 값을 그대로 보존, UNAVAILABLE은 NULL, 실제 0 유지 |
| `stars INT NULL` | 저장소 `stars` | 음수·INT 범위 초과 거부, 원천 NULL과 실제 0 유지 |
| `open_issues INT NULL` | 저장소 `open_issues` | stars·downloads와 독립적으로 값·NULL 보존 |

서비스 PK는 `(package_id, snapshot_at)`이고 기존 V1 테이블 계약을 유지한다.
다운로드 `data_status`, 기대·관측·유효 일수, `null_reason`, `quality_reasons` 및 날짜별 상세를
버리지 않는다. 저장소 선택 버전·URL·provider·경로·관측 시각·매핑 상태와 NULL 근거도 유지한다.
여러 패키지가 한 저장소를 가리키면 해당 관측값을 각각 연결하며 저장소 지표를 합산하지 않는다.

이 품질 정보는 검증 가능한 상세 산출물과 DB 실행 이력의 품질 요약·manifest 참조로 연결한다.
실행 이력에서 입력 두 지표의 SHA와 상세 품질 위치까지 추적 가능해야 한다.
P-03에서 신규 migration 없이 기존 V1~V3를 유지하기로 확정했다. 통합 `quality.parquet`에
패키지별 다운로드 상태·일수·사유와 저장소 선택 근거를 함께 보존한다. 원천의 날짜별 품질과
미매칭 상세는 입력 manifest의 파일 key·크기·SHA로 연결한다.
`etl_load_execution.input_metadata`에 통합 manifest 전체를, `etl_load_attempt.quality_report`에
입력 manifest·출력 파일·품질 요약·전수 대조 범위를 기록한다. 서비스 값의 NULL은 그대로 유지한다.

## 통합 게시와 DB 반영

통합 Curated는 두 원천을 덮어쓰지 않는 별도 실행으로 만든다. 게시 경로는
`pickage-curated/depsdev/v1/package-snapshot/snapshot=<S>/run_id=<run-id>/`다.
초도 실행 ID와 SHA는 [실제 결과](05-results.md)에 기록했다.
manifest에는 패키지·스냅샷·두 지표의 입력 식별자/해시, 정책/코드 해시, 출력 파일·행 수·품질을 남긴다.
출력 역할은 서비스 값 `package_snapshot`, 품질 `quality`, DB의 ID/name 대조용 `package_identity`다.
DB 적재는 통합 결과의 명시적 run ID와 manifest SHA를 요구하며, 기존 완료된 입력을 재사용한다.

1. 입력 검증 → 통합 결과 생성 → 전체 키·값·품질 검증 → 파일 게시·원격 GET/SHA 대조 → 완료 표시 게시.
2. 완료된 통합 manifest를 고정하고 DB 실행·시도를 등록한다. 입력·검증 실패를 성공 상태로 바꾸지 않는다.
3. 실행별 staging에 COPY하고 전체 모집단·PK/FK·음수/범위·NULL·원천 대조를 검증한다.
4. 트랜잭션 안에서 대상과 선행 이력을 다시 확인하고 서비스 행·실행 이력·현재 게시 포인터를 함께 반영한다.
5. DB에서 실제 행 수·ID·값·품질 연결을 대조한 결과를 실행 보고서와 작업 기록에 남긴다.

DB 대상은 선행 package/version manifest 및 snapshot 후보 이력과 일치해야 한다.
실패 시 서비스 변경과 성공 상태 확정을 롤백하되 실패 시도의 근거는 남긴다.
DB 실패로 이미 성공한 통합 또는 선행 Curated의 `_SUCCESS`를 삭제하지 않는다.

## 재실행과 기존 데이터 보호

- 같은 실행 ID·입력으로 재실행하면 DB의 실제 값을 다시 비교하고 변경 없이 재검증 기록을 남긴다.
- 입력·정책·코드 계약이 달라진 실행을 기존 ID로 위장하지 않는다. 새 입력에는 새 실행 ID가 필요하다.
- 같은 S의 기존 지표가 다른 입력에서 왔거나 값이 다르면 자동 덮어쓰지 않고 충돌로 처리한다.
- 실패한 시도 재실행, writer 잠금, commit 직전 입력·선행 상태 확인으로 부분 게시와 경쟁을 방지한다.
- package·version·snapshot·다른 기준일·기존 성공 이력과 원천 객체는 보존한다.
- 재현 명령·실행 ID·조회 SQL은 [실제 결과](05-results.md)와 [모듈 안내](../../../pipeline/package_snapshot/README.md)를 따른다.
