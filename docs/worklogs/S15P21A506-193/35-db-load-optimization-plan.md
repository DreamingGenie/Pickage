# 35. DB 적재 성능 개선 조사와 실행 계획

## 결론과 현재 범위

2026-09-12 사용자 요청에 따라 조사 및 계획만 수행했다. 서비스 DB/적재 코드는 변경하지 않았으며 적재는 PAUSED_BY_USER다.
권장 순서는 **단계별 실측 → 날짜 조회·중복 검증 개선 → 동일 제약조건 아래 적재 비교 → 필요하면 날짜별 독립 적재/연결 구조 실험 → 호환 재개**다.
단순 COPY 교체나 작업자 증가만으로 몇 배 빨라진다고 가정하지 않는다.

## 고정된 조건과 관측 근거

- DB PostgreSQL 16.14, 로컬 `pickage-267-validation` / `pickage_267_full_defaulted`.
- 43일/106,346,692행 PUBLISHED, 2023-02-27까지 보존. 2023-03-06은 rollback 완료. 남은 186일/900,737,916행.
- 기준 기록: [중단과 재개](34-db-pause-and-resume.md), [기존 적재기 검증](32-full-db-loader.md).
- 실제 FK 검사 중이었다는 취소 CONTEXT, INSERT에서 DataFileRead/Write 대기, 최근 약 279만 행/6분 35초는 관측 사실이다.
  FK/PK/반복 조회 각각의 시간 비율은 아직 모른다.
- 읽기 전용 catalog 확인: 대상 PK만 존재하며 날짜 전용 인덱스 없음. `pg_stats.snapshot_at.correlation=1`, distinct 날짜 43.
  이 값은 현재 통계의 관측이며 미래에도 날짜 순서가 유지된다는 보장은 아니다.
- 저장소 V4에는 `(package_id,snapshot_at)` 인덱스가 있지만 이 로컬 DB에는 없다. 패키지별 API 조회용 인덱스와 전체 날짜 검증용 인덱스를 구분한다.
- 현재 catalog에는 대상을 참조하는 외부 FK/뷰가 없고 대상에는 내부 FK trigger만 있다. 구조 변경 전 grants/RLS/functions/ORM/마이그레이션 상태는 추가 확인한다.
- 근거 코드: `historical_db_load.py:77-110` 순차 날짜 처리, `historical_db_publish.py:130-156` staging/COPY/검증/INSERT/반복 조회,
  `historical_db_source.py:33-49,132-157` 0 복원/날짜 품질 검증.
- API 계약: `backend/.../PackageQueryRepository.java:209-215,261-272` 패키지·날짜 추이 및 버전별 분포 조회.
  V1의 PK `(package_id,version,snapshot_at)`와 버전 복합 FK/날짜 FK, 열 타입·NULL·기본값을 보존한다.

## 공식 자료로 확인한 개선 후보

| 후보 | 기대되는 변화 | 한계와 적용 조건 |
|---|---|---|
| snapshot_at BRIN | 날짜와 물리적 저장 순서가 일치하므로 해당 날짜가 없는 블록을 건너뛴다. 현재 correlation=1이 실험 근거다. | PK 대체 불가. 정확한 행은 재검사한다. 신규 범위 요약까지 포함해 비용을 측정한다. |
| snapshot_at B-tree | 날짜 equality/range를 직접 찾는다. | BRIN보다 크고 매 삽입 갱신 비용이 추가된다. 검증뿐 아니라 적재 전체 시간을 비교한다. |
| 기존 PK/FK 유지 + 직접 COPY | 기존 INSERT SELECT와 다른 bulk write 경로를 비교한다. | FK trigger와 PK 갱신은 계속 발생한다. 현재도 staging에는 COPY를 쓰므로 'COPY 도입=대폭 개선'으로 표현하지 않는다. |
| 날짜별 독립 테이블 COPY → 키 일괄 생성/검증 → partition attach | 누적 PK를 행마다 갱신하는 대신 새 날짜만 준비하고 게시한다. 큰 구조적 개선 후보다. | 기존 일반 테이블은 partition parent로 바로 바꿀 수 없다. FK 전파/검증, attach 잠금, API 영향 증명이 필요하다. |
| 메모리/작업자 조정 | 캐시 부족 또는 동시 작업 여지가 실측될 때 제한적으로 개선한다. | 디스크 병목에 무조건 병렬화하지 않는다. 공용 설정 재시작이나 한도 증가는 기본 실험에서 하지 않는다. |

공식 근거:

1. [PostgreSQL 16 bulk loading](https://www.postgresql.org/docs/16/populate.html): COPY의 bulk 경로, 기존 인덱스 증분 유지와 FK trigger 비용, 사후 일괄 키 생성/검증의 차이.
2. [BRIN](https://www.postgresql.org/docs/16/brin-intro.html): 물리적 상관관계, lossy 재검사, 신규 범위 요약 필요.
3. [Partitioning](https://www.postgresql.org/docs/16/ddl-partitioning.html): 독립 테이블 적재 후 attach, 기존 일반 테이블을 partition으로 연결 가능, partition key를 포함한 unique/PK 요건.
4. [ALTER TABLE](https://www.postgresql.org/docs/16/sql-altertable.html): NOT VALID는 이후 쓰기의 FK 검사를 끄지 않는다. 일반 테이블에 적재 후 FK를 만들고 VALIDATE하는 방식과 구별한다. PG16 partition parent FK에는 NOT VALID를 사용할 수 없다. attach 시 동일 FK가 재사용돼 검증이 사라진다고 가정하지 않는다.
5. [session_replication_role](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-SESSION-REPLICATION-ROLE): replica 모드는 FK 검사를 우회한다. 이번 기본 계획에서는 사용하지 않는다.

## P0. 비교 환경과 측정 기준 만들기

**장소:** 전체 적재가 멈춘 현재 노트북의 같은 Docker PostgreSQL 안에 새 테스트 DB. 기존 DB는 읽기만 한다.
원본 DB를 TEMPLATE로 복제하려고 사람의 접속을 끊지 않는다. 필요한 테이블을 읽어 새 DB에 구성하고 준비 시간을 별도로 기록한다.

- 작은 정확성 fixture: 0/양수, 신규 버전, 잘못된 FK, 중복, 최대 int32, 관측 시각, PARTIAL을 포함한다.
- 성능 입력: 첫 미완료 2023-03-06과 최신 2026-08-31의 실제 전체 날짜. 최신은 7,822,819행이다.
- 먼저 약 10만 행 smoke로 실험 장치의 오류를 찾고, 여기서 전체 소요시간을 추정하지 않는다.
- 실제 규모 비교에서는 `version` 참조 테이블의 행 수·행 폭·PK 크기와 메모리 한도를 기존 DB에 맞춘다.
  단순 3행 FK fixture나 package_id/version 두 열만 있는 축소 테이블로 FK 성능을 대표시키지 않는다.
- 날짜 인덱스 비교에는 기존 43일 규모의 누적 대상도 복제한다. 축소 데이터만 쓰면 결과를 예비 결과로 표시하고 실제 규모 결론을 보류한다.
- PostgreSQL은 DB 사이 FK를 지원하지 않으므로 테스트 DB의 참조 테이블을 별도로 준비한다. 운영 DB 테이블에 테스트 INSERT를 하지 않는다.
- 순차 비교, 동일 입력·DB 설정·인덱스 상태. 작은 후보 탈락 후 최종 후보를 A/B/B/A 순서로 최소 2회 비교한다.
  OS cache를 강제로 비우지 않고 순서·cache 영향과 편차를 기록한다.

측정 구간: 파일 준비 / 입력 hash / staging COPY / staging 인덱스·검증 / 실제 삽입 / FK·PK 관련 진단 / 최종 값 비교 / COMMIT / 총 경과.
수집: rows/s, DB 크기 증가, 인덱스 크기, WAL 차이, shared/temp block I/O, 프로세스 메모리, lock wait.
벤치마크 DB에서만 EXPLAIN ANALYZE/BUFFERS/WAL 등 진단을 실행한다. 상세 타이머 오버헤드가 있는 실행은 속도 비교와 분리한다.
시스템 전체 WAL·I/O 카운터는 다른 세션 영향을 구분하며, 누적값을 이번 실행의 비용으로 단정하지 않는다.

**완료 기준:** 각 후보가 같은 입력을 사용했음을 SHA로 확인하고, 단계별 시간과 정확성 결과를 별도 JSON으로 남긴다.

## P1. 기존 테이블을 유지하는 개선

1. `snapshot_at` BRIN 기본 범위와 B-tree를 따로 비교한다. BRIN은 날짜 게시 전 새 범위를 요약하는 비용과 유지 전략을 포함한다.
2. 값의 missing/extra/different와 행 수·0/양수·합계를 한 비교 결과에서 집계해 같은 날짜를 여러 번 읽는 SQL을 줄인다.
   단순 count/sum만으로 값 비교를 대체하지 않는다. 삽입 전 기존 데이터 충돌 검사는 유지한다.
3. staging 검증 뒤 `INSERT SELECT`와 실제 대상 `COPY`를 비교한다. 후자는 COPY 파일을 다시 전달하는 비용도 포함한다.
4. 큰 문장 하나와 10만/50만 행 단위 문장을 비교할 수 있다. **문장 분할은 날짜 트랜잭션 안에서만** 하며 날짜 내부 COMMIT은 하지 않는다.
   FK trigger 메모리 감소는 가설이다. 문장 수 증가 및 전체 날짜 트랜잭션 비용까지 측정한다.
5. 기존 PK/FK, 원본 품질 확인과 before-COMMIT 소스 재확인은 유지한다. 변경 파일은 신규 publisher/validator 모듈 중심으로 분리한다.

**채택 기준(계획상의 목표):** 두 실제 날짜에서 결과 전체 일치, 총 처리 시간이 반복 측정 중간값 기준 30% 이상 감소하며 최대 입력에서 메모리/디스크 한도를 넘지 않을 것.
30%는 실측 결과가 아니라 적용 판단 기준이다. 충족하지 못하면 빠르다고 보고하지 않는다.

## P2. 구조적 개선 실험 — 큰 개선이 필요할 때

P1로 FK/PK 비용이 충분히 줄지 않는 경우 격리 DB에서 비교한다. 기존 서비스 FK를 끄는 실험을 기본 대안으로 삼지 않는다.

```
하루치 0 포함 결과
  → 서비스에서 보이지 않는 LOGGED 일반 테이블에 COPY
  → 같은 날짜 CHECK / 중복 없는 PK 구축 / 값 전수 비교
  → 버전·날짜 FK를 추가하고 전체 검증
  → 모든 제약이 유효한 상태인지 확인
  → 날짜 partition 연결 + ETL 게시 이력을 같은 트랜잭션으로 COMMIT
```

- 서비스에 연결하기 전 준비 테이블은 비공개 staging schema/권한 안에 둔다. 미래에 공개될 FK를 끈 기존 서비스 테이블로 넣는 방식이 아니다.
- 새로운 일반 테이블은 적재 후 FK를 추가/검증할 수 있다. NOT VALID를 적재 전에 붙여서 FK 검사가 생략된다고 해석하지 않는다.
- parent에는 기존과 동일한 PK/FK 계약을 둔다. attach 후 child/parent 제약이 VALID이고, parent/child 직접 잘못된 INSERT 및 참조 부모 삭제가 거부되는지 시험한다.
- 동일 child FK가 attach에서 재사용되는지, 다시 검사하는지, 추가 잠금/스캔이 생기는지는 PG16.14에서 증명한다. 문서만으로 무비용 attach를 약속하지 않는다.
- 날짜 CHECK의 정당성을 미리 검증해 attach 범위 확인의 중복 스캔을 줄인다. FK 검증을 대신하는 것은 아니다.
- 테이블은 LOGGED로 유지한다. 준비 단계의 실패는 해당 날짜 staging을 폐기/재생성하거나 SHA 기반 검증 후 재사용한다.
- 43일 기존 테이블은 재삽입하지 않고 새 partition parent의 legacy 범위 `<2023-03-06`로 연결하는 전환안을 검토한다.
  기존 범위 CHECK 검증은 106,346,692행을 한 번 읽는 비용이 있다. 임의의 오래된 날짜 backfill이 필요하면 별도 설계한다.
- 새 parent와 기존 테이블의 이름 교체는 OID/의존성/권한/마이그레이션에 영향을 준다. V1 수정 대신 신규 migration을 제안하고 API 조회까지 검증한다.
  43일에 대한 재삽입이 없다는 것과 전환 비용이 없다는 것은 다르다.

**구조 변경 채택 기준:** COPY+PK+FK+attach+검증+전환을 모두 포함한 남은 작업 예상 총시간이 기존 방식의 절반 이하라는 근거,
결과 전수 일치, 참조 무결성/원자성/재개 시험 통과, 주요 API 조회 회귀 10% 이내 또는 별도 검토.
이것 역시 목표이며 성능 개선을 보장한 값이 아니다. 기준을 충족하지 못하면 P1 경로를 선택한다.

## P3. 제한된 병렬화와 자원 조정

- 먼저 1 worker의 병목을 제거한다. 그 뒤 하루 파일 준비와 직전 날짜 DB 작업의 중첩, 또는 staging 2 worker만 비교한다.
- 준비된 날짜 큐는 최대 2개, 최종 게시(COMMIT/attach)는 1개로 제한한다. 같은 디스크의 random I/O 경쟁이 생기면 1개로 돌아간다.
- 4/8 worker, GPU, Spark 도입은 현재 DB FK/PK 병목의 직접 해법으로 채택하지 않는다.
- shared_buffers/컨테이너 메모리는 별도 실험 축으로 두고, DB 재시작/메모리 한도 변경 비용과 다른 작업 영향을 먼저 검토한다.
- WAL/fsync/FK trigger를 비활성화해 숫자만 빠르게 만드는 설정은 사용하지 않는다.

## P4. 완료된 43일을 보존하는 호환 재개

근거: `historical_db_load.py:47-66`은 전체 실행 계획의 코드 지문을 고정한다.
`historical_db_publish.py:44-71`은 PUBLISHED 원본 계약을 보존하며 새 검증 attempt 지문을 구분하지만,
FAILED 실행은 다른 코드 계약으로 같은 execution ID를 재사용할 수 없다.

1. `pause-checkpoint.json`과 기존 source run/입력/달력 SHA, 매핑 정책, 계산 세대를 변경하지 않는다.
2. 최적화 경로에는 새 계획/실행 폴더와 새로운 코드 계약을 부여한다. 기존 load-plan이나 생성 코드 해시를 새 값으로 덮어쓰지 않는다.
3. 43일의 원본 execution ID/manifest/count는 유지하고, 개선된 날짜 조회 방식으로 실제 DB 값의 전수 비교를 한 번 수행한다.
   row count/sum만으로 변조를 놓치거나 이력만 믿고 검사를 생략하지 않는다. 새 validation receipt는 이전 checkpoint SHA를 참조한다.
4. 나머지 186일만 실제 삽입한다. 첫 날짜는 2023-03-06 전체를 다시 처리한다.
5. 중단된 FAILED 날짜는 이전 실행 이력을 유지한 채 새 execution prefix/ID로 게시한다. 날짜별 competing input 검사를 그대로 둔다.
6. 날짜 데이터와 PUBLISHED/current 상태를 같은 트랜잭션으로 확정하고, current 날짜가 뒤로 가지 않게 한다.
7. 같은 세대의 재개 중 준비 중단/INSERT 중단/COMMIT 직전/COMMIT 후 응답 유실을 시험한다. 완료 날짜 재삽입 0, 미완료 날짜의 부분 노출 0을 확인한다.

## P5. 검증 및 재개 판단

정확성 필수 항목:
- 기준 결과와 `(package_id,version,snapshot_at,dependents_count)` 전수 동일; missing/extra/mismatch 각각 0.
- 날짜/시각, 미출시 버전 제외, 0 보존, PARTIAL 품질 유지, PK/FK 유효성.
- 다른 패키지/날짜/지표 및 43일 게시 이력 보존.
- 잘못된 FK, 중복, 음수, NULL, int32 초과, 입력/저장값 변조, 실패·재개·동시 게시 충돌 거부.
- 입력 세대 불일치 차단, 과거 계약 보존, 코드 변경 시 원래 실행으로 위장하지 않음.
- 파티션 후보라면 parent/child 직접 쓰기 및 참조 버전 삭제/갱신, 범위 중복, attach rollback을 추가 검사.

예상시간은 패키지 수나 초반 날짜 평균만으로 계산하지 않는다.
남은 날짜별 행 수, 누적 테이블 규모, 단계별 실측으로 범위를 계산하고 준비 DB 복제/인덱스/43일 재검증/전환 시간도 별도로 더한다.
작은 smoke 결과를 전체 시간으로 외삽하지 않는다. 실측 범위를 벗어난 부분은 불확실성으로 표시한다.

산출물: 신규 benchmark runner/fixture, 단계별 결과 JSON, 검증 통과한 새 publisher/호환 resume 경로,
필요하면 신규 migration 초안, 업데이트된 실행 계획과 채택/보류 근거.
실제 서비스 DDL 변경이나 전체 재개는 실험 결과와 적용 범위가 구체화된 뒤 결정한다.

## 아직 하지 않은 작업

이 문서는 조사·계획이다. 테스트 DB 생성, 성능 비교 실행, 코드 수정, 인덱스 생성, DDL/설정 변경, 전체 적재 재개, commit/push를 하지 않았다.
다음 구현 범위는 P0과 P1의 격리 실험까지이며, 결과를 본 뒤 P2의 필요성과 구조 변경 범위를 결정한다.
