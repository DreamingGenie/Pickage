# 37. 날짜별 일괄 적재 결과의 연결·중단/재개 검증

## 범위와 계획

2026-09-12 사용자 승인으로 36번의 빠른 일괄 키 생성/검증 경로를 날짜 partition으로 연결하는 실험을 진행한다.
기존 43일/106,346,692행, 서비스 DDL, 원래 적재 코드·계약은 보존한다. 전체 적재나 실제 테이블 이름 전환은 수행하지 않는다.

1. 새 UUID 실험 schema에 기존 날짜를 나타내는 일반 테이블과 같은 컬럼/PK/FK의 partition parent를 만든다.
2. 기존 날짜 테이블의 OID/물리 파일/값을 유지한 채 legacy 범위로 연결한다. 작은 fixture이므로 실제 1억 행 전환 비용을 측정한 것으로 보지 않는다.
3. 하루치 LOGGED 테이블 COPY → 날짜 CHECK/PK/FK 생성·검증 → 값 대조 → ATTACH와 실험 전용 게시 이력을 같은 transaction으로 COMMIT한다.
4. 연결 직전/직후 rollback, COMMIT 후 응답 유실 재개, 다른 입력/변조/중복/범위/잘못된 FK 차단을 검사한다. 참조 삭제/수정 검사는 별도 fixture 참조 테이블에서만 수행한다.
5. 실제 참조 테이블과 2023-03-06 전체 2,827,680행으로 일괄 준비+연결+전수 검증 시간을 측정한다. 기존 prepared 입력을 재사용하고 생성 계약을 보존한다.
6. parent/child 제약 연결, 실행 통계와 attach 시간, 날짜 partition pruning을 증거로 기록한다. 기존 43일 실제 대규모 전환과 API 부하 검증은 별도 미실행 범위로 남긴다.

완료 기준: 실험 데이터만 변경, 원본과 값 동일, FK 유효, transaction 실패 시 날짜 노출/게시 이력 모두 0, 재개 중 재삽입 0, 준비 테이블 변조 차단, 실험 schema 정리와 원래 적재 재개 검사 통과.

## 실제 결과

### 구현과 초기 검사

새 모듈 `pipeline/version_dependents/historical_db_partition_probe.py`에 실험용 publisher와 자체 fixture를 추가했다. 서비스 ETL 테이블을 수정하지 않으며 실험 전용 journal에 입력/코드 지문·날짜·child OID·행 수·품질을 기록한다. 원래 43일 적재 코드와 계약은 그대로다.

초기 검사에서 부모의 CHECK 제약과 자식의 자동 생성 이름이 달라 연결이 거부되는 문제, PostgreSQL OID가 JSON 문자열로 전달되는 비교 문제를 발견해 수정했다. 모든 테이블에 명시적 공통 CHECK 이름을 사용하고 catalog OID를 bigint로 읽는다.

작은 fixture에서 준비 중단, 연결 후 rollback, 게시 기록 후 COMMIT 직전 rollback, 다른 세션에서 미완료 데이터/게시 이력 비노출, prepared 값 변조 차단, 다른 입력 거부, 새 세션 재개 시 재삽입 0, COMMIT 응답 유실 재개를 검사했다. parent/child 직접 잘못된 FK·중복·음수·NULL·int32 초과 쓰기, 날짜 범위 위반, 참조 테이블 삭제/수정, partition 범위 중복도 거부됨을 확인했다. 실제 public 참조 데이터에는 쓰지 않았다.

### 연결 시 재검사 여부의 근거

- [PostgreSQL 16 ATTACH 문서](https://www.postgresql.org/docs/16/sql-altertable.html#SQL-ALTERTABLE-DESC-ATTACH-PARTITION): 대응하는 인덱스와 날짜 범위를 증명하는 유효 CHECK가 있으면 불필요한 생성/범위 스캔을 피한다.
- [16.14 고정 소스 tablecmds.c](https://github.com/postgres/postgres/blob/0d1c00c624fa7367d4a895f44381887757289682/src/backend/commands/tablecmds.c#L9952): 참조 대상·컬럼/연산자·match/action/deferrability가 같고 이미 검증된 독립 FK를 재사용한다. 맞지 않으면 FK 생성과 데이터 검증이 다시 발생할 수 있다.
- 실제 실험은 child FK OID 보존과 conparentid 연결, PK index OID/물리 파일 보존과 parent index 연결을 확인한다. ATTACH 직전/직후 같은 transaction의 `pg_stat_xact_user_tables` 읽기 카운터도 비교한다. 이는 해당 연결 작업의 관측이며 모든 향후 DDL 조합에서 무스캔을 보장하지 않는다.
- 연결은 parent에 SHARE UPDATE EXCLUSIVE, child에 ACCESS EXCLUSIVE가 필요하고 참조 version/snapshot에도 쓰기와 충돌하는 잠금을 잡을 수 있다. 준비·검증이 빠르다는 것이 모든 동시 쓰기에 무중단이라는 뜻은 아니다.

### 첫 하루 전체 측정

`data/vd-db-partition-full-20260912-01`: 실제 2,827,680행과 public 참조 테이블을 사용해 42.328초에 완료했다. 날짜 입력 TSV는 앞서 만든 검증 파일을 재사용했다. 따라서 Parquet부터 TSV를 새로 만드는 시간은 이 수치에 포함되지 않는다. 포함 구간은 입력 SHA/크기/행 수 확인, 실험 source/legacy 준비, COPY·PK/FK 생성, 연결과 게시, 새 세션 재개·값 검증·정리다.

COPY 3.984초, PK 생성 0.516초, FK 생성/검증 23.281초. 별도 날짜 준비 총 28.312초, 게시 총 1.328초. 값 전수 비교 일치, FK/PK 재사용과 ATTACH 중 읽기 증가 0 확인. legacy는 실제 기존 데이터 중 1,000행만 복사해 물리 파일·OID·값 보존을 시험했다. 실제 106,346,692행 전환을 시험한 것이 아니다.

첫 연결 시간은 Windows GetTickCount64 기반 타이머의 15.625ms 해상도 아래여서 0초로 기록됐다. 무비용이라는 뜻이 아니다. QueryPerformanceCounter 기반 perf_counter로 변경해 후속 실험에서 재측정한다. 앞선 보고서를 새 코드 지문으로 덮어쓰지 않는다.

### 최종 정밀 측정과 검토

정밀 타이머 적용 뒤 full-02는 총 35.155초, ATTACH 4.062ms였다. 검토 결과 격리 실험의 차단 결함은 없었으며, 다음 증거/입력 경계를 보강했다.

- 입력 metadata는 호출자가 별도로 고정한 SHA-256과 먼저 비교하고 내부 manifest SHA도 검사한다. metadata와 payload를 함께 교체해도 DB 연결 전에 거부한다. 실제 서비스에 연결할 때는 기존 H6/H7의 전체 세대·달력·이름 매핑 검증도 연결해야 한다.
- ATTACH 전후 읽기 카운터 차이를 계산해 모든 항목이 0인지 명시적으로 검사한다.
- legacy 표본은 package_id/version/date 순서로 고정하고 날짜 조회 계획의 실제 Relation Name 집합이 day_counts만 포함하는지 검사한다.

최종 코드 `f1211e96…`의 fixture-06/full-03 모두 완료. [최종 fixture 결과](evidence/db-partition-final-fixture-results.json), [최종 실제 하루 결과](evidence/db-partition-final-results.json). 이전 지문/결과는 그대로 보존했다.

| 최종 실제 하루 단계 | 소요 시간 |
| --- | ---: |
| COPY | 3.707초 |
| PK 생성 | 0.555초 |
| FK 생성·전체 검증 | 8.597초 |
| 준비값 전수 대조 | 0.576초 |
| 날짜 준비 전체 | 13.452초 |
| 연결 자체 | 0.003327초 (약 3.3ms) |
| 값 재검사·연결·외부 관찰·게시 COMMIT | 1.255초 |
| 입력 확인·실험 준비·위 작업·재개 확인·최종 검증·정리 전체 | 23.033초 |

준비 전체와 게시 전체는 각각 그 안의 세부 단계를 포함하므로 표의 모든 행을 더하지 않는다. 게시 시간에는 별도 세션에서 미완료 데이터가 보이지 않는지 확인하는 실험 비용도 포함한다.

최종 입력: 2,827,680행, 0값 2,047,195행, dependents_count 합계 109,238,213. 공개 참조 테이블은 실제 DB 데이터를 사용했다. 관측된 3회 전체시간은 약 42/35/23초로 편차가 있다. 타이머와 입력 검증/표본 선택의 보강도 있었으며 캐시를 강제로 초기화하지 않았으므로 엄밀한 동일조건 3회 성능 평균이나 남은 186일 ETA로 해석하지 않는다.

완료 검증:

- 최종 fixture의 11개 검증 그룹 통과. 별도 입력 변경 거부 2개 + 기존 namespace/COPY/입력 테스트 7개, 총 9개 unittest 통과(0.553초).
- parent를 통한 날짜별 전수 값 일치, 기존 legacy 표본 OID·물리 파일·값 보존.
- 두 FK의 OID/parent 연결과 validated 상태 유지. PK index OID·물리 파일·parent index 연결 유지.
- ATTACH 중 day_counts/version/snapshot 읽기 카운터 증가량 전부 0. 날짜 조회 계획은 해당 day_counts만 읽음.
- 실험 schema/세션 0개, 원래 43일 게시 이력/입력·코드 계약 검사 통과. 실제 서비스 전체 적재 재개 없음.

### 적용 전에 남은 범위

이번 완료 범위는 **격리 환경의 날짜 연결/원자성/재개 실험**이다. 기존 106,346,692행 테이블 자체를 이름 변경하거나 partition으로 전환하지 않았다. 성능 결과는 미리 준비한 TSV에서 시작하며 전체 source 준비·실제 43일 전환/재검증 비용은 제외한다.

실제 적용에는 새 publisher의 기존 ETL execution/attempt/current·세대 검증 연결, 원래 테이블의 권한/OID 의존성/이름 전환·되돌리기·전체 값 보존 검증, 실제 API 조회와 통계 갱신(ANALYZE), 잔여 날짜별 성능/전환 비용 산정이 남아 있다. 기존 서비스 제약 제거와 실제 전환/전체 재개를 이 실험 결과만으로 수행하지 않았다.

재현:

```powershell
$env:PYTHONPATH="$PWD;$PWD\.venv-bq\Lib\site-packages"
& C:/Users/SSAFY/miniforge3/python.exe -m pipeline.version_dependents.historical_db_partition_probe --output data/new-partition-fixture
& C:/Users/SSAFY/miniforge3/python.exe -m pipeline.version_dependents.historical_db_partition_probe --output data/new-partition-full --input-dir data/vd-db-bench-input-20260912-01 --expected-metadata-sha256 69272bd6581ebf5f6c3b2f3ae2e3f49bc65dbb62ab074d0f0a3637777a7137c2
```

출력 폴더는 새 경로여야 하며 기존 결과를 덮어쓰지 않는다. 이 명령은 실험 schema만 생성/정리하며 서비스 전체 적재는 시작하지 않는다.
