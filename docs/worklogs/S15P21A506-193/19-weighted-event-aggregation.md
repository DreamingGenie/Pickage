# 19. 가중치 이벤트 집계와 source 품질 요약

상태: A0~A3 구현·실제 표본 대조·전체 회귀 검증 완료.

## 변경 범위와 작업 계획

사용자가 승인한 [알고리즘 계획](../../../.omx/plans/dependents-algorithm-20260911.md)의 A0~A3을 구현한다. 선정 target에 대한 모든 적격 source 버전, 원본 선언 품질, 날짜별 distinct count, 기존 stable/미해석 정책을 보존한다.

1. 기존 production 코드·입력과 정답 결과를 기준으로 고정한다.
2. 단일 lookup source-target 쌍의 birth 가중치와 다중 lookup fallback을 분리하고, 같은 날짜의 source 추가·winner 변경을 한 번 적용한다.
3. 원본 declaration 상태는 별도 가중치로 계산하고 source 상태는 전역 min/max/never 요약으로 계산한다.
4. production v2 partition receipt·재개·검증 연결을 구현한다. v1 기본 경로와 H1/H5-A/H4 생성 코드는 유지한다.
5. 작은 fixture와 실제 표본에서 기존 결과·품질을 대조하고 시간·중간 행·메모리/임시파일을 측정해 보고한다.

범위 밖: 세그먼트 트리 resolver(A5), 조회/JSON 개선(A4), cache/writer 최적화(A6), 전체 선정 계산·입력 재생성, 서버/Spark/DB/Jira, commit/push. ready_for_load=false를 유지한다.

## 검증 기준

- 작은 날짜별 원본 source identity oracle 및 기존 SQL과 모든 count/품질 값 일치.
- fast/fallback 집합 보존, 전역 target name/id 일대일성, raw duplicate 품질 보존, 같은 날짜 교체, source의 여러 partition 소속, 오류/unknown/미해석/빈 입력.
- 기존 최종 count 상한·target birth·구간 닫힘 검사, v1/v2 혼합 및 변조 거부, v2 중단 후 재개.
- 동일 실제 작은 입력에서 단계별 전후 시간을 비교한다. histogram 항목 수 감소를 속도 개선 배수로 표시하지 않는다.
- 실제 전수 계산·DB 적재 직전 행 준비 시간으로 확대 해석하지 않는다.

## 이슈와 해결 및 실제 결과

### 구현한 동작

`historical_production_events.py`는 같은 source 버전이 같은 target 이름에 요구하는 조건이 하나이면
`(lookup_id, birth_index)`별 source 수로 묶는다. 원본 선언 수는 별도 가중치로 보존한다.
조건이 여러 개이면 그 source/target 쌍 전체를 기존 구간 합집합 방식으로 계산해 중복 참조를 제거한다.
서로 다른 target 버전으로 해석되는 경우에는 각 버전에서 한 번씩 센다.

가중치를 묶은 뒤 source가 추가되는 날짜와 선택 버전이 바뀌는 날짜를 함께 처리한다.
예를 들어 기존 source 1,000개와 신규 30개가 있는 날 선택 버전이 바뀌면 이전 버전에서 1,000을
빼고 새 버전에 1,030을 더한다. 같은 조건을 참조하는 source마다 버전 교체 구간을 만들지 않는다.
정렬된 입력은 나누어 읽고, count 사건은 lookup을 가로지르는 최대 8,192행 버퍼로 기록한다.

`historical_production_quality.py`는 source별 원본 선언 수·끝까지 미해석인 수·최초/마지막 해석 시점을
한 행으로 보존하고 파티션을 합친 뒤 source 상태를 정한다. 원본 declaration의 상세 상태별 수는
별도의 가중치 사건으로 계산한다. 중복 선언은 품질에 남으며, 선택 버전만 바뀔 때 source 품질용
사건을 반복해서 생성하지 않는다. 오류/unknown 우선순위와 PARTIAL 정책은 같다.

준비 입력 전체의 target 이름/ID 일대일성 및 declaration→lookup 연결을 계산 전에 검사한다.
`RESOLVED`였다가 미해석으로 돌아가는 입력은 새 방식의 전제에 맞지 않아 실패시킨다.
final count 상한 2,147,483,647, target 배포 이전 양수 금지, 구간 닫힘 검사를 유지한다.

runner의 새 옵션은 `--algorithm weighted-events-v2`다. 기본값 `interval-sql-v1`은 유지한다.
새 run format은 `historical-production-run-v2`이며 파티션에는 `lookup_intervals`, `counts`,
`source_summary`, `status_deltas` Parquet를 저장한다. 새 모듈 지문과 알고리즘이 실행 계약에
포함되므로 기존 v1 run을 v2로 재개하거나 이전 manifest의 코드 지문을 수정해 재사용하지 않는다.
최종 H4의 count 구간·target population·quality 스키마는 유지한다.

### 같은 실제 입력의 3회 비교

`historical_weighted_benchmark.py`로 기존 SAMPLE run의 검증된 lookup 구간을 읽었다.
알고리즘마다 새 프로세스와 작업 DB를 사용하고 실행 순서를 교대했으며, 동시에 계산하지 않았다.
두 방식 모두 DuckDB 4 threads/4GB/임시 디스크 상한 40GB다. 아래 시간은 3회 중간값이다.

측정 범위는 **파티션 집계 + 전역 source/선언 품질 계산**이다. 새 방식의 전역 입력 의미 검사도
포함한다. 입력 파일 지문 확인 시간은 따로 기록했다. 입력 준비·npm 해석·중간 Parquet 저장·
H4 날짜별 파일 저장·독립 검증·DB 적재 시간은 이 합계에 포함하지 않는다.

| 실제 표본 | 기존 방식 | 가중치 방식 | 판단 |
| --- | ---: | ---: | --- |
| lodash 전체 source, 229일 | 11.652초 | 4.831초 | 58.54% 감소, 약 2.41배 |
| 기존 6개 target, 229일 | 0.501초 | 1.043초 | 약 0.542초 증가, 작은 입력에는 적용 이점 없음 |

두 표본 모두 모든 날짜의 `(package_id, version, count)`와 품질 JSON 전체 필드,
target population을 양방향 `EXCEPT ALL`로 비교했고 **차이 0건**이다.
중간값의 단계별 내역은 각 단계를 독립적으로 집계하므로 그 합이 전체 시간의 중간값과 다를 수 있다.

| lodash 처리량·자원 | 기존 방식 | 가중치 방식 |
| --- | ---: | ---: |
| 원본 선언 | 3,262,021개 | 동일 |
| 선언×lookup 구간 중간 행 | 8,480,513행 | fast 경로에서 생성하지 않음 |
| source 가중치 묶음 | 해당 없음 | 11,602행 |
| count 증감 사건 | 기존 SQL 경로 | 13,442행, INSERT 2회 |
| source 품질 중간 데이터 | delta 11,523,373행 | 요약 3,262,021행 |
| 최종 count 구간 | 2,309행 | 2,309행 |
| 프로세스 peak RSS 중간값 | 3,903.7 MiB | 1,177.8 MiB |
| 표본 중간/대조 Parquet 합계 중간값 | 71,319,048 bytes | 19,632,051 bytes |

메모리는 입력 지문 확인을 포함한 독립 Python/DuckDB 프로세스의 OS 최고 RSS다.
이 비교는 저장된 해석 구간을 쓰므로 Node를 실행하지 않는다. 임시 디스크 최고 사용량과
Python+Node가 함께 실행되는 전체 경로의 합산 peak는 이번에 측정하지 않았다.
위 Parquet 크기는 benchmark의 중간·대조 파일 합계이며 DB 크기나 날짜별 최종 파일 크기가 아니다.

lodash의 fallback은 0개였다. 따라서 이 실측은 같은 요구조건을 많이 재사용하는 입력에 대한
개선 증거이며, 다중 조건 source가 많은 전체 선정 입력의 성능을 대표하지 않는다.
작은 6개 target은 추가 집계·검사 비용 때문에 느려져 새 방식을 기본값으로 전환하지 않았다.
패키지별 자동 선택 기준도 아직 구현하지 않았다.

### 실제 저장·독립 정확성 확인

같은 6개 target의 전체 source 12,630개 선언·lookup 50개·후보 49,936개를 사용해
새 v2 production run에서 229일 파일을 저장했다.

| 확인 | 결과 |
| --- | --- |
| 준비된 입력→해석→집계→229일 저장 | COMPLETE, 29.797초 |
| 파티션→cache→날짜별 파일 별도 전수 검증 | 통과, 13.949초 |
| 매 날짜 기존 npm 해석기로 재계산한 DISTINCT source 정답 대조 | 229일, count/lookup 차이 0건, 29.562초 |
| 완료 상태 | SAMPLE, PARTIAL, ready_for_load=false |

이전 실제 run과 새 run의 cache도 전수 대조했다. count 구간 402행·quality 229행·
target population 49,936행 모두 같은 값이며 행 중복 수까지 일치한다.

29.797초에는 입력 준비와 위 두 별도 검증 시간이 포함되지 않는다. 이전 동일 표본의
25.781초 실행은 다른 시점의 참고값이며 통제된 전체 경로 반복 측정은 아니다.
lodash의 4.831초를 패키지 한 개의 DB 적재 직전 전처리 시간으로 해석하지 않는다.

결과 위치는 `data/vd-weighted-six-0911`, 독립 정답 보고서는
`data/vd-weighted-six-0911-oracle/report.json`이다. 입력은 기존
`data/version-dependents/historical-production-inputs/sample-20260911-v2`를 그대로 읽었다.
lodash 입력도 기존 `data/vd-eta-input-111350`의 전체 source를 보존했다.

### 실패·수정과 검증 경계

- 초기 구현에서 TEMP 테이블 재사용과 reader 수명, lookup마다 출력 INSERT하는 문제가 발견됐다.
  같은 연결의 파티션 재계산을 지원하고 별도 reader와 공유 8,192행 버퍼를 사용하도록 수정했다.
- 누락 lookup이나 원문 spec 불일치가 INNER JOIN에서 빠지는 경우를 막기 위해 LEFT JOIN과
  NULL-safe 원문 비교를 추가했다. 전역 매핑 오류는 resolver가 실행되기 전에 거부한다.
- 벤치마크 최초 실행은 DuckDB COPY의 쿼리/파일명 위치 매개변수 충돌로 실패했다.
  검증된 정수 calendar 길이를 쿼리에 넣고 파일명만 매개변수로 전달해 재실행했다.
  실패 폴더 `data/vd-wbench-six-0911-a`와 로그는 보존했다.
- 새 테스트 20개에서 같은 날 1,000→1,030 교체, 중복 원문 품질 보존, 같은 winner 중복 제거,
  다른 winner 버전별 count, PARTIAL, 파티션을 걸친 source 상태, 비단조 상태 거부,
  1,000 lookup의 날짜별 직접 source identity 대조, int32 상한, 재개·변조 거부를 확인했다.
- 독립 코드 재검토에서 앞선 BLOCK 항목의 수정이 확인됐으며 A0~A3 정확성 blocker 없음으로 승인됐다.
- 변경 전 코드 41개 중 runner를 제외한 40개 SHA가 같다. H4 generation도 같다.
  새 파일 포함 Python 46개의 AST 검사와 전체 회귀 **229개 테스트(100.673초)**를 통과했다.

실제 표본에는 fallback이 드물어 대규모 다중 조건 입력의 속도는 미측정이다. 추가 최적화
A4(조회/직렬화), A5(버전 검색 알고리즘), A6(cache/날짜별 저장 검증)는 구현하지 않았다.
전체 99,996개 선정 이름의 입력 준비·계산, EC2/Spark 실측, H6/DB 적재, commit/push는 미실행이다.

### 증거와 재현

- [lodash 3회 성능·전체 값 대조](evidence/weighted-events-lodash-comparison.json)
- [6개 target 3회 성능·전체 값 대조](evidence/weighted-events-six-comparison.json)
- [v2 실제 실행](evidence/weighted-events-sample-run.json), [별도 파일 검사·독립 날짜별 정답 대조](evidence/weighted-events-sample-check.json)
- [기존/새 실제 cache 전체 값 대조](evidence/weighted-events-real-cache-comparison.json)
- [코드 지문·AST·측정 범위](evidence/weighted-events-code-check.json), [회귀 로그](evidence/weighted-events-tests.log)

가중치 실행은 새 출력 폴더로만 시작한다. 아래 명령은 이미 준비된 제한된 표본에 대한 예시다.

```powershell
python -B -m pipeline.version_dependents.historical_production run `
  --prepared-dir data/version-dependents/historical-production-inputs/sample-20260911-v2 `
  --manifest-sha256 00d3fabed0ca2b031436de5d5b60e86f12b273d2d520a3210723a19a963336e8 `
  --output data/vd-weighted-six-new-run --algorithm weighted-events-v2
```
