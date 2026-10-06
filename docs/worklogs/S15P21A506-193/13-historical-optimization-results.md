# 13. 과거 날짜별 집계 최적화

## 변경 범위와 작업 계획

2026-09-10 사용자의 다음 작업 요청에 따라 H3 계산 핵심을 구현한다. H2의 날짜별 전수
재선택과 독립적으로, 고유 요구조건의 선택/미해석 상태 구간과 source 활성 기간을 교차하고
동일 source-target 기간을 합친 뒤 시작/종료 증감을 누적한다.

1. 별도 npm worker에서 후보를 최초 포함 index 순서로 추가하고 새 후보만 비교한다.
   semver 동률 원문 순서, unsupported/invalid 분류, 후보 부족 상태 전환은 기존 정책을 유지한다.
2. DuckDB에서 source-target 구간의 중첩·인접 기간을 합치고 target별 증감을 누적한다.
   count는 양수인 날짜만 출력하며 선언 상태와 source 품질은 별도로 보존한다.
3. H2와 전체 키/count/상태/품질을 비교한다. 입력 순서·파티션, nested overlap, 날짜 경계,
   여러 source 버전·중복 선언·미해석을 검증하고 소형 반복 요구조건의 처리량을 측정한다.
4. 예제와 실행 증거, 코드 검토 결과, 실제로 수행하지 않은 항목을 기록한다.

H3의 작은 fixture adapter와 계산 핵심을 검증한다. H1 전체 원본을 읽는 실행 연결, H4의
Parquet 저장·재개 기능, H5 실제 대용량 성능 측정·229일 전체 실행은 다음 단계다.
기존 H2 기준 계산기·7번 resolver·기존 8번 집계 경로는 변경하지 않는다. 새 패키지를 설치하지 않는다.

## DB 저장 결정의 현재 상태

69.7억은 모든 대상 버전과 날짜를 0까지 물리행으로 저장할 경우의 규모다. 필수 DB 행 수나
생성된 결과 수가 아니다. 결과 Parquet는 양수 count만 보존할 계획이다. DB에서 0·누락·미계산을
구분하는 조회 계약과 PARTIAL 게시 여부는 아직 미확정이며, 이번 계산 핵심 구현은 그 결정을
대신하지 않는다. DB/Jira/commit/push 및 69.7억 행 생성은 이번 범위에 없다.

## 실제 결과

H3 계산 핵심과 작은 fixture adapter를 구현했다. 새 npm worker는 후보를 birth index 순서로
추가하고 고유 요구조건별로 새 후보만 검사한다. DuckDB는 원본 선언의 상태 구간에서 동일
source-target 구간을 합쳐 증감을 누적한다. 실제 날짜별 source-target 관계 파일과 0인
target/date 행을 만들지 않는다. 소형 비교 결과에는 선언·source 구간을 남긴다.

### 변경 파일과 검증 범위

| 파일 | 역할 |
| --- | --- |
| `pipeline/version_dependents/historical_semver_worker.cjs` | 고유 요구조건의 최대 만족 버전/미해석 상태 구간, 동률 원문 순서, 기존 npm/의존 모듈 지문 |
| `pipeline/version_dependents/historical.py` | 입력 교집합, 구간 합집합·delta·양수 count 및 source/선언 품질, 작은 fixture adapter |
| `test_historical.py` | H2와 전체 날짜별 count·상태·품질 비교, 파티션·입력 순서·seeded fixture |
| `test_historical_semver_worker.py` | 새 후보만 검사, 후보 충돌, 기존 상태·동률·실행 상한 |
| `test_historical_kernel.py` | nested/adjacent/동일 구간, 누락·겹침·birth·INT 범위, 128개 초과 lookup batch와 오류 원문 |

H2 입력 구조·검증만 재사용한다. H2의 날짜별 재선택·중복 제거 계산은 공유하지 않는다.
결과 비교에서만 작은 target 목록과 구간을 펼쳐 H2의 0 포함 전체 키·선언·source 상태까지
일치하는지 검사했다. 기존 7번/H1/H2/8번 코드와 테스트 30개 파일의 해시가 이전과 같았다.

**기존 96개와 신규 25개, 전체 121개 테스트가 31.985초에 통과**했다. Python 파일 19개
AST와 Node 문법 검사도 통과했다. 별도 검토에서 미매핑 후보 모순·구간 입력 검증·정렬 동률을
보완한 뒤 PASS를 받았으며, 최종 JSON fixture adapter의 NULL/타입 보존도 따로 검토했다.
[검토 기록](evidence/historical-optimization-review.md)

### 실제 측정

최종 [비교 영수증](evidence/historical-optimization-comparison.json)은 같은 합성 입력과
같은 Node/npm/의존 모듈 지문에서 실행한 결과다. 반복 예제는 실행 순서를 번갈아 3회 측정했다.

| 항목 | 기존 H2 기준 | 새 H3 |
| --- | ---: | ---: |
| 16개 날짜·124개 버전 반복 예제 실행 시간 중간값 | 1.859초 | 0.219초 |
| 반복 예제 시간 측정 3회 | 2.109 / 1.859 / 1.813초 | 0.219 / 0.234 / 0.218초 |
| 날짜별 선언 해석 호출 / 고유 조건 파싱 | 3,840회 해석 호출 | 고유 조건 2개 파싱 |
| H3가 실제 검사한 새 후보 | 해당 지표 미계측 | 8회: 후보 4개 × 조건 2개 |
| 출력 양수 count 행 | 비교 기준은 0 행도 출력 | 16행 |
| 작은 3일·6버전 예제 실행 시간 1회 | 0.172초 | 0.234초 |

반복 예제의 최종 전체 실행 시간이 약 8.49배 개선됐다. 매우 작은 예제에서는 DuckDB 초기화
등의 비용 때문에 H3가 더 느렸다. 모든 입력에서 빨라진다는 주장이나 실제 229일 실행 시간의
추정치로 사용하지 않는다. 메모리·임시 디스크 최고 사용량과 실제 원본 성능은 미측정이다.

반복 예제는 source 버전 120개가 일반 의존성 두 개로 같은 dep를 가리킨다. dep 버전 4개가
4일 간격으로 등장하며, 각 날짜에는 현재 선택된 dep 버전 하나의 count가 정확히 120이다.
lookup 구간 8개, source와 교차한 선언 구간 960개, 중복 제거된 관계 구간 480개,
target 증감 이벤트 8개에서 양수 count 16행을 계산했다. 선언 수와 고유 관계 수는 별도로
보존했다. 두 예제 모두 전체 키/count/선언/source/품질 대조와 runtime 지문 일치가 통과했다.

### 발견한 문제와 해결

1. 초안 worker가 매 날짜 누적 후보를 다시 검사했다. birth별 새 후보만 검사하고 winner를
   유지하도록 수정했다. 날짜 32개에서도 후보 3개 × 조건 2개의 검사 6회가 유지되는지 검증했다.
2. 미매핑 상태명 `UNMAPPED`를 기존 `UNMAPPED_TARGET_PACKAGE`로 맞췄다. 미매핑인데 후보를
   함께 전달한 모순 입력은 실패시킨다. alias/prerelease/protocol 기존 정책은 변경하지 않았다.
3. 동일 시작·종료 시각의 중복 구간에서 두 SQL window의 정렬이 달라 count가 120 대신
   121이 되는 오류를 반복 예제에서 발견했다. 두 window 모두 원본 `declaration_index`를
   정렬 기준에 포함했다. 120 source × 2 선언 × 4 구간에서 각 날짜 120과 관계 구간 480을
   확인하는 회귀 테스트를 추가했다.
4. 최초 반복 예제는 H3가 4.422초로 더 느렸다. 행별 입력을 list batch로 바꿔도 3.969초가
   걸렸다. 프로파일과 import 추적에서 DuckDB의 Python 값 변환이 없는 `pandas` 모듈을
   25,324회 찾는 비용을 확인했다. fixture만 JSON 문자열 두 개와 명시적 타입으로 일괄
   전달하도록 바꿔 새 패키지 설치 없이 0.219초를 얻었다. 생산 Parquet 입력 연결은 별도다.

중간 측정은 [행별 입력](evidence/historical-optimization-before-batch.json)과
[list 입력](evidence/historical-optimization-before-json.json)에 보존했다. 이슈 해결 전의
측정값을 최종 구현 성능으로 표시하지 않는다.

### 결과 확인과 재현

최종 예제 폴더:
`data/version-dependents/optimization-examples/run_id=h3-20260910T134625831970Z`

- [3일 예제 H3 결과](../../../data/version-dependents/optimization-examples/run_id=h3-20260910T134625831970Z/golden-optimized.json)
- [16일 반복 예제 H3 결과](../../../data/version-dependents/optimization-examples/run_id=h3-20260910T134625831970Z/repeated-optimized.json)
- [최종 비교·시간·코드 SHA](evidence/historical-optimization-comparison.json)
- [재현 스크립트](evidence/historical-optimization-check.py)
- [테스트 결과](evidence/historical-optimization-validation.json), [테스트 로그](evidence/historical-optimization-tests.log)

저장 결과는 `scope=BOUNDED_H3_FIXTURE`, `ready_for_load=false`다. 재현 스크립트는 저장소
루트에서 다음처럼 실행하며 매번 새 예제 폴더를 만든다. 실제 H1 자료는 읽지 않는다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -c "import runpy; runpy.run_path('docs/worklogs/S15P21A506-193/evidence/historical-optimization-check.py', run_name='__main__')"
```

## 다음 단계와 제한

다음은 H4의 과거 계산 결과 Parquet·manifest·재개 목록 저장과 파일 검증이다. H3의
`aggregate_interval_tables`는 정규화된 DuckDB 입력 테이블을 받으며 파일 계보·입력 분할·
디스크 자원 설정은 이를 호출할 생산 실행기가 책임져야 한다. 작은 fixture adapter는
H2의 512버전·2,048선언·32일·예상 비교 2,000,000 상한을 그대로 사용한다.

worker 한 요청도 후보 100,000개·고유 조건 512개·후보×조건 2,000,000·결과 구간 20,000개·
JSON 프레임 7MiB를 제한한다. SQL kernel의 날짜 상한은 4,096이다. 실제 큰 패키지의
요구조건 batch 조정·메모리 사용·최신 진단 결과 대조·229일 전수 계산은 H4/H5에서 검증한다.
특히 전체 파일을 Python 리스트로 읽어 이 작은 adapter에 넣는 방식으로 확장하지 않는다.

DB의 0 저장/조회 계약과 PARTIAL 게시 결정은 여전히 미확정이다. 69.7억 행 생성·DB 적재·
Jira 접속·commit/push는 수행하지 않았다.
