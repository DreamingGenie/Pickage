# 16. 전체 날짜 계산 코드와 작은 실제 표본 검증

## 승인 범위와 종료 조건

사용자 요청은 **코드 완성 → 작은 실제 데이터로 정확성·속도 확인 → 보고**까지다.
선정한 전체 패키지의 229일 계산, DB 적재, commit/push는 이번 실행 범위에 포함하지 않는다.
이 문서의 계획과 실제 결과를 구분하고, 표본 성공을 전체 실행 성공으로 기록하지 않는다.

## 변경 범위

- 기존 H1/H5-A 입력·생성 코드와 완료 산출물을 보존한다.
- 새 production 입력·실행·SQL 모듈과 테스트를 추가한다. 기존 npm worker, H4 cache와
  날짜별 Parquet 저장/재개 기능을 재사용한다.
- D-22 다운로드 CSV의 원본 SHA와 중복 제거한 이름 집합을 고정한다. 실제 실행은 그중
  명시한 작은 target 표본으로 한정한다. 해당 target을 참조하는 source는 전체 H1 모집단에서
  가져오며, 모든 후보 버전과 원본 선언 식별자를 유지한다.

## 작업 계획

1. 입력 manifest/H5-A/선정 CSV 지문을 검증하고 실제 후보 이력·고유 요구조건·원본 선언을
   SQL로 연결한다. 원본 배열 전체를 Python 메모리로 가져오지 않는다.
2. 같은 target 이름을 같은 hash partition에 배치한다. 고유 요구조건은 기존 worker의
   후보 수·요구조건 수·비교 횟수·응답 구간 수·프레임 크기 한도에 맞춰 나눠 요청한다.
3. source의 최초 포함 시점을 적용하고 동일 source 버전→target의 겹친 구간을 합친다.
   날짜별 전체 관계를 펼치지 않고 양수 count 구간과 품질 변화량을 저장한다.
4. 완료 partition은 입력·runtime·생성 코드와 출력 지문이 일치할 때 재사용한다. 파티션별
   source 수를 단순 합산하지 않고 source 식별자로 통합해 품질을 계산한다.
5. H4 저장 계약으로 날짜별 count/품질/입력 이력을 만든다. 계산 완료와 PARTIAL 품질,
   DB 게시 가능 여부를 분리하며 ready_for_load=false를 유지한다.
6. 작은 합성 입력으로 중복·시점·여러 source 버전·파티션 경계·변조·재개를 검증한다.
   작은 실제 target 표본에서 229개 날짜를 계산하고 독립 날짜별 해석 및 최신 진단 결과와
   대조한다. 큰 후보 목록은 별도 제한된 요구조건 표본으로 프레임·처리 시간을 측정한다.

## 품질 범위

품질은 선정 target의 일반 dependencies 선언과 이를 가진 H1 적격 source 버전을 기준으로 한다.
이미 H1에서 제외된 NULL 배포일·비적격 버전의 원본 수는 H1 manifest에 보존한다. 정규화된
입력 안의 0을 전체 npm 원본의 누락/제외가 없다는 뜻으로 해석하지 않는다. peer/optional과
미해석 정책은 기존 계약을 유지한다. source의 extraction error/unknown도 유지한다.

## 실제 결과

**계산 코드와 실제 6개 target의 229일 표본 계산을 완료했다.** 저장 대상만 표본으로 제한하고
참조하는 source는 전체 H1에서 추출했다. 독립 날짜별 재계산과 기존 최신 진단에서 차이 0건이다.

| 실제 입력 | 값 |
| --- | ---: |
| 선정 target 이름 | 6개 |
| 해당 target의 전체 적격 후보 버전 | 49,936개 |
| 원본 일반 dependencies 선언 | 12,630개 |
| 고유 이름·요구조건 | 50개 |
| 서로 다른 source 패키지 | 362개 |
| 서로 다른 source 패키지·버전 | 12,630개 |
| 다운로드 선정 목록 밖 source 버전 | 6,546개 — 이 참조도 계산에 포함 |
| 기준일 | 2022-05-08 ~ 2026-08-31, 229개 |

표본 이름은 `@adguard/dnr-rulesets`, `@types/lodash.get`, `angularx-flatpickr`, `carrot-scan`,
`ddp-underscore-patched`, `less-plugin-autoprefix`다. 일반 규모의 3개는 이름 해시 순으로
선택하고 큰 후보 목록·참조 없음·후보 없음 사례를 추가했다. 임의 source 행을 잘라내지 않았다.
`carrot-scan`의 표본 요구조건은 INVALID_SPEC이라, 유효 요구조건에 대한 큰 후보 목록 처리는
별도 59개 실제 요구조건 측정으로 보완했다.

| 결과·측정 | 실측 |
| --- | ---: |
| 원본 검증·표본 입력 추출·저장 | 60.625초 |
| 파티션 계산·공통 cache·229일 파일 저장/내부 검사 | 33.219초 |
| 위 실행 중 날짜별 파일 저장/검사 단계 | 약 30.844초 |
| 별도 저장 결과 전체 재검증 | 13.578초 |
| 독립 날짜별 재계산·최신 진단 대조 | 29.360초 |
| count가 유지되는 구간 | 402행 |
| 양수 version·snapshot 결과 | 2,875행 |
| 최신 날짜의 양수 target 버전 | 14개, count 합계 7,202 |
| 표본 입력 Parquet 합계 | 138,682 bytes |
| 계산 run의 Parquet 합계 | 2,437,548 bytes |
| 계산 Python 프로세스 OS peak RSS | 155,320,320 bytes (약 148MiB) |

RSS는 계산 Python 프로세스의 값이며 입력 준비·Node 자식·시스템 전체 peak가 아니다.
입력 추출은 원본 전체 파일을 읽으므로 target 수에 비례해 시간이 줄지 않는다. 위 수치를
99,996개 전체 이름에 단순 곱해 전체 소요 시간을 예측하지 않는다.

최신 값 예시: `@types/lodash.get@4.4.9 = 4,183`, `less-plugin-autoprefix@1.5.1 = 1,189`,
`angularx-flatpickr@6.6.0 = 569`다. 각각 해당 버전을 가리키는 서로 다른 source 버전 수다.

독립 검증은 매 날짜 기존 7번 Node 해석기로 후보를 다시 선택하고 Python 집합으로 source
패키지·버전 중복을 제거했다. **229일 모두 count와 lookup 상태·정규화 range·선택 버전 차이
0건**, 기존 2026-08-31 진단의 해당 target count와도 차이 0건이다. 새 구간 알고리즘과
계산 방식은 독립적이지만 같은 npm semver/npa 정책을 사용하므로 기존 prerelease/alias 정책의
타당성을 새로 검증하거나 변경한 결과는 아니다.

큰 후보 목록 측정은 `@octopusdeploy/type-utils`의 **33,966개 후보 + 실제 요구조건 59개**를
사용했다. 229일 구간 요청은 metadata 포함 4회, 대기 합계 1.109초, 파일 읽기·기존 최신값
대조 포함 4.328초였다. 최대 요청 1,487,660 bytes, 최대 응답 1,623,798 bytes로 7MiB 한도 안에
들었고 최신 해석 결과 59개 모두 일치했다. 요청 bytes는 canonical UTF-8 JSON, 응답은 읽은
UTF-8 line 기준이다. 이 측정은 해당 패키지 전체 33,908개 요구조건의 계산이 아니다.

결과는 PARTIAL로 보존했다. 최신 표본 선언 중 5,428개는 미해석이며 성공한 7,202개만 count에
반영했다. source extraction error도 quality에 보존한다. `run_status=COMPLETE`는 표본 계산과
저장 완료이고 `ready_for_load=false`다.

입력은 `data/version-dependents/historical-production-inputs/sample-20260911-v2`, 계산 결과는
`data/vd-sample-20260911-v3`다. [표본 실행 수치](evidence/historical-production-sample.json),
[회귀 검증](evidence/historical-production-validation.json),
[테스트 로그](evidence/historical-production-tests.log)를 함께 확인한다.

전체 회귀 테스트 201개가 70.890초에 통과했다. 이후 진단 Parquet의 실제 물리 열 연결을
보완한 최종 검증기 테스트 7개도 2.312초에 통과했다. Python AST 38개를 확인했고 기존
Python 생성 코드 30개를 보존했다. 파티션·날짜 단위 재개/변조 거부와 겹친 선언·여러 source
버전·빈 lookup·잘못된 진단 날짜·긴 Windows 경로를 검증했다.
[최종 검증기 테스트](evidence/historical-production-verifier-final-validation.json),
[독립 날짜별 대조](evidence/historical-production-independent-verification.json),
[별도 파일 검사](evidence/historical-production-file-verification.json),
[큰 후보 목록 측정](evidence/historical-production-benchmark.json),
[문제와 수정 기록](evidence/historical-production-corrections.json).

**이번 종료 지점:** 코드 완성, 작은 실제 데이터 계산·정확성·속도 확인, 결과 기록까지다.
전체 선정 이름에 대한 계산·DB 적재·commit·push는 수행하지 않았다.

## 구현에서 확인한 문제와 보완

- 최초 실제 입력 준비 `sample-20260911-v1`은 원본 배열을 lateral `UNNEST WITH ORDINALITY`로
  펼치는 과정에서 임시 디스크 40GB 한도에 도달했다. 완료 입력 manifest는 없으며 실패 폴더를
  보존했다. `SELECT unnest + generate_subscripts`로 선언과 원래 배열 순서를 함께 꺼내도록
  바꿔 delimiter join을 제거했다. source/target 정책과 자원 한도는 동일하게 유지한다.
- 두 번째 입력 준비는 동일 자원 한도로 60.625초에 완료했다. 첫 계산 실행은 파티션·공통
  cache를 만든 뒤 Windows의 260자 경로 제한 때문에 첫 날짜 manifest 임시 파일 저장에
  실패했다. 계산 전에 가장 긴 예상 임시 경로를 검사하도록 보완하고 짧은 새 run 경로
  `data/vd-sample-20260911-v3`를 사용했다. 실패 run을 덮어쓰지 않았다.
- 파티션 간 source 상태를 합치는 SQL에서 source별 이벤트 전체를 Python으로 읽던 부분은
  날짜·상태별 `SUM(delta)` 뒤에 읽도록 보완했다. Python으로 넘어가는 크기는 날짜×상태 수다.
- 재개는 완료 파일 SHA 확인에 더해 파티션에서 공통 count/target/quality를 재구성하여
  저장 cache와 양방향 `EXCEPT ALL`로 대조한다. 날짜별 저장 파일은 기존 H4 검증을 재사용한다.
- 최초 전체 테스트 198개 중 기존 Windows child 종료 후 잠금 해제 테스트 1개가 실패했다.
  같은 테스트를 별도 재실행했을 때 통과했다. 최초 실패 로그와 결과를 보존하며 최종 회귀
  실행 결과는 아래 증거에서 별도로 기록한다. 기존 H4 코드는 변경하지 않았다.
- 기존 진단 Parquet의 물리 열은 `resolved_dependents_count`이며 `run_id`는 폴더에서 만들어지는
  partition 열이다. 검증기에 실제 물리 스키마를 적용하고, 표본 날짜와 파일 내부 날짜·정확한
  시각이 같은지 검사했다. 진단 비교 실패를 count 불일치로 보고하지 않고 입력 연결 문제로
  수정한 뒤 재검증했다.

## 저장과 재개 계약

계산 partition은 target 이름의 SHA-256 앞 16자리 modulo로 결정한다. 같은 target에 대한
모든 source 선언을 함께 처리한 뒤 source ID/version/target의 겹친 구간을 합친다.
파티션 품질을 단순 합산하지 않고 source ID/version으로 다시 합쳐 여러 target을 참조하는
source를 중복 계산하지 않는다. 과거 229개 날짜의 전체 관계 행을 생성하지 않는다.

파티션 완료 영수증 → production provenance → H4 공통 cache → 날짜별 count/quality/lineage
→ 전체 완료 manifest 순서로 최초 지문을 연결한다. 기존 H4 `quality_origin`은 저장 어댑터의
기존 라벨이며, 새 provenance의 `computation_origin=H5_PRODUCTION_INTERVAL_SQL`이 실제 계산
출처다. 작업용 DuckDB·scratch·로그는 완료 출력 목록에 포함하지 않는 진단 자료다.

전체 경과 시간 제한은 없고, 개별 Node 요청 제한은 60초다. 기본 DuckDB 설정은 4스레드,
메모리 4GB·임시 디스크 40GB이며 파티션 시작 전에 20GB 여유 공간을 확인한다. 이 설정이
Node를 포함한 프로세스 전체 RSS의 강제 상한을 뜻하지는 않는다.
