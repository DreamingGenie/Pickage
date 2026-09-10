# 패키지 스냅샷 지표 통합과 PostgreSQL 적재

이미 검증·게시된 다운로드 구간 합계와 저장소 stars·open_issues를 승인 패키지 전체에 연결한다.
서비스 행의 키는 `(package_id, snapshot_at)`이며 새 package ID는 만들지 않는다.
다운로드의 COMPLETE·PARTIAL 값을 보존하고, 각 지표의 NULL과 실제 0을 독립적으로 유지한다.

## 입력과 출력

입력은 package/version Curated run, Projects 스냅샷 후보, 다운로드 구간 run, 저장소 지표 run이다.
각각 명시적 run ID와 SHA를 지정한다. 후보의 S·직전 P·정확한 시각과 두 지표의 모집단이 같아야 한다.
예상 밖 파일·행 누락과 중복은 실패로 처리한다.

통합 결과는 `pickage-curated/depsdev/v1/package-snapshot/snapshot=<S>/run_id=<run>/`에 게시한다.

| 출력 역할 | 내용 |
| --- | --- |
| `package_snapshot` | package_id, snapshot_at, downloads, stars, open_issues |
| `quality` | 패키지별 다운로드 상태·일수·사유와 저장소 선택 버전·경로·관측 시각·매핑 사유 |
| `package_identity` | PostgreSQL의 기존 ID/name 대조용 승인 패키지 목록 |

manifest에는 입력·정책·코드 SHA, 출력 파일 SHA·건수, 품질 요약과 원천 상세의 위치를 남긴다.
완료 표시를 게시하기 전에 파일을 원격에서 다시 읽고 SHA를 확인한다.

## 실행

저장소 루트에서 기존 Python 환경을 사용한다. 명령은 두 단계로 나뉜다.
통합 파일 생성 옵션은 `python -m pipeline.package_snapshot.build --help`에서 확인한다.
완료된 통합 run의 manifest SHA를 고정한 뒤 DB에 반영한다.

```powershell
python -m pipeline.package_snapshot.load `
  --snapshot 2026-08-31 `
  --curated-run-id <통합-run-id> `
  --manifest-sha256 <통합-manifest-sha256> `
  --execution-id <DB-실행-id> `
  --docker-container <기존-PostgreSQL-컨테이너> `
  --database <DB-이름>
```

로컬 psql을 사용하려면 `--docker-container` 대신 `--psql <실행파일>`을 지정한다.
DB 이름·사용자를 명시하고 접속 비밀번호는 기존 libpq 환경 설정으로 공급한다.
실행 보고서는 `data/package_snapshot/postgresql/<execution-id>/<attempt-id>/execution_report.json`에 남는다.

## DB 게시와 재실행

기존 `package_snapshot` 및 V1~V3 migration을 유지한다. 임시 테이블에 COPY한 후 전체 키·값·음수·
ID/name과 선행 게시 이력을 검증한다. 승인 package/version 현재 입력과 snapshot-reference 이력이
일치할 때 서비스 행·성공 이력·현재 포인터를 하나의 트랜잭션에서 확정한다.

품질 상세는 Curated 파일에 있으며 `etl_load_execution.input_metadata`와
`etl_load_attempt.quality_report`에서 manifest·파일·품질 요약까지 추적할 수 있다.
게시 전 실패하면 서비스 변경을 롤백하고 등록된 시도의 실패 이력을 남긴다.
DB 커밋 이후 확인 연결에 실패한 경우 보고서의 `COMMITTED_UNVERIFIED`는 DB 확인이 필요하다는 뜻이다.
이미 완료된 Curated의 `_SUCCESS`는 DB 실패 때문에 삭제하지 않는다.

동일 실행 ID·입력·적재 계약으로 재실행하면 DB의 모든 서비스 값을 다시 비교하며 행을 고치지 않는다.
다른 입력·코드 계약을 같은 실행 ID로 실행하거나 같은 기준일의 다른 출처 값을 덮어쓰면 실패한다.
새 입력에는 새 run·실행 ID를 사용한다. 이 관측 기반 경로에서 현재 모집단을 과거 관측 목록으로 복제하지 않는다.

## 배포일로 재구성한 전체 기간

`python -m pipeline.package_snapshot.history --help`는 별도 승인 정책인
`package-snapshot-history-v1`으로 과거 기준일을 처리한다. 현재 승인 버전 중 정확한 기준 시각까지
배포된 버전이 있는 패키지를 포함한다. 저장소가 없어도 패키지는 유지하고, 배포일을 모두 모르는
패키지는 과거에서 제외한다. 대표 저장소는 당시 배포된 유효 후보의 기존 우선순위로 선택한다.

패키지 대상·저장소 연결은 **재구성한 이력**이고, stars·open_issues는 해당 시각의 실제 Projects 관측,
다운로드는 실제 `[P,S)`의 유효 날짜 합계다. 과거 원천의 부재나 현재 패키지 목록에서 사라진 대상을
복원할 수 없다는 한계를 manifest에 기록한다. 기존 최신 관측 스냅샷과 게시 포인터는 유지한다.

명시적인 입력 설정은 `population`, `repository`, `downloads`의 승인 run/SHA, `candidate_path`와
`candidate_sha256`, 로컬 `curated_output_root`·`repository_local_root`·`projects_root`·`downloads_root`,
날짜별 `projects_runs`를 받는다. `expected_date_counts`를 지정하면 독립 산정한 날짜별 모집단과도 대조한다.
전체 입력을 승인 manifest의 파일 SHA로 검사한 뒤 상태를 고정하고, 날짜별로 생성·검증·게시·DB 적재한다.
실패한 실행은 같은 설정과 run ID로 재개한다. 중단 후에는 DB의 PUBLISHED 날짜를 제외한 목록을
`--snapshots <날짜> ...`에 지정한다. 옵션을 생략하면 이미 완료한 날짜까지 전수 대조하며 중복 삽입하지 않는다.
선택 실행의 결과는 `SELECTED_DATES_PUBLISHED`이므로 전체 완료는 승인 달력·날짜별 실제 건수·
최신 기준일 보존 결과를 함께 확인한다. 이전 `result.json`은 새 실행이 끝날 때까지 남아 있을 수 있다.

실제 명령·날짜별 목표 건수·대표 날짜 검증·전체 실행 결과는
[전체 기간 작업 기록](../../docs/worklogs/S15P21A506-288/08-full-history-plan.md)과
[직접 조회 SQL](../../docs/worklogs/S15P21A506-288/09-inspect-history.sql)에 남긴다.

## 검증과 기록

```powershell
python -m unittest pipeline.package_snapshot.test_input pipeline.package_snapshot.test_build pipeline.package_snapshot.test_load -v
$env:PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER = '<기존-검증-컨테이너>'
python -m unittest pipeline.package_snapshot.test_postgres -v
python -m unittest pipeline.package_snapshot.test_history_build pipeline.package_snapshot.test_history_postgres -v
```

DB 테스트는 `pickage_288_test_<UUID>`라는 새 격리 DB를 만들고 종료 시 해당 DB만 삭제한다.
환경 변수가 없으면 DB 테스트가 skip되므로 실제 DB 검증과 구별해야 한다.
초도 실행 결과·승인 해시·조회 방법·미실행 범위는
[S15P21A506-288 작업 기록](../../docs/worklogs/S15P21A506-288/README.md)에 남긴다.
