# 372 로컬 주간 Curated 연결 작업

## 변경 범위와 계획
로컬에서 versions_min 입력, 기존 메타데이터 보존과 신규 버전 상속, 추가·변경 master 출력, 입고 완료 후 한 명령 실행을 연결한다. 서버/운영 DB/배포는 변경하지 않는다. 세부 계획: .omx/plans/372-local-weekly-curated.md.

1. 입력 및 parent 계약과 버전별 메타데이터 상속 구현
2. package/version 차분·누적 master와 snapshot 산출물 연결
3. 입고 manifest 기반 요청 자동 생성과 다운로드 회차 처리
4. 로컬 단위·통합 검증, 격리 MinIO 두 회차 및 재개 검증

## 실행 기록
- 372 브랜치에서 시작. 기존 evidence 폴더는 보존한다.
- 메타데이터 adapter, master 차분, 주간 요청 생성은 파일 소유권을 분리해 병렬 구현한다. runner/게시 계약 통합은 주 작업에서 수행한다.
- 로컬 Docker 정상 확인. 원격 서버 접속 없이 진행한다.

## 결과
2026-09-16 로컬 구현·검증 완료. 원격 서버·운영 배포·DB는 변경하지 않았다. 커밋/푸시는 하지 않았다.

### 실제 변경한 내용

| 영역 | 변경 |
| --- | --- |
| `weekly_request.py`, CLI | `weekly --snapshot --run-id --work-dir`로 입고 원천과 완료 부모를 고정하고 전체 실행. CSV는 승인 SHA/행 수 확인 후 대상 이름 중복 제거 |
| `contracts.py`, `intake.py` | 기존 v1 full 요청 유지, v2 min 요청·완료 bundle 부모·추가 다운로드 회차 지원 |
| `weekly_metadata.py` | 기존 description/licenses와 package repo_url 보존. 신규 package는 NULL, 신규 version은 현재 ordinal 기준의 이전 회차 후보에서 상속 |
| `curated/build.py`, `transform.py`, `changes.py` | 현재 스냅샷 모집단, 누적 master, INSERT/UPDATE 변경분, 원천 누락 품질, 상속 출처를 함께 게시 |
| `repository_metrics/input.py`, stages | Curated 승인 명세의 derived weekly_versions를 repository 계산에 연결. raw min을 full로 위장하지 않음 |
| downloads interval | 여러 입고 회차의 `(name,date)`를 현재→추가 회차 순서로 선택. 원본 검증 후 중복 병합, 충돌 사례/제외 건수 기록, raw·derived 해시 재검증 |
| runner, `weekly_parent.py` | 전체 완료 marker 뒤 bundle current pointer CAS. 중간 단계 pointer는 다음 부모로 사용하지 않음. 완료된 과거 요청 재실행으로 pointer 후퇴 방지 |
| Node runtime | Linux npm의 `prefix/lib/node_modules` 경로도 발견. Windows 기존 경로 유지 |

역의존 계산의 importer 범위는 전체 적격 버전을 유지한다. 대상 목록만 collector의 고정 CSV에서 가져온다.
현재 snapshot의 지표는 전체 계산하며, master 차분 파일 생성과 계산 자체의 증분화를 구분한다.
누락된 과거 package/version은 현재 snapshot 결과에서 빠지더라도 누적 master에서 삭제하지 않는다.

### 실행 및 검증 결과

- 로컬 회귀: **149개 중 147개 통과, 2개 skip, 실패 0**, 26.234초.
  - skip은 `DOWNLOADS_INTERVAL_MINIO_TEST=1`로 별도 실행하는 기존 선택 테스트 2개다.
  - MinIO 실제 통합은 아래 별도 전체 파이프라인 시험으로 실행했다.
- 격리 MinIO 작은 fixture: full→min 6단계 완료, 중간 실패·재개·완료 요청 재사용 통과.
- 격리 MinIO **합성 1,000개** 최종 시험: 통과, 59.359초.
  - 이전 package 999개 → 현재 package 1,000개, 현재 version 1,002개.
  - 누적 master package 1,001개: 현재 원천에서 빠진 `obsolete`도 보존.
  - 기존 package `alpha`의 신규 version 2개는 모두 이전 회차 `1.0.0`에서 복사. 같은 회차끼리 연쇄 상속하지 않음.
  - 신규 package 2개, 기존 version deprecated 변경, 기존 ID·description/licenses 보존 검증.
  - repository 단계 직전 강제 실패: 전체 bundle current는 이전 회차 유지.
  - 공개 `weekly` CLI로 재개해 전체 완료. 완료된 요청 재실행 시 stage 호출 없이 객체 재검증.
  - 과거 full 요청 재실행 후에도 최신 bundle pointer 유지.
- 다운로드 추가회차 실제 `prepare → aggregate → revalidate` 검증:
  - 파일명 순서와 관계없이 primary 우선, history 전용 패키지 행 보존.
  - 값 충돌/동일 값 중복 구분, derived 파일 변조 차단.
  - 같은 원천의 name/date 중복, raw 물리 날짜/partition 불일치 거부.
- 변경·추가 Python 26개 AST 파싱, `git diff --check` 통과.

로그: [최종 검증 요약](evidence/weekly-local/verification-summary.json),
[회귀 로그](evidence/weekly-local/data-weekly-regression.log),
[1,000개 통합 로그](evidence/weekly-local/data-weekly-1000-final.log).
합성 검증의 소요 시간은 테스트 실행 시간이며 운영 성능 측정 결과로 사용하지 않는다.

### 로컬 환경과 격리

- Python/Java/Node/Spark는 기존 `pickage-spark-experiment:runtime-3.5.3` 이미지 사용.
  Spark 3.5.3, DuckDB 1.5.5. runner 2 CPU / 4 GiB, MinIO 1 CPU / 512 MiB 제한.
- 전용 내부 Docker network `pickage-weekly-372-local`, 전용 volume `pickage-weekly-372-data`.
- 전용 MinIO container `pickage-weekly-372-minio`, 호스트 바인딩 `127.0.0.1:19020`.
  기존 `pickage-local-minio-1`과 9000/9001 포트 및 볼륨은 변경하지 않았다.
- 운영과 동일한 MinIO tag를 pull했으나 `pull access denied`로 실패했다.
  기존 로컬 이미지 `RELEASE.2025-09-07T16-13-09Z`로 검증했으며 운영 버전 호환성은 미검증이다.
- 최종 시험 후 runner는 자동 제거됐고 전용 MinIO는 **중지**했다. 결과 객체가 있는 전용 volume과
  중지된 container는 남겼다. 필요하면 `docker start pickage-weekly-372-minio`로 로컬 증거를 확인할 수 있다.
- 원래 작업 폴더 `S15P21A506`의 Git 상태는 기존 untracked `pipeline/duckdb_ui.py`만 유지했다.

### 발견한 문제와 해결

1. Linux 이미지의 npm module 경로를 Windows 방식으로만 탐색해 최초 실행이 실패했다.
   Unix 경로 fallback 추가 후 전체 실행 통과.
2. 다운로드 원본 CSV에는 동일 이름이 중복될 수 있었다. 원본 행 수와 SHA는 그대로 검증하고
   dependents 대상 Parquet를 만들 때 이름을 중복 제거하도록 native 다운로드 정책과 맞췄다.
3. 병렬 편집 중 실행한 초기 시험은 코드 SHA 변경을 감지해 중단됐다. 코드 고정 후 다시 실행해 통과했다.
4. 회차 병합 전 원본 중복/날짜 검증이 없으면 잘못된 입력이 정상처럼 보일 수 있었다.
   원본 검증을 먼저 수행하고, 다른 회차 사이의 중복만 병합하도록 수정했다.
5. 신규 버전 후보를 이전 ordinal로 찾으면 순번이 바뀐 스냅샷에서 잘못 상속할 수 있었다.
   현재 min과 이전 master를 버전 키로 연결해 현재 ordinal로 비교하고 회귀 테스트를 추가했다.

### 남은 범위와 제한

- 실제 두 raw 스냅샷 전체, EC2 분산 실행, 운영 MinIO 버전, 실제 크기의 자원·성능은 이번에 검증하지 않았다.
- DB 적재, 수집기 실행, 스케줄러 연결, 배포는 수행하지 않았다.
- 첫 full **전체 bundle 완료**가 v2의 선행 조건이다. 예전 package/version만 있는 상태를 자동 승격하지 않는다.
- v2는 이전 날짜→새 날짜 흐름이다. 같은 날짜를 새 코드로 교체하거나, 다른 미완료 run의
  native pointer를 자동 폐기하는 기능은 포함하지 않는다. 같은 코드·입력·work-dir의 재개만 검증했다.
- `ready_for_load=false`, 운영 `ready_for_publication=false`. 로컬 fixture의 Curated 게시 성공과 구분한다.

실행법 및 정책 정본: [orchestration README](../../../pipeline/orchestration/README.md),
[인수 계약](../../../pipeline/orchestration/CONTRACT.md).
