# 43. 패키지·버전별 전체 날짜 조회 측정

## 요청·범위·계획

전체 날짜별 적재 완료 후 패키지·버전별 모든 날짜의 dependents_count 조회 시간을 측정한다.
대상은 완료된 private 날짜별 테이블이며 public 서비스 전환이나 백엔드 쿼리 변경은 하지 않는다.

- 기존 전체 적재 결과: 229일/1,007,084,608행, 9,028.416초(2시간 30분 28초).
- 유명 패키지 8개와 선정 목록에서 고정 난수 대신 이름 SHA 순서로 선정한 8개를 표본으로 삼는다.
- 각 패키지의 최신 날짜에 존재하는 버전 문자열 정렬의 처음/중간/마지막을 선택한다. semver 순서나 배포 시각 순서로 표현하지 않는다.
- 조회는 `package_id = ? AND version = ? AND snapshot_at BETWEEN ? AND ? ORDER BY snapshot_at`이며 버전 간 SUM을 하지 않는다.
- 최초 실행과 반복 실행을 구분하되 DB/OS 캐시를 비우거나 DB를 재시작하지 않는다. 최초 실행은 콜드 캐시 검증이 아니다.
- EXPLAIN ANALYZE/BUFFERS/TIMING OFF/JSON에서 계획 시간·실행 시간·파티션 인덱스 접근과 root의 buffer 수를 기록한다. 부모/자식 buffer를 더해 중복 계상하지 않는다.
- 일반 SELECT 결과 수신 시간은 Python→지속 psql/Docker 연결→응답 수신 경과 시간이다. 실제 API/HTTP 성능과 구분한다.
- 각 표본의 반복 반환값 일치·날짜 중복 없음·정렬을 검사한다. 대표 표본은 PREPARE generic plan 재사용도 별도로 비교한다.
- 세션 읽기 전용 및 쿼리 제한 30초. 전체 데이터 쓰기·VACUUM·인덱스 변경·동시 부하 테스트는 범위 밖이다.

공식 기준: [EXPLAIN](https://www.postgresql.org/docs/16/using-explain.html), [PREPARE](https://www.postgresql.org/docs/16/sql-prepare.html).

## 결과

2026-09-13 02:45:58~02:46:08 KST, 로컬 PostgreSQL 16.14의 완료된 날짜별 대상에서 측정했다.
private 완료 receipt 229일/1,007,084,608행과 저장된 계획/클러스터 실체/현재 코드 지문을 확인했다.
추가 10억 행 전수 COUNT나 원본 재집계는 하지 않았으며 앞선 적재기의 최종 검증 결과를 사용했다.

표본은 16패키지/48버전이며 버전별 실제 반환은 1~229행(중앙값209)이었다.
그중 **229개 날짜가 모두 있는 19개 버전**만 분리한 결과는 다음과 같다.

| 측정 | 횟수 | 중앙값 | 표본 p95(최근접 순위) | 최댓값 |
| --- | ---: | ---: | ---: | ---: |
| 각 버전의 최초 DB 계획+실행 | 19 | 105.605ms | 316.327ms | 316.327ms |
| 반복 DB 계획+실행 | 57 | 13.274ms | 15.577ms | 16.458ms |
| 반복 일반 SELECT 결과 수신 | 57 | 15.482ms | 18.987ms | 26.626ms |

전체 48개 버전 기준 최초 DB 중앙값41.104ms/p95 146.345ms, 반복 DB 중앙값13.269ms/p95 15.399ms였다.
일반 SELECT 수신 중앙값15.458ms/p95 18.697ms. 반환 날짜가 짧은 새 버전을 포함하므로 위 229일 표본과 구분한다.
표본 p95는 관측값의 분포이며 서비스 사용자 p95나 신뢰구간이 아니다.

## 실행 계획과 비용

- 모든 48개 최초 계획이 229개 날짜 relation을 실제 Index Scan했다(총10,992개). Seq Scan은 없었다.
- 인덱스는 기존 `(package_id, version, snapshot_at)` PK이며 count를 포함한 인덱스나 추가 최적화는 적용하지 않았다.
- 144회 반복 EXPLAIN의 DB 계획 중앙값7.991ms, 실행 중앙값5.211ms였다. 229개 파티션을 처리하기 위한 계획 비용이 무시할 수준은 아니지만, 이 조건의 반복 단건 조회 총시간은 약13ms였다.
- 최초 root Shared Read Blocks 중앙값178.5/최대907, 반복144회는 모두0이었다. Shared Read는 PostgreSQL shared buffer 밖에서 읽었다는 뜻이며 OS 캐시가 있을 수 있으므로 물리 디스크 읽기나 cold-cache로 단정하지 않는다.
- 가장 느린 최초 조회는 express@0.14.0: 계획132.730ms+실행183.597ms=316.327ms. 이 실험의 첫 전체 조회라 계획 메타데이터 초기화와 캐시 영향이 섞여 있다.
- 대표 express@0.14.0에만 force_generic_plan PREPARE를 별도로 적용했다. 생성 후 반복10회 DB 총시간 중앙값6.649ms, 범위6.021~6.974ms. 실제 JDBC 자동 plan 선택·연결 풀에서는 재현을 확인해야 하며 이미 적용된 서비스 개선으로 표현하지 않는다.

## 정확성·환경·한계

- 각 버전의 일반 SELECT 3회 반환값 일치, 날짜 중복 없음/정렬, 229행 상한, 음수 count 없음, EXPLAIN 반환 행 수 일치 확인.
- prepared 결과도 동일 버전의 일반 SELECT 값과 일치했다. 이는 조회 결과의 반복 일관성 검사이며 원본 관계부터 재계산한 정확성 검증은 아니다.
- PostgreSQL shared_buffers=2GB, work_mem=4MB, block_size=8192, jit=on, max_parallel_workers_per_gather=2. 세션 default_transaction_read_only=on, statement_timeout=30s, 기존 PgLoader lock_timeout=10s.
- DB와 OS 캐시를 비우지 않았고 별도 VACUUM/ANALYZE도 실행하지 않았다. 적재 직후 상태와 다른 표본 조회의 캐시 영향이 존재한다.
- 단일 지속 psql 연결의 순차 측정이다. 일반 SELECT 시간에는 psql/Docker 연결을 통한 명령·결과 전달과 완료 marker 수신이 포함된다. 연결 생성·HTTP·인증·패키지 이름→ID 조회·동시 요청 비용은 포함하지 않는다.
- 패키지 ID를 알고 조회하는 목표 SQL을 측정했다. 기존 백엔드의 버전 간 SUM 쿼리나 public 테이블의 응답 시간을 측정한 것이 아니다.
- 사전순 버전 표본이며 모든 패키지·조회 분포·EC2·cold-cache·동시 부하를 대표하지 않는다. 반복에 의한 캐시 효과가 크므로 첫 요청 성능도 별도 판단해야 한다.

판단: 이 로컬 단건 측정에서는 날짜별 구조를 즉시 바꿔야 할 정도의 반복 조회 지연은 발견하지 못했다.
날짜별 적재의 장점을 유지한 채 실제 API의 패키지·버전 쿼리와 연결 풀/동시 요청 조건을 다음 검증 대상으로 삼을 수 있다.
측정 단계에서는 서비스 전환·backend 변경·추가 인덱스를 적용하지 않았다.

## 결과 파일과 재현

- [측정 요약과 48개 버전별 지표](evidence/db-history-query-results.json)
- [express@0.14.0의 실제 229일 반환값](evidence/db-history-query-example.json)
- 전체 원본 결과: `data/vd-db-query-probe-20260913-01/result.json`, 최초3개 실행 계획과 prepared 계획은 같은 폴더 `plan-*.json`.
- 실행기: `pipeline/version_dependents/historical_db_query_probe.py`.

```powershell
$env:PYTHONPATH="$PWD;$PWD\.venv-bq\Lib\site-packages"
& C:/Users/SSAFY/miniforge3/python.exe -m pipeline.version_dependents.historical_db_query_probe --config data/vd-db-reload-timed-20260912-2354/config.json --output data/new-query-probe
```

출력 폴더는 새 경로여야 하며 쿼리는 읽기 전용이다. 재실행의 최초 조회는 이번 조회가 채운 캐시의 영향을 받는다.
