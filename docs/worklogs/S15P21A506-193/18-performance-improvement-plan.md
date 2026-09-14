# 18. 전체 날짜 count 계산의 성능 개선 계획

작성일: 2026-09-11. 상태: **계획 작성, 최적화 구현 미착수**.

## 목표와 범위

선정 target의 모든 적격 버전·229개 날짜에 대해, 전체 적격 source 버전이 참조하는
`dependents_count`와 품질 정보를 기존과 동일하게 계산하면서 반복 변환·검사·정렬을 줄인다.
이번 요청의 종료점은 개선 계획과 검증 기준의 보고다. 아래 구현·성능 목표는 아직 수행하거나
달성한 결과가 아니다. 전체 선정 계산, 서버 실행, DB 쓰기, commit/push는 시작하지 않는다.

보존할 기준은 [D-22](06-decisions.md)와 [기존 표본 계약](16-historical-production-code.md)이다.

- target은 다운로드 선정 목록의 고유 이름 99,996개, source는 해당 target을 참조하는 전체 적격 패키지·버전이다.
- 일반 `dependencies`, NULL 배포일 제외, 기존 stable 후보·semver 정책을 유지한다.
- 동일 source 패키지·버전→target 패키지·버전은 같은 날짜에 한 번만 센다.
- 미해석과 extraction error/unknown을 품질에 보존한다. PARTIAL과 `ready_for_load=false`를 유지한다.
- sparse 양수 count와 target population을 유지한다. 속도를 위해 source를 표본으로 자르거나 0을 정상값으로 게시하지 않는다.
- 기존 H1/H5-A/H4 생성 코드와 완료 산출물의 지문을 보존한다. 개선 코드는 production 계층에 둔다.

## 확인한 기준값과 남은 불확실성

| 관측 | 값과 의미 | 근거 |
| --- | --- | --- |
| `lodash` 1개, 모든 source·229일 | 후보 113개, lookup 949개, 선언 3,262,021개. 준비 53.640초 + 계산/저장 39.750초 + 별도 검증 16.891초, 총 110.312초 | [실행 영수증](../../../data/vd-eta-lodash-111350.json) |
| 위 실행의 내부 구간 | 원본 지문 확인 26.416초, 추출 25.025초, 준비 파일 쓰기 1.753초. 해석 0.362초, 집계 9.266초, cache 마무리 5.093초, 날짜 저장 24.723초 | [입력 로그](../../../data/vd-eta-input-111350/progress.jsonl), [실행 로그](../../../data/vd-eta-run-111350/progress.jsonl). phase 간격이며 소계 밖 준비 비용이 있다 |
| 큰 후보의 요청 구성 | `@octopusdeploy/type-utils` 후보 33,966개 전체 + 고유 lookup 총 33,908개 중 59개 표본. batch 23/23/13, 후보 포함 JSON 구성 119회·177,009,827 bytes. 구성 1.762초(프로파일 실행), 별도 측정 2.113초. Node 요청/응답 확인 1.056초, 전송 4,462,822 bytes | 직전 진단 턴의 메모리 내 측정. 기존 [59개 표본](16-historical-production-code.md)과 같은 선택 규칙. 패키지 전체 요구조건의 완료 시간으로 취급하지 않음 |
| 집계 중간 행 | lodash 선언 3,262,021개→구간 join 8,480,513행. 그중 유효하지 않은 기간 208,035행(약 2.45%) | 직전 읽기 전용 join 집계. 빈 기간 제거만으로 큰 개선이 난다고 주장하지 않음 |
| 품질 변화 기록 | lodash `source_deltas` 11,523,373행 중 `delta=0` 5,010,453행(약 43.5%) | [파티션 출력](../../../data/vd-eta-run-111350/partitions/018). 직전 읽기 전용 집계 |
| 전체 선정 workload | 후보 7,822,819개, 고유 lookup 4,220,751개, 선언 239,556,025개 | [H5-A profile](../../../data/version-dependents/historical-profiles/observed=2026-08-31/run_id=profile-20260910T203912020724Z-unlimited/profile)과 pinned download selection의 이름 join. H5-A에 없는 선정 이름도 실행 scope에서 보존 |

위 시간에는 이미 완료한 H1/H5-A를 다시 만드는 비용이나 DB 적재가 포함되지 않는다.
공통 입력 읽기와 날짜별 출력은 패키지마다 독립 실행하는 비용이 아니므로 110초에 패키지 수를 곱하지 않는다.
전체에서 어느 단계가 가장 오래 걸리는지는 아직 미측정이다. 패키지별 Parquet 조회가 실제로
얼마나 스캔하는지도 실행 계획·row-group 통계를 확인하기 전에는 단정하지 않는다.

## 실행 순서

### O-0. 비교 기준 고정

1. 현재 production 코드, 입력/선정 CSV/런타임 지문과 기존 정답 결과를 고정한다.
   입력 adapter의 생성 계약이 바뀌면 같은 원본·같은 target으로 새 prepared 입력을 만든다.
   기존 prepared manifest의 코드 SHA를 고쳐 재사용하지 않는다. 전후 비교는 같은 의미의 입력/결과를 기준으로 한다.
2. 측정기를 생산 코드와 분리한다. 입력 검증·추출, 요청 구성, Node 대기, SQL 집계,
   품질/cache 생성, 날짜 출력, 독립 검증을 각각 잰다. SQL 중간 행 수, JSON 변환 횟수/bytes,
   Python+Node 메모리, 임시 디스크 최대치도 기록한다.
3. 기존 6-target 표본, 모든 source를 포함하는 lodash 표본, 큰 후보 59-lookup 보조 측정을 재사용한다.
   작은 합성 기준 구현으로 아래 단계의 경계 사례를 먼저 잠근다.
4. 가벼운 동일 kernel 비교는 baseline/개선 순서를 바꿔 3회 측정하고 중간값을 비교한다.
   전처리 전체를 불필요하게 3회 반복하지 않는다. 단일 실행 결과와 OS 캐시 영향은 따로 표시한다.

수정 예정: production 전용 benchmark 모듈과 테스트/측정 기록.
기존 기준: [benchmark](../../../pipeline/version_dependents/historical_production_benchmark.py),
[production 테스트](../../../pipeline/version_dependents/test_historical_production.py),
[SQL 테스트](../../../pipeline/version_dependents/test_historical_production_sql.py).

### O-1. 후보 JSON을 요구조건마다 다시 만들지 않기

현재 [batches()](../../../pipeline/version_dependents/historical_production.py) 87–123행은
요구조건을 추가할 때 메시지 전체를 직렬화해 크기를 검사한다. 먼저 이 부분만 바꾼다.

- 패키지의 고정 후보 목록·고정 필드 bytes는 한 번 계산하고, 요구조건 JSON bytes를 더해
  요청 크기를 산정한다. 실제로 보낼 batch가 확정될 때 전체 메시지를 구성한다.
- UTF-8, 따옴표/역슬래시 escape, 쉼표/괄호, null의 길이를 정확히 계산한다. 기존 요청/응답
  frame 한도, 비교 횟수 한도, 최악 응답 구간 한도는 그대로 적용한다.
- 기존 Node 요청 형식과 semver worker는 유지한다. 후보를 Node에 상주시킬 새 프로토콜은
  이 단계에 섞지 않는다. 남는 전송 경로의 중복 직렬화는 별도 측정 후 production 전용 경로에서 판단한다.

완료 기준: 기존과 요청 값·해석 결과가 일치하고, **요청 크기 산정 단계**의 후보 전체 직렬화는
패키지당 상수 횟수로 제한한다. 실제 전송 경로에는 batch 수에 따른 직렬화·후보 재검증 비용이
남으므로 횟수와 시간을 별도로 측정한다.
59-lookup 표본의 **요청 구성 시간 70% 이상 감소를 성능 목표**로 둔다. 전체 전처리 70% 개선을 뜻하지 않는다.
한도 직전/직후, 긴 원문, Unicode/escape/null, 빈 lookup, 후보가 많은 패키지의 회귀 테스트를 통과해야 한다.
수정 예정: `historical_production.py`, `test_historical_production.py`와 전용 benchmark.

### O-2. 전역 검사를 한 번 수행하고 패키지별 파일 조회를 묶기

[전체 target 검사](../../../pipeline/version_dependents/historical_production_sql.py) 111–124행은
현재 partition마다 반복된다. [패키지별 조회](../../../pipeline/version_dependents/historical_production.py)
131–145행은 후보와 lookup에 각각 하나의 쿼리를 실행한다.

- 원본 prepared target의 스키마·범위·전역 `(package_id, version)` 중복·partition 배치를
  계산 시작 전에 한 번 검사한다. 검사 결과를 동일 실행·동일 입력 지문 안에서만 재사용한다.
- partition에서 새로 생성되는 lookup interval의 연속성/상태/target 존재·birth 검사는 매번 유지한다.
  partition 선언 key 중복·누락 lookup·출력 범위 검사도 유지한다. 아직 생성되지 않은 interval을
  시작 시 전역 검사했다는 방식으로 대체하지 않는다.
- 후보와 lookup 조회에 partition 경계를 적용하고, partition 안에서 이름 순 cursor 두 개를
  병합 순회한다. 후보는 현재 패키지 한 개만 메모리에 올린다. 조회·정렬은 패키지당 두 번에서
  partition당 두 스트림으로 줄이되 정렬의 임시 디스크 비용을 함께 측정한다.
- 후보만 있는 이름, lookup만 있는 이름, 둘 다 없는 선정 이름을 target 목록 기준으로 보존한다.
  잘못된 partition 연결은 필터로 숨기지 않고 오류로 처리한다.
- 실행 종료 전 입력 파일 SHA/크기를 다시 확인한다. 재개·독립 검증에서는 새 실행의 전역 검사를 수행한다.

완료 기준: partition 1/4/128 변경 시 전역 target 중복 검사 횟수가 증가하지 않고,
결과/품질은 동일하다. 입력 변조 및 다른 partition의 target 연결을 거부한다.
`EXPLAIN ANALYZE`의 스캔 행/row-group과 조회 횟수·wall time을 기록하며, 현재와 다른 파일 정렬로
만든 벤치를 실제 전체 prepared 파일의 실측으로 표시하지 않는다.
수정 예정: `historical_production_input.py`, `historical_production.py`, `historical_production_sql.py`, 해당 테스트.

### O-3. 원본 source 품질을 보존하면서 중간 행 줄이기

[구간 join·변화량 집계](../../../pipeline/version_dependents/historical_production_sql.py) 129–214행,
[source 품질 마무리](../../../pipeline/version_dependents/historical_production_sql.py) 268–341행이 대상이다.

- `p_sources`를 구간 확장 전의 해당 partition 원본 declarations에서 만든다. 원본 선언 수,
  source birth, extraction error/unknown을 보존한다.
- interval은 `max(source_birth, interval_start) < interval_end`인 기간만 집계용으로 확장한다.
  lookup 누락/구간 coverage 검사는 필터 전에 수행한다. 실제 사용하지 않는 target LEFT JOIN도 제거 후보로 검증한다.
- source/status/target별 변화량은 먼저 정확한 key로 합산한 후 합계가 0인 행만 제외한다.
  target 변화량은 기존 source→target 중복 구간 합집합을 계산한 뒤 만든다.
- source 상태를 시작하는 birth anchor는 유지한다. 종료점 `n`의 실제 음수 변화량과
  기간 닫힘 검사도 유지한다. 미해석만 있는 source가 사라지지 않아야 한다.
- 전역 품질 마무리도 partition 간 같은 source/version의 변화량을 합친 뒤 net-zero를 정리한다.

완료 기준: lodash `source_deltas`의 0 변화량 5,010,453행이 제거되고 비영 변화량 6,512,920행은 유지된다.
날짜별 count·lookup 상태·품질은 이전과 전부 일치한다. 내부 interval 분할 모양은 달라질 수 있으므로
중간 Parquet SHA 동일성을 강요하지 않는다. source 중복/여러 target/같은 날짜 교체/끝점/미해석/
error/unknown/참조 없는 target 및 partition 간 source 중복을 검증한다. SQL 시간과 peak 메모리를 비교한다.
수정 예정: `historical_production_sql.py`, `test_historical_production_sql.py`.

### O-4. 날짜별 검증에서 동일 전체 데이터를 반복 합산하지 않기

현재 [cache 검증](../../../pipeline/version_dependents/historical_cache.py) 194–234행은 날짜마다
target 수와 count 합계를 다시 조회한다. [날짜별 expected 계산](../../../pipeline/version_dependents/historical_artifact.py)
114–152행도 같은 합계를 구한다. 기존 [production writer](../../../pipeline/version_dependents/historical_production_writer.py)는
이미 fresh 날짜의 이중 전수 검증을 제거했으므로, 그 개선을 다시 성과로 세지 않는다.

- target은 birth별 수의 누적합, count는 구간 시작/종료의 증감 누적합으로 229일의 검증용
  합계를 한 번 계산한다. quality JSON의 상태·보존식·상세 상태 수 검사는 그대로 수행한다.
- 날짜별 실제 count 행을 쓰는 작업은 남는다. 결과 파일의 스키마/key/실제 값 전수 검증과
  게시 직전 SHA/크기 재확인을 유지한다. 품질 요약을 재사용했다고 실제 출력 검증을 생략하지 않는다.
- 같은 실행의 동일 cache에 대한 계산형 검증을 재사용하되 종료 시 입력 cache 파일 SHA/크기를
  다시 확인한다. 코드/plan 지문만 확인하는 것으로 입력 내용 검사를 대체하지 않는다.
- 최초 `verify_cache()` 안에도 날짜별 반복이 있으므로 writer 바깥 호출만 줄여서는 충분하지 않다.
  기존 H4 파일은 그대로 두고 필요 시 `historical_production_cache.py`에 빠른 검증 경로를 둔다.
  기존 검증의 항목별 대응표와 정상/손상 입력에 대한 신구 검증기의 결과 일치를 먼저 확인한다.
- 새 helper와 writer를 production generation contract에 포함한다. 이전 산출물 manifest의 코드
  지문을 수정하지 않으며 새 run/cache를 만든다. 재개·독립 검증은 새 실행에서 입력과 출력을 다시 검증한다.

완료 기준: quality 합계를 만들기 위한 대형 테이블 조회가 날짜 수에 비례해 반복되지 않고,
229일 합계·상태·출력 값이 동일하다. cache 중도 변조/검사 직후 출력 변조/누락 파일/재개 변조를
거부한다. 파일별 SHA는 실행 이력 변경으로 달라질 수 있어 lineage의 지문 필드와 실제 count/품질 값을 구분한다.
수정 예정: production writer/runner, 필요 시 새 production cache helper, 대응 테스트.

### O-5. 대표 표본으로 전체 처리량 추정 후 보고

- 앞 단계는 하나씩 적용해 성능 차이를 분리한다. 병렬로 benchmark를 실행해 자원 경쟁을 만들지 않는다.
- 기존 6개와 lodash 정답 대조 후, workload로 선정한 8→16→32개 target의 모든 후보·모든
  source 선언·229일을 처리한다. 일반 규모, 큰 후보, 많은 lookup, 많은 참조, 버전 교체가 잦은 경우,
  후보 없음/참조 없음/미해석 사례를 포함하고 표본 목록·선정 규칙을 기록한다.
- 큰 후보 59-lookup kernel은 요청 구성의 보조 측정으로만 쓴다. 해당 패키지 전체 완료나
  대표 end-to-end 시간으로 취급하지 않는다. 무거운 패키지가 표본에서 빠지면 별도 strata로 남긴다.
- 전체 입력 연결 비용, 패키지/lookup 처리, 확장된 유효 구간, source 품질 사건 수, 최종 출력 행/bytes에
  따른 비용을 나눠 추정한다. 표본 수만 곱하지 않으며 정렬 spill·왜곡된 package 분포·전역 merge의
  비선형 비용은 추정 범위와 미측정 항목에 표시한다. 일부 표본을 추정식 검사용으로 남긴다.
- 결과 보고에는 단계별 전후 시간, 결과 차이, CPU/메모리/임시 디스크, 전체 10만개에 대한 추정 근거와
  범위를 포함한다. 근거가 부족하면 추가로 필요한 한정 측정을 특정하고 숫자를 임의로 확정하지 않는다.

실행 경계: 입력 준비와 계산 모두 승인된 작은 scope를 유지한다. 현재 sample 32개 상한을 우회해
전체 준비/계산을 실행하지 않는다. 장시간 전체 실행은 후속 범위이며 전체 elapsed time으로 강제 종료하는
1시간 제한을 다시 넣지 않는다. 향후 독립 계산이 시작되면 모델의 상시 폴링 없이 로그·완료 기록을 남긴다.

## 검증과 중단 기준

| 대상 | 통과 기준 |
| --- | --- |
| 의미 | 기존 독립 기준과 모든 날짜·target/version count 차이 0, 품질/lookup 상태 차이 0 |
| 보존 | source/target/정책 scope 및 기존 완료 입력 지문 유지. 원본 선언 식별자와 미해석 source 보존 |
| 성능 | O-1 요청 구성 70% 감소 목표. O-2 전역 검사 횟수·조회 구조 개선, O-3 zero-delta 제거, O-4 합계 조회 반복 제거를 각각 측정 |
| 전체 표본 | 각 변경의 작은 회귀 검증 후 마지막에 해당 모듈 전체 회귀 테스트 1회. 기존 209개 테스트는 이전 기준이며 새 통과 결과로 재인용하지 않음 |
| 산출물/재개 | 새 코드 지문으로 새 run, 재개는 동일 지문만 허용. 입력/출력 변조 거부와 중간 실패 후 재개 결과 일치 |
| 자원 | 기본 4 threads/4GB DuckDB·Node 별도 메모리·기존 디스크 보호를 기준으로 기록. 메모리 상한을 올려 개선 효과를 가장하지 않음 |

값 불일치, 경계 검사 누락, 기존 생성 코드 지문 훼손이면 해당 단계를 중단하고 원인을 해결한다.
성능 목표 미달이면 측정 결과로 설계를 조정한다. 빠르다는 이유로 불일치 결과를 채택하지 않는다.
미실행 검증은 미실행으로 기록한다.

## 후속 경계: 병렬화와 DB 직전 시간

먼저 위 반복 비용을 줄인 뒤 남는 CPU·읽기·정렬 비용으로 partition 병렬화의 필요성을 판단한다.
두 EC2는 각각 4 vCPU·약 15GiB·swap 0B이며 실제 처리량은 미측정이다. 서버별 target partition
분담 또는 Spark 이식은 이 계획에서 구현하지 않는다. 어느 쪽도 기존 속도에 단순히 2배를 적용하지 않는다.

이번 최적화의 측정 끝점은 **검증된 count/품질 파일 준비**다. 사용자가 원하는 DB 적재 직전까지의
최종 전처리 시간에는 후속 H6의 **0 보완·기존 DB key 연결·적재용 행 준비**도 포함해야 한다.
이 단계가 아직 구현/측정되지 않았다는 점을 전체 ETA에서 분리한다. 1,007,084,608개 selected
target/version/date 유효 key는 dense 출력 규모이며 현재 sparse count 행 수와 같지 않다.

## 이번 요청에서 실제 수행한 일

- 앞선 진단의 실측과 현재 코드의 반복 경계를 계획에 연결했다.
- SQL 경계·source 품질 보존과 writer/cache 신뢰 범위를 독립 검토해 반영했다.
- 계획 독립 검토에서 표본 59개와 전체 lookup 33,908개의 범위를 더 명시하고, O-1의 직렬화
  감소 기준을 요청 크기 산정 단계로 한정했다. batch별 전송 비용까지 제거됐다고 주장하지 않는다.
- 계획과 안내 문서만 작성했다. O-0~O-5 구현·새 성능 개선·전체 계산·DB 적재는 수행하지 않았다.
