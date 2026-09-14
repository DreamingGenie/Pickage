# 15. H5 실제 입력 연결과 계산 실행

## 2026-09-11 시간 제한 수정 및 재실행 계획

첫 실행은 2026-09-11 00:50:05 KST에 3,604.406초 경과로 자동 종료됐다.
`job_receipt.json`의 상태는 `BUDGET_EXCEEDED`, 원인은 `elapsed time`이다.
최고 RSS 8,279,638,016 bytes, 최고 scratch 13,813,055,488 bytes로 각 자원 한도
이내였다. 완료 Parquet/manifest는 생성되지 않았으며 기존 실패 기록을 보존한다.
세부 SQL 단계 로그가 없어 어느 집계가 오래 걸렸는지는 확정할 수 없다.

사용자는 근거 없이 설정한 1시간 제한을 수정하고 다시 실행한 뒤, 프로세스만 남겨 두고
모델의 반복 확인과 채팅을 중단하도록 요청했다. 이번 변경 범위는 다음과 같다.

1. `historical_job.py`에서 `max_seconds: null`을 명시적인 시간 제한 없음으로 지원한다.
   다른 메모리·디스크 한도와 실패/완료 검증은 유지한다. 큰 정수를 제한 시간으로 대신 넣지 않는다.
2. SQL 집계 전후의 세부 단계가 파일에 남도록 진행 기록을 보완한다. 집계 의미는 바꾸지 않는다.
3. 1시간을 넘긴 가상 경과 시간에서도 실제 child가 완료되는 회귀 테스트와 기존 유한 시간
   제한/자원 보호/별도 프로세스 통합 테스트를 실행한다.
4. 새로운 run 폴더와 config SHA로 숨겨진 독립 프로세스를 실행하고 시작 상태만 확인한다.
   이후 모델은 폴링하지 않는다. 완료 범위는 H5-A 입력 측정이며 후속 count 작업과 구분한다.

위 내용은 실행 전 계획이다. 검증 및 재실행 결과는 아래에 별도로 기록한다.

### 수정 후 검증 결과

관련 3개 모듈의 23개 테스트가 15.290초에 통과했다. 회귀 테스트는 경과 시간을 2시간
이상으로 모의하면서 실제 child가 정상 완료되는 것을 확인한다. 별도 Python 프로세스에서
시간 제한 없이 H1 합성 입력을 프로필로 저장하는 통합 테스트도 통과했다. 기존 유한 시간
종료, 무제한 시간에서 RSS 초과 종료, 출력 상한, parent 종료 및 완료 영수증 검사도 포함한다.
Python 30개 AST와 이전 검증 대비 이번 변경 5개 외 25개 파일 SHA 보존을 확인했다.

- [수정 검증 증거](evidence/historical-profile-unlimited-validation.json)
- [테스트 로그](evidence/historical-profile-unlimited-tests.log)

재실행은 `max_seconds=null`, `elapsed_limit_enforced=false`를 사용한다. 아래 3,600초 표는
첫 실패 실행의 설정이다. 새 실행에는 시간 경과 또는 무진행 시간에 의한 자동 종료가 없다.
메모리/디스크 예산은 첫 실행과 같다. SQL 시작 단계는 `GROUP_UNIQUE_REQUIREMENTS`,
`GROUP_PACKAGE_CANDIDATES` 등으로 기록되며 각 timestamp 간격으로 단계 시간을 알 수 있다.
`status.json`의 갱신은 supervisor 생존 기록이며 SQL 내부 처리율을 의미하지 않는다.
이번 수정은 시간 제한과 관측 기록에 한정하며, 프로필 중간 저장/재개 기능은 추가하지 않았다.

### 시간 제한 없는 재실행 시작

2026-09-11 05:39:41 KST에 새 run `profile-20260910T203912020724Z-unlimited`를 숨겨진
독립 프로세스로 시작했다. 05:40:04 최초 확인에서 supervisor PID 311328, worker PID 308232가
살아 있었고 시간 제한 해제·config SHA·실제 로드한 코드 SHA가 일치했다. 오류 로그는 0 bytes,
worker의 마지막 기록은 입력 검증을 마친 `SUM_SOURCE_DECLARATIONS`였다.
이 기록은 시작 확인이며 측정/count 완료 증거가 아니다. 이후 모델 폴링은 중단했다.

- [새 실행 영수증](evidence/historical-profile-unlimited-launch.json)
- [새 상태 파일](../../../data/version-dependents/historical-profiles/observed=2026-08-31/run_id=profile-20260910T203912020724Z-unlimited/status.json)
- [세부 진행 로그](../../../data/version-dependents/historical-profiles/observed=2026-08-31/run_id=profile-20260910T203912020724Z-unlimited/profile/progress.jsonl)

기존 실패 run의 영수증 SHA `7c93ec277020a90a14fd7ce8e4bd16866a17954c37b07491b5939ed169bc80dc`는
변경하지 않았다. 현재 실행은 완료 시 새 run 내부에 `job_receipt.json`과 결과 manifest를 남긴다.
모델이나 채팅 세션이 이 파일을 반복 조회할 필요는 없다.

### 완료 확인 및 실제 파일 재검증 (2026-09-11)

08:43:13 KST에 기존 실행이 COMPLETE·exit_code=0으로 정상 종료했다. 시작부터 종료까지
경과 시간은 11,012.219초이며 이동/절전 구간을 제외한 순수 계산 시간으로 해석하지 않는다.
입력/출력 검증 및 종료 전 입력 지문 재검증이 모두 완료 기록에 남았다.

| 항목 | 실제 결과 |
| --- | --- |
| source 버전 | 47,172,949 |
| 원본 일반 dependencies 선언 수 | 289,214,123 |
| 고유 대상 이름/요구조건 | 11,051,014 |
| 패키지 이름별 workload 행 | 4,134,640 |
| target 후보 버전 | 47,172,771 |
| Parquet | 2개, 합계 102,329,307 bytes |
| 실행 중 최고 RSS / scratch | 8,279,429,120 / 13,762,494,464 bytes |
| count 상태 / DB 적재 가능 여부 | NOT_COMPUTED / false |

사용자가 정상 완료 여부를 다시 확인해 달라고 요청해 별도 연결로 저장 파일을 전수 읽었다.
27개 검사가 12.778초에 통과했다. Parquet SHA·크기·스키마·행 수, 중복 키/고유조건,
lookup 순서와 birth 범위, 양수/NULL 계약, 선언/조건/후보 합계를 검사했다. 패키지별
lookup 수·선언 수와 H1 target에서 다시 집계한 후보 수·후보 JSON byte 추정치도
양방향 EXCEPT ALL에서 불일치 0이었다. 원본 package의 ID/이름 매핑도 일치했다.
독립 검토자는 최초 실행부터 완료까지의 SHA·PID 연결 및 현재 생성 코드 12개를 대조했다.

- [실제 파일 검사 27개 결과](evidence/historical-profile-completion-postcheck.json)
- [완료 기록·생성 코드 독립 검토](evidence/historical-profile-completion-review.md)

재검증 중 일회성 검사 코드의 manifest 키 참조와 SQL 별칭 문법을 수정한 뒤 최종 PASS를
기록했다. 저장된 산출물이나 구현 코드의 결함은 발견되지 않았고 해당 파일은 수정하지 않았다.
이번 후속 검사는 2.89억 원본 선언의 고유조건 묶음을 다시 생성하거나 229개 날짜의 semver
해석을 새로 실행한 것이 아니다. 완료한 범위는 H5-A이며 실제 count 계산은 다음 단계다.

## 변경 범위와 작업 계획

2026-09-10 사용자가 H5를 진행하되, 독립 계산에 들어가면 프로세스만 남기고 모델의 반복
확인을 멈추도록 요청했다. 이번 첫 실행은 **H5-A 입력 workload 측정**이다. 전체 229일
count 실행의 예산과 분할 기준을 마련하기 위해 고정된 실제 입력을 한 번 조사한다.

1. 기존 H1 manifest·원본 manifest·파일·생성 코드 지문을 대조한다. H1을 재생성하거나
   기존 7번 파일을 수정하지 않는다.
2. 실제 source의 일반 dependencies를 SQL로 묶어 고유 대상 이름/요구조건별 선언 수와
   최초 source 포함 날짜를 저장한다. 패키지별 후보 수·조건 수·worker 한도 초과를 측정한다.
   날짜별 관계나 0 count 행은 만들지 않는다.
3. 작은 합성 입력에서 NULL 선언·중복·미매핑·저장 파일 보존식과 실패 처리를 검증한다.
4. 독립 프로세스에 시간·메모리·임시 디스크·출력 상한을 적용한다. 진행/자원 상태와 완료·실패
   기록을 파일에 남기고, 시작 확인 후 모델 폴링을 중단한다. 프로세스의 자동 자원 검사는 계속된다.

현재 H3 kernel은 마지막에 양수 target×날짜를 메모리/임시 테이블로 확장한다. 전체 실행에
그대로 사용하지 않는다. 실제 후보 수와 요청 크기를 측정한 뒤 큰 패키지 처리·구간 출력
경로를 연결하고, H2/최신 진단 대조와 229일 backfill을 다음 H5 단계에서 수행한다.

## 실제 결과

입력 프로필 SQL, 입력/출력 manifest 검증, 독립 실행 supervisor를 구현했다.

| 파일 | 역할 |
| --- | --- |
| `historical_profile_queries.py` | DuckDB 내부 join/UNNEST 후 고유 조건·패키지별 workload 집계, Parquet 대조 |
| `historical_profile.py` | H1·원본·calendar·생성 코드 pin, 실행 전후 파일 검증과 결과 게시 |
| `historical_job.py` | 실제 계산 프로세스 실행, 자원 검사·parent 종료 감지·상태 및 최종 영수증 |
| 세 모듈의 `test_*.py` | NULL·중복·미매핑·한도 초과·파일 변조·별도 프로세스 성공/실패·강제 종료 |

### 생성 파일의 의미

`lookup_workload.parquet`는 고유 `(declared_name,requirement)`마다 하나의 행이다. 결정적인
lookup_id, 같은 조건의 원본 선언 수, 첫 source birth index를 기록한다. NULL 이름/조건,
빈 조건과 같은 source의 중복 선언은 각각의 의미를 보존한다.

`package_workload.parquet`는 패키지 이름별 후보 수·고유 조건 수·원본 선언 수·ID/매핑 유무·
후보 JSON 크기 추정치를 기록한다. 조건만 있고 후보가 없는 이름과 NULL 이름도 보존한다.
후보 수/조건 수의 상위 50개와 고정 해시 표본 20개는 manifest 통계에 남긴다.

이는 count 결과도 날짜별 source-target 관계 파일도 아니다. 실제 resolver 요청/응답의
전체 직렬화 byte 수는 아직 측정하지 않았다. 후보 JSON 크기는 DuckDB 직렬화 기준
추정이며, 프로필 완료를 전체 worker 실행 가능 판정으로 사용하지 않는다.

### 독립 실행과 확인 방법

새 job 폴더 안에 다음 기록을 남긴다.

- `config.json`: 입력 manifest SHA, 출력 위치, 실행 자원 예산. 최초 SHA는 launch 영수증에 고정한다.
- `status.json`: 실행/완료/실패/예산 초과, 실제 worker PID, 마지막 갱신 시각, 자원 관측치.
- `worker.stdout.log`, `worker.stderr.log`: 계산 프로세스 출력과 오류.
- `profile/progress.jsonl`: 입력 검증·조건 집계·출력 검증·완료 단계 기록.
- `profile/profile_plan.json`: 입력·코드·정책·calendar·DuckDB 지문.
- `profile/profile_manifest.json`, `profile/result.json`: 모든 입력/출력 검증을 마친 경우에만 생성.
- `job_receipt.json`: 종료 시점의 변경 불가능한 최종 기록. status는 이 파일의 SHA도 보존한다.
- `supervisor_lost.json`: 감시 프로세스가 강제 종료되면 worker가 실패 기록 후 종료한다.

OS 자원 검사는 5초 간격의 **soft limit**이다. 측정 사이의 순간 사용량에 대한 절대 상한이
아니다. RSS 최고치는 살아 있는 실제 프로세스에서 읽은 OS peak이며, 한 번도 측정하지
못한 경우 0 대신 NULL로 기록한다. DuckDB 메모리/임시공간 설정도 별도로 적용한다.

Windows 가상환경의 `python.exe`가 실제 인터프리터를 다시 실행해 Popen PID와 계산 PID가
다를 수 있음을 실제 subprocess 시험에서 확인했다. supervisor의 child는 base interpreter를
직접 실행하고 기존 환경의 module path를 전달한다. 따라서 PID·RSS·종료 감시 대상이
실제 계산 프로세스와 일치한다. 새 패키지는 설치하지 않았다.

parent-death guard는 실제 supervisor 프로세스 handle을 기다린다. supervisor를 강제 종료한
테스트에서 worker가 `SUPERVISOR_LOST` 실패 기록을 남겼다. PC 재부팅 자체를 테스트한
것은 아니며, 재부팅은 실행을 중단한다. 미완료 프로필을 COMPLETE로 간주하지 않는다.

코드 검토에서 받은 조치 사항은 [검토 기록](evidence/historical-profile-review.md)에 남긴다.
테스트와 실제 job의 실행 시점·위치는 아래 실행 영수증에 분리해 기록한다.

### 첫 실행 예산 (시간 제한으로 종료된 실행)

현재 PC의 RAM 약 68.2GB, 가용 RAM 약 39.2GB, 작업 디스크 여유 약 1.245TB를 확인했다.
모두 실행 준비 시점의 관측이며 실행 중 여유 공간은 다시 검사한다.

| 항목 | 이번 H5-A 한도 |
| --- | --- |
| DuckDB | 8스레드, 메모리 8GB, 임시공간 100GB |
| supervisor RSS | 16GB, 5초 주기 관측 |
| scratch / 결과·작업 DB | 100GB / 50GB |
| 유지할 디스크 여유 | 최소 20GB |
| 이번 입력 프로필 제한 시간 | 최대 3,600초 |

GB는 위 예산에서 10진 byte 기준이다. 1시간은 예상 소요시간이 아니라 자동 중단 한도다.
전체 229일 count 실행 예산은 프로필 및 실제 해석 표본 측정 후 별도로 정한다.

### 다음 H5 단계

프로필 결과를 확인해 큰 패키지의 후보 전체를 보존하는 분할/요청 방식을 정하고, 실제
resolver 요청과 응답의 정확한 frame 크기 및 처리시간을 측정한다. 날짜별 양수 count를
중간 테이블로 모두 확장하지 않는 production 구간 경로를 연결한 뒤, 최신 진단과 값 대조·
229일 전체 계산을 수행한다. 이번 입력 측정 프로세스는 그 단계까지 자동 진입하지 않는다.

### 구현 참고

Windows 메모리 계측은 Microsoft의 [GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo)와
[PROCESS_MEMORY_COUNTERS_EX](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex) 정의를 확인해 구현했다.


## 수행하지 않는 작업

H5-A의 PROFILE_COMPLETE는 전체 count 완료가 아니다. count_status=NOT_COMPUTED,
ready_for_load=false를 유지한다. DB/Jira/commit/push와 기존 산출물 변경은 수행하지 않는다.

## 실행 준비 및 검증 영수증

전체 177개 테스트가 57.357초에 통과했다. Python AST 30개와 기존 H4 코드 24개 SHA 보존을
확인했다. 실제 입력 프로필은 테스트와 별도로 실행한다.

- [테스트 결과](evidence/historical-profile-validation.json), [테스트 로그](evidence/historical-profile-tests.log)
- [실제 실행 영수증](evidence/historical-profile-launch.json): 최초 config SHA·PID·상태 파일 경로
- [실시간 상태](../../../data/version-dependents/historical-profiles/observed=2026-08-31/run_id=profile-20260910T144839066319Z/status.json): 실행 이후 생성
- [최종 종료 기록](../../../data/version-dependents/historical-profiles/observed=2026-08-31/run_id=profile-20260910T144839066319Z/job_receipt.json): 실행 종료 이후 생성

실행 시작을 확인한 뒤 모델은 반복 조회하지 않는다. 실제 성공 여부·처리량·최종 사용량은
프로세스가 남긴 기록을 사용자가 결과 확인을 요청했을 때 읽는다. 아직 없는 최종 기록을
완료로 표시하지 않는다.
