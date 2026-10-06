# 12. 날짜별 집계 기준 구현과 작은 정답 데이터

## 변경 범위와 작업 계획

2026-09-10 사용자가 다음 작업 진행을 요청했다. H1의 실제 입력 모집단 준비 다음인 H2를
수행한다. 이 단계의 목표는 작은 데이터에서 매 기준일의 후보를 처음부터 다시 선택하고,
성공 관계를 source 버전별로 중복 제거하여 count를 구하는 독립 비교 기준을 만드는 것이다.

- `pipeline/version_dependents/historical_reference.py`와 전용 테스트를 추가한다.
- 기존 npm worker로 exact/범위 표현을 해석한다. alias·prerelease·프로토콜의 기존 정책과
  상태 분류를 변경하지 않는다. 고유 요구조건 구간 캐시나 delta 최적화는 이 구현에 넣지 않는다.
- 작은 fixture의 관측 시각·calendar·package/version ID·일반 선언을 검증한다. 배포일 NULL과
  T 이후 source/target을 제외하고 모든 대상 source 버전을 각각 센다.
- 날짜마다 target 후보를 다시 선정하고, source-target 쌍의 집합으로 중복을 제거한다.
  target 모집단 전체의 count(소형 비교용 0 포함), 선언/source 상태, 품질 보존식을 출력한다.
- 독립적으로 정한 정답으로 높은 버전 교체·늦은 낮은 버전·동률 원문 정렬·UTC 경계,
  반복 선언·여러 source 버전·self-edge·체인·미해석 상태 전환과 품질 우선순위를 검증한다.
- 합성 예제 결과를 JSON으로 저장하고 사용자가 읽을 수 있는 날짜별 표로 남긴다.

## 제외 범위와 완료 조건

실제 229개 날짜의 dependents_count 계산, H3 구간 최적화, DB 접속·적재, Jira, commit/push는
이번 범위 밖이다. H1의 2.63GB 입력 파일을 다시 전수 조회하지 않는다. 작은 fixture의 구조는
H1 이후 ID가 연결된 release 버전·원본 선언을 나타내며 원본 파일 검증이나 실제 데이터의
완전성을 대신하지 않는다. 버전·선언·날짜·예상 비교 횟수에 상한을 두어 전수 실행을 막는다.

완료 조건은 손계산 기대값·상태·보존식 일치, 기존 테스트 통과, 별도 검토, 합성 예제 생성과
기록이다. 소형 기준 구현의 성공을 전체 229개 실제 결과나 H3 성능 검증으로 표시하지 않는다.

## 실제 결과

H2를 완료했다. 기존 회귀 80개와 새 기준 구현 테스트 16개, **전체 96개 테스트가
30.953초에 통과**했다. Python 파일 15개의 AST 문법 검사도 통과했다. 별도 검토에서 핵심
계산의 차단 결함은 없었다. 기존 7번 resolver와 기존 8번 구현·테스트 27개 파일의 해시가
이전 단계와 같은 것을 확인했다.

### 합성 예제에서 실제 계산한 값

실제 npm 원본 전체가 아닌 **패키지 3개·버전 6개·기준일 3개의 합성 데이터**다.
각 기준 시각은 해당 날짜 12:00:00 UTC이며, 관측 시각은 2026-08-31 12:00:00 UTC다.

- `app@1.0.0`은 `dep@^1.0.0`, `dep@>=1.0.0 <2.0.0`, `util@1.0.0`을 선언한다.
- 8월 20일 배포된 `app@2.0.0`은 `dep@~1.2.0`을 선언한다.
- `dep@1.0.0`도 `util@1.0.0`을 선언한다. 나머지 버전은 일반 의존성이 없다.

| target | 8월 10일 | 8월 21일 | 8월 31일 |
| --- | ---: | ---: | ---: |
| app@1.0.0 | 0 | 0 | 0 |
| app@2.0.0 | 미배포 | 0 | 0 |
| dep@1.0.0 | 1 | 0 | 0 |
| dep@1.2.0 — 8월 15일 배포 | 미배포 | 2 | 2 |
| dep@1.1.0 — 8월 25일 배포 | 미배포 | 미배포 | 0 |
| util@1.0.0 | 2 | 2 | 2 |
| count 합계 = 고유 직접 관계 수 | 3 | 4 | 4 |
| 성공한 일반 선언 수 | 4 | 5 | 5 |
| 중복으로 제거한 성공 선언 수 | 1 | 1 | 1 |

`app@1.0.0`의 dep 선언 두 개는 같은 target을 고르므로 한 번만 센다. dep@1.2.0이
배포되면 기존 app 버전과 새 app 버전이 각각 이를 가리켜 2가 된다. 그 뒤 더 낮은
dep@1.1.0이 배포되어도 선택이 바뀌지 않는다. util의 2는 app@1.0.0과 dep@1.0.0의 직접
선언이다. app@2.0.0의 간접 경로는 더하지 않는다.

예제 계산·저장은 0.203초였다. 이 값은 소형 예제 실행 시간이며 실제 229개 날짜 계산 시간의
추정치가 아니다. 예제의 품질은 세 날짜 모두 COMPLETE지만 소형 기준 결과이므로
`ready_for_load=false`다. 기존 실제 데이터의 PARTIAL 상태를 바꾸지 않는다.

### 검증한 경계와 계약

| 검증 영역 | 실제 확인 내용 |
| --- | --- |
| 버전 표현 | exact, `^`, `~`, 비교식, OR, x-range, hyphen, `*` |
| 시간별 선택 | 더 높은 버전으로 교체, 늦은 낮은 버전 유지, 동률 원문의 `+z → +aa` 교체 |
| 시간 경계 | 정확한 UTC 시각, 배포일 NULL·미래 제외, 잘못된 날짜 순서·중복·naive timestamp·정밀도 손실 거부 |
| 집계 단위 | 동일 source 버전의 중복 제거, 여러 source 버전 별도 계산, self-edge 포함, 간접 의존 미합산 |
| 품질 | 미해석 PARTIAL, 누락·NULL 목록·추출 오류·추출 상태 미상 구분, 오류 source의 성공 관계도 보존 |
| 기존 해석 정책 | alias UNSUPPORTED, prerelease target 제외, protocol INVALID_SPEC 유지. 해당 정책의 수정 검증은 아님 |
| 상태 전환 | 알려진 패키지의 `NO_ELIGIBLE_TARGET → NO_SATISFYING_VERSION → RESOLVED`, 미매핑 이름 구분 |
| 재현·보존 | 입력 행 순서 변경 시 결과 동일, 입력/코드/결과 SHA, 기존 output 덮어쓰기 거부 |
| 실행 범위 | 버전 512·일반 선언 2,048·날짜 32·예상 비교 2,000,000 상한 및 파일 4MiB 제한 |

검토 중 H1과 달리 H2 calendar가 관측 시각보다 이전까지만 주어져도 허용된다는 점을
확인했다. 작은 비교는 일부 날짜만 골라 실행할 수 있도록 이 동작을 유지하고 회귀 테스트를
추가했다. 모든 계산 시각은 관측 이하이며, 생략 날짜의 결과는 생성하지 않는다. H1의 실제
전체 calendar 및 마지막 관측 시각 일치 계약은 그대로다.

### 결과 확인과 재현

- [예제 입력 JSON](../../../pipeline/version_dependents/fixtures/historical_reference.json)
- [날짜별 결과 JSON](../../../data/version-dependents/reference-examples/run_id=reference-20260910-v1/reference_result.json)
- [입력·코드·결과 SHA manifest](../../../data/version-dependents/reference-examples/run_id=reference-20260910-v1/reference_manifest.json)
- [명령·시각·실행 영수증](evidence/historical-reference-example.json), [저장 파일의 손계산 대조](evidence/historical-reference-example-check.json)
- [96개 테스트 요약](evidence/historical-reference-validation.json), [테스트 로그](evidence/historical-reference-tests.log), [독립 검토 기록](evidence/historical-reference-review.md)
- [실행 방법·소형 입력 계약](../../../pipeline/version_dependents/README.md)

결과 SHA256은 `53218e71cc1481db19c2847765bc31e16164712c4224ebe6a0adefc06cdeec8f`다.
저장 후 별도 프로세스에서 전체 예제 키·count·품질과 SHA를 다시 대조했다.

## 다음 작업과 아직 하지 않은 것

다음 H3에서는 요구조건의 target이 유지되는 기간을 계산하고, 같은 source-target 기간을
합친 다음 시작/종료 변화량을 누적해 날짜별 count를 구한다. 이번 기준 구현과 모든
target/date count·상태를 대조해야 한다. H3 알고리즘의 성능, 실제 229개 날짜의 count,
PARTIAL의 서비스 저장 정책과 DB 적재는 이번에 검증하거나 완료하지 않았다.
