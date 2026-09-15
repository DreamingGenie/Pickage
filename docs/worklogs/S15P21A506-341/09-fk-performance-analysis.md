# FK 검사 병목과 개선 시간 추정

이 문서는 개선 실행 전 분석이다. 아래 시간은 당시 가정이며, 이후 재개 실측은 약 3시간 17분이었다. [최종 결과](12-final-result.md)의 실측 및 비교 한계를 우선한다.

## 범위

2026-09-14 사용자 요청으로 개선 방법과 소요 시간을 분석했다. 현재 전체 복원은 중단/변경하지 않았다. 전체 후보에서 카탈로그 조회와 EXPLAIN만 실행했다. 별도 기존 벤치마크 DB에서는 읽기 전용 검사 SQL을 2회 실측했다. 서버 설정/데이터/스키마는 변경하지 않았다.

## 확인한 상태

- PostgreSQL 16.15. 검사 대상 PVS 1,007,084,608행, 날짜 파티션 229개. 참조 version 정확한 원본 receipt는 54,188,349행.
- version 힙 19,771,490,304바이트, PK 인덱스 1,712,709,632바이트. PK는 유효하지만 version의 키 컬럼 pg_stats는 없고 relallvisible=0이다. 양쪽 version 컬럼 타입/콜레이션은 같다.
- 현재 내부 RI SQL을 재구성한 EXPLAIN은 양쪽 Seq Scan+Sort의 Merge Anti Join이다. 실행 중 내부 plan 자체를 추출한 증거와 구분한다.
- 병렬 설정/메모리를 EXPLAIN 연결에서만 바꿔 비교했다. Hash 강제/메모리512MB만으로 참조 힙 반복 읽기는 없어지지 않았다. Index Only Scan 경로 자체는 존재하지만 현재는 heap visibility 확인 비용이 높다. planner cost는 시간이 아니므로 cost 배수를 속도 향상률로 쓰지 않는다.

## 개선 계획 (아직 미적용)

1. 종료 전 완료 인덱스/FK/파티션 연결과 정의를 저장하고, 미완료 TOC 항목만 실행하는 재개 경로를 준비한다. 입력 데이터/완료 항목을 유지한다.
2. 기존 복원 coordinator/worker를 조율해 중단한다. 현재 ADD FK는 중간 재개가 불가능하므로 이후 처음부터 재실행한다.
3. 남은 PK/인덱스를 우선 생성하고 필요한 파티션 인덱스를 부모에 연결한다. 충돌하는 FK 작업과 겹치지 않는다.
4. version과 PVS 자식의 VACUUM/ANALYZE로 visibility map과 키 통계를 준비한다. vacuum full이나 테이블 재적재는 필요하지 않다. 같은 FK가 실행 중이면 잠금이 충돌하므로 먼저 끝내야 한다.
5. 실제 전체 후보의 대표 날짜 EXPLAIN 및 제한된 검사를 통해 정렬 제거/인덱스 경로/heap fetches를 확인한다. 확인 전 추정 시간을 실측으로 표현하지 않는다.
6. 부모 FK를 실행하고 나머지 FK/Flyway/ANALYZE/구조 검증을 수행한다. 서비스 전환과 원본 전수 값 비교 유예 경계는 유지한다.

## 표본 실측

기존 pickage_import_341_server_pilot_a208a899eb4d에서 2026-08-31 leaf 검사 SELECT만 실행했다. 표본 version은 allvisible=relpages이며 해당 leaf와 version PK를 이용한 Merge Anti Join이다.

- 실제 읽은 입력: leaf 250,000행 + version 인덱스 915,417행. 표본 version 전체 1,200,987행이 모두 읽힌 것은 아니므로 계산에는 actual rows를 사용했다.
- 첫 측정 1.049526초, 반복 0.313127초. 첫 측정을 OS 캐시까지 비운 cold run이라고 부르지 않는다.
- version Heap Fetches=0, leaf Heap Fetches=250,000. 임시 파일 읽기/쓰기=0.
- 작은 표본이며 인덱스가 캐시에 들어간다. 전체 데이터에서 동일한 성능이 보장되지 않는다.

## 계산과 한계

정렬 경로 O(sum(N_i log N_i) + P*M log M)에서, 정렬된 인덱스로 대조하는 경로가 확인되면 O(N + P*M)로 정렬 항을 없앨 수 있다. 여전히 날짜별 참조 인덱스 반복 접근은 남는다.

- 전체 입력 방문량 모델: N + 229*M = 13,416,216,529.
- 표본 처리량 환산: 1,165,417행 / 1.049526~0.313127초.
- 현재 FK의 개선 후 단순 환산: 약 1.0~3.36시간. 전체 데이터 재실행 검증 전 가설이다.
- 참조 측 읽기 구조는 4.53TB 힙 반복에서 약392GB PK 반복으로 감소할 여지가 있다(약11.5배). 이것은 물리 IO나 전체 속도11.5배를 보장하지 않는다.
- 재개 후 전체 계획: PK/인덱스1~3시간, vacuum/통계15~45분, 현재 FK1~3.5시간, 나머지 FK/Flyway/마무리1~2시간을 가정하면 약3.25~9.25시간. 계획 범위는 반올림하여4~10시간. PK/마무리 시간은 전체 개선 실측이 없는 낮은 신뢰도의 가정이다. 재개 코드 준비 시간은 제외한다.

증거는 data/service-data-migration/341/server-full-20260914-01/fk-improvement-estimate.json, fk-index-only-sample.json, fk-plan-alternatives.json에 저장했다.

공식 근거: https://www.postgresql.org/docs/16/indexes-index-only-scans.html , https://www.postgresql.org/docs/16/storage-vm.html , https://www.postgresql.org/docs/16/sql-vacuum.html , PostgreSQL REL_16_STABLE ri_triggers.c (RI 메모리 대체와 SPI 검사).
