# 17. 날짜별 저장의 중복 검증 제거

## 범위와 계획

2026-09-11 사용자가 속도 개선 진행을 요청했다. 먼저 확인된 날짜별 중복 검증을 제거하고
같은 실제 6개 target·229일 표본으로 정확성과 시간을 비교한다. 전체 선정 패키지 계산,
DB 적재, commit/push, 후보 worker 프로토콜 변경, 병렬화는 이번 변경 범위에 포함하지 않는다.

기존 H4 writer는 날짜 파일 저장 중 전수 검증을 완료한 직후, 완료 목록을 구성하기 위해
같은 날짜 파일을 다시 전수 검증한다. 새로 쓴 날짜는 전수 검증 결과를 재사용하고 완료 표시
직전에 파일 SHA·크기만 다시 확인한다. 이전 실행에서 저장한 날짜의 재개 및 독립 검증에서는
기존 전수 검사를 유지한다.

H5-A의 생성 코드 계약이 기존 H4 파일도 고정하므로 기존 파일을 변경하지 않는다. 새 production
writer에 저장/재개 제어 루프를 두고 기존 H4 쓰기·검증 함수를 재사용한다. 새 daily plan과
production run 계약에 새 writer의 SHA를 포함하며 기존 완료 결과의 코드 SHA를 바꾸지 않는다.

1. 기존 동작과 중복 호출 횟수, 재개·변조·게시 순서의 회귀 테스트를 먼저 준비한다.
2. 새 writer를 연결하고 새 날짜만 중복 읽기를 생략한다. 파일 자체의 최초 전수 검증은 유지한다.
3. 동일 고정 cache의 기존/개선 writer를 새 경로에서 실행하여 저장 시간과 결과를 비교한다.
4. 동일 준비 입력으로 전체 production 경로의 표본을 새 run에 계산하고, 독립 검증 및
   이전 229일 결과와 count/품질을 비교한다. 실제 결과와 테스트를 기록하고 종료한다.

## 실제 결과

**중복 검증 제거와 같은 실제 입력의 비교를 완료했다.**

| 측정 | 결과 |
| --- | ---: |
| 같은 고정 cache, 기존 writer의 229일 저장 | 29.297초 |
| 같은 고정 cache, 개선 writer의 229일 저장 | 23.078초 |
| 저장 시간 감소 | 21.23% (약 1.27배) |
| 새 production 표본 실행 전체 | 25.781초 |
| 새 production 결과 별도 전수 검증 | 12.187초 |
| 변경 전/후 count Parquet 파일 SHA 일치 | 229개 모두 |
| quality/lineage 값 일치 (실행 plan SHA 제외) | 458개 모두 |
| 전체 회귀 테스트 | 209개 통과, 76.063초 |

동일 cache에서 기존·개선 writer를 각각 한 번 새 디렉터리에 실행한 비교다. 여러 번 측정한
통계적 결론이나 전체 선정 패키지의 성능 향상률은 아니다. 새 production 실행은 동일 준비
표본(6개 target, 후보 49,936개, 선언 12,630개, 229일)을 사용했고 입력 준비를 다시 수행하지
않았다. 이전 실행 전체 33.219초와 새 실행 25.781초는 별도 시점 측정 참고값이다.

새 결과의 count 구간·target population·quality cache 3개 Parquet도 이전 독립 검증 완료
결과와 SHA가 일치한다. 새 run의 파티션→cache→229일 파일은 별도 `verify_run`으로 다시
검증했고 통과했다. 계산 로직은 변경하지 않았으므로 기존 날짜별 semver 재계산을 반복하는 대신
기존 독립 정답과의 바이트 동일성 및 새 저장 파일 전수 대조를 사용한다.

초기 구현 검토에서 최초 전수 검증 직후 파일이 변하는 경우를 추가로 시험했다. 완료 표시
직전 SHA·크기 재확인을 넣어 해당 경우에도 완료로 게시하지 않도록 보완했다. 3일 합성 예제의
전수 값 검증 호출은 기존 6회→3회다. 기존 날짜 재개, 변조, 새 writer 코드 지문 불일치,
기존 출력과의 값 일치도 테스트했다. Python AST 40개 확인, 기존 생성 코드 30개 보존.

새 모듈은 `historical_production_writer.py`이며 production runner의 저장/검증 연결만 바꿨다.
기존 H4/H5-A 및 준비 입력의 코드·manifest는 변경하지 않았다. 새 writer 코드 지문을 새
daily plan과 production run에 기록하므로 이전 run을 새 코드로 덮어 재개하지 않는다.

[같은 cache 성능·값 비교](evidence/historical-write-optimization-comparison.json),
[회귀 검증](evidence/historical-write-optimization-validation.json),
[테스트 로그](evidence/historical-write-optimization-tests.log),
[새 표본 실행](evidence/historical-write-optimization-run.json),
[새 결과 전수 검증](evidence/historical-write-optimization-run-verification.json).

## 추가로 확인한 운영 환경

사용자가 제공한 두 EC2는 각각 4 vCPU·약 15GiB 메모리·309G root 파일시스템·swap 0B다.
로컬 읽기 전용 확인에서 PC는 Core Ultra 9 185H, 16코어·22논리 CPU·물리 메모리
68,186,861,568 bytes(약 63.5GiB)다. 현재 DuckDB 설정은 4스레드·4GB다.

Spark의 driver는 여러 노드의 executor에 작업을 분배하므로 두 EC2 분산 실행은 가능한
운영 후보다. 하지만 두 서버의 메모리를 단일 작업이 통째로 쓰는 것은 아니며, 논리 CPU
개수나 서버 개수만으로 로컬보다 빠르다고 판단할 수 없다. 같은 서버 환경·대표 입력으로
실제 처리 시간, 메모리, 임시 디스크, 데이터 전송량을 비교해야 한다.
[Spark cluster 개요](https://spark.apache.org/docs/latest/cluster-overview.html),
[Spark partition·shuffle 설명](https://spark.apache.org/docs/latest/rdd-programming-guide.html#shuffle-operations).

서버의 디스크 IOPS/처리량·네트워크·동시 서비스 부하는 아직 측정하지 않았다. SSH 접속,
Spark 이식·서버 실행·배포는 수행하지 않았다. [제공된 사양과 로컬 관측](evidence/historical-server-comparison-context.json).
