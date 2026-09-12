# 34. 전체 DB 적재 중단 지점과 재개 준비

## 사용자 요청

2026-09-12 사용자가 현재 진행 상황과 성능 문제를 기록하고, 완료된 부분을 보존한 채 적재를 중단하도록 지시했다.
자동 재시작이나 성능 개선 코드는 이번 작업에 포함하지 않는다.

## 중단 결과 — 2026-09-12 12:57:19 KST

| 항목 | 확인 결과 |
|---|---|
| 누적 실행 시간 | 약 3시간 35분 56초 |
| 완료 날짜 | 43 / 229개 |
| 마지막 완료 날짜 | 2023-02-27 |
| 완료된 게시 이력의 행 수 합계 | 106,346,692 / 1,007,084,608행 |
| 중단한 날짜 | 2023-03-06 |
| 남은 범위 | 186개 날짜, 900,737,916행 |
| 적재 Python / 자식 Docker 프로세스 | 종료 확인 |
| 해당 PostgreSQL backend 29905 | 종료 확인 |
| 중단 날짜의 보이는 서비스 행 | 0행 — EXISTS 검사로 확인 |
| 기존 완료 날짜 이력 | 중단 전후 manifest/contract/count/status 유지 확인 |

해당 backend의 시작 시각·DB·삽입 SQL을 확인한 후 `pg_cancel_backend`로 실행 중인 쿼리를 취소했다.
psql 연결 종료로 미완료 날짜의 트랜잭션이 rollback되고, 기존 오류 처리기가 execution/attempt를 FAILED로 기록했다.
Python launcher도 예외 처리 후 종료했으며 절전 방지 요청은 해제됐다. 사용자나 다른 작업의 DB 세션은 종료하지 않았다.
실행 폴더의 상태는 사용자 요청임을 구분하여 PAUSED_BY_USER로 표시했다. DB의 FAILED와 취소 원문 로그는 보존했다.

## 확인된 성능 문제

1. 날짜마다 약 270만~280만 행을 처리하던 시점에 날짜별 DB 단계가 약 6분 15초~6분 35초 걸렸다.
2. 실행 중인 `INSERT INTO ... SELECT ...`에서 DataFileRead/Write 대기를 관측했다.
3. 취소 시점 PostgreSQL CONTEXT는 `public.version`의 package_id/version을 `FOR KEY SHARE`로 확인하는 SQL이었다.
   실제 외래키 검사가 진행 중이었음을 확인했지만, 전체 시간 중 외래키·기본키·디스크가 차지한 비율은 측정하지 않았다.
4. PK 순서가 `(package_id, version, snapshot_at)`이고 날짜 전용 인덱스는 없다.
   날짜 조건의 EXPLAIN은 Parallel Seq Scan이었다. 날짜별 기존 행 검사·값 비교·행 수 확인이 누적 테이블을 다시 읽는 비용을 만든다.
5. 날짜는 순차 실행된다. 현재 적재는 임시 테이블 COPY 후 실제 테이블 INSERT이며 PK/FK가 유지된 상태다.
6. 관측 시 컨테이너 메모리 한도는 16GiB, shared_buffers는 2GB였다. PK_VERSION 약 2.1GB,
   대상 PK 약 4.3GB, version 본문 약 18GB였다. 메모리 설정만으로 개선될 비율은 미확인이다.

단순히 작업자 수를 늘리면 디스크 경쟁이 커질 수 있다. 전체 적재는 멈췄으므로 이제 격리 테스트 DB에서
날짜 조회/중복 검증/일괄 적재 방식의 정확성과 성능을 비교할 수 있다. PK/FK 제거·DDL 변경·코드 교체는 아직 하지 않았다.

## 재개 자료

실행 폴더: `data/vd-db-full-20260912-01`

- `pause-before.json`: 취소 직전 44개 execution과 당시 프로세스/단계.
- `pause-checkpoint.json`: 43개 완료 날짜의 execution/manifest/contract/count, 미완료 날짜 목록, 원본 SHA와 원래 실행 계획.
- `code-at-pause/`: 당시 적재 관련 코드 6개와 launcher의 참고 사본. 현재 코드를 덮어쓰는 용도로 사용하지 않는다.
- `check_resume.py`: 원본 SHA/적재 코드/실행 계획/기존 완료 이력을 읽기 전용으로 확인한다.
- `resume.ps1`: 검사를 통과하면 기존 launcher를 숨김 백그라운드 실행한다. `-CheckOnly`는 재시작하지 않는다.
- 기존 `load/attempt-*/YYYY-MM-DD.json`과 모든 계산 Parquet를 보존했다.

현재 코드 그대로 재개할 때:

```powershell
# 검사만: 이번에 실행하여 통과했으며, 실제 재시작은 하지 않았다.
& .\data\vd-db-full-20260912-01\resume.ps1 -CheckOnly

# 실제 재개: 향후 사용자가 재개를 요청했을 때 실행한다.
& .\data\vd-db-full-20260912-01\resume.ps1
```

재개는 완료된 43일을 새로 INSERT하지 않는다. 다만 기존 loader 정책에 따라 원본/DB 값을 재검증하므로
완료 구간 재검증 시간이 발생한다. 첫 미완료 날짜인 2023-03-06부터 실제 삽입을 다시 시작한다.
중단 날짜는 부분 행부터 이어가지 않고 그 날짜 전체를 재처리한다.

성능 개선으로 코드가 달라지면 이 재개 검사는 의도적으로 차단한다. 기존 계약에 새 해시를 덮어씌우지 말고,
이 체크포인트를 기준으로 완료 이력과 개선된 적재 방식의 호환성을 검증한 별도 재개 경로를 준비해야 한다.
이 자료는 그 작업에 필요한 완료 날짜·원본·실행 신원을 보존한 것이다.

## 검증과 미실행

- 중단된 backend/launcher/자식 프로세스 종료, 기존 완료 이력 유지, 미완료 날짜 0행 확인.
- `resume.ps1 -CheckOnly`: RESUME_CHECK_PASSED, load_started=false.
- 서비스 테이블/PK/FK/DB 설정 변경, 계산 재실행, 실제 재개, commit/push 없음.
- rollback 행은 조회되지 않지만 물리적 공간 회수는 별도 PostgreSQL 관리 작업이다. 정리 목적으로 DELETE/VACUUM FULL을 실행하지 않았다.
