# 24. CPU·GPU 버전 선택의 실제 집계 연결

## 요청과 변경 범위

2026-09-11 사용자 승인: 개선 CPU/GPU 버전 선택을 실제 dependents_count 계산에 연결하고,
작은 입력에서 정확성·재개를 확인한 뒤 기존 32개 패키지의 229일 집계·저장까지 비교한다.
시작 기준은 `2095c3d1b4ce61851a17b3d64e6d074007c691be`다.

변경 범위는 8번 production 실행기의 선택 가능한 해석 경로, 새 연결 모듈·테스트,
실제 표본 측정/검증 도구와 이 작업 기록이다. 기존 npm 경로를 기본값으로 둔다.
GPU 없이 실행할 때는 개선 CPU 경로를 명시할 수 있으며, GPU를 요청했는데 CUDA가 없으면
출력을 생성하기 전에 실패한다. 자동 CPU 대체나 속도를 위한 조건 누락은 허용하지 않는다.

일반 dependencies·배포일 NULL 제외·stable 후보·원문 동률 순서·PARTIAL 보존 정책,
선정 target과 전체 source 모집단, 기존 H4 저장 스키마를 유지한다. 미해석 정책 수정,
전체 99,996개 실행, 극단 3개 추가 평가, EC2/Spark·DB·Jira·commit·push는 이번 범위 밖이다.

## 계획

1. 기존 32개 완료 결과를 생성 당시 코드로 먼저 검증하고, 원본 파일 지문과 commit을 고정한다.
   production 코드 변경 후 현재 검증기에 과거 생성 계약을 허용하는 예외를 추가하지 않는다.
2. `npm`, `cpu`, `gpu`를 선택하는 backend 경계를 추가한다. 후보를 패키지 단위로 읽고,
   전체 요구조건을 메모리·전송 상한 안에서 묶음 처리해 기존 lookup_intervals 형식으로 전달한다.
3. 선택 backend·설정·NumPy/PyTorch/CUDA 등 runtime·새 코드 지문을 production plan에 기록한다.
   설정·생성 코드가 바뀐 재개를 차단한다. 기존 완료 manifest의 지문을 새 코드로 고치지 않는다.
4. 작은 합성 입력에서 npm/개선 CPU/GPU의 해석·집계·품질·최종 파일을 비교한다. 같은 설정의
   파티션/날짜 재개, 다른 backend 재개 거부, 변조·CUDA 부재·CPU의 torch 비의존을 검사한다.
5. 기존 32개와 같은 이름·전체 요구조건·source·229일로 공통 입력을 한 번 준비한다.
   CPU/GPU를 별도 새 run에서 순차 실행해 집계·날짜 저장·독립 검증까지 측정한다.
   단독 32개 측정이며 전체 선정 패키지 예상시간으로 단순 환산하지 않는다.
6. 기존 결과와 새로운 두 경로를 lookup·count·품질 행 단위로 비교한다. runtime/provenance가
   다른 파일의 바이트 동일성 대신 값 동일성을 검사하고 원본 파일 SHA 보존도 재확인한다.

입력 준비·버전 해석·집계·병합·날짜 저장·별도 검증을 구분한다. 새 코드로 전체 흐름을
통과한 시간이 나와야 기존 resolver-only 9.86초와 구분해 보고할 수 있다.

## 완료 기준

- 새 경로로 32개·40,701개 조건·141,607 후보·229일 결과를 생성하고 기존 count/품질과 일치한다.
- 신규 경로의 검증 및 같은 설정 재개가 성공하고 backend/코드 변경 재개는 거부된다.
- GPU 없이 개선 CPU를 실행할 수 있으며 GPU 미실행을 GPU 성공으로 기록하지 않는다.
- 원본 파일 보존과 새 실행의 코드·설정·입력·출력 연결 증거, 단계별 시간과 자원 관측을 남긴다.

## 실제 진행

착수 시 기존 production 실행기가 npm worker를 사용하고 개선 CPU/GPU는 별도 비교 도구에만
연결되어 있음을 확인했다. 독립 설계 검토에서 backend 계약을 production 경계에만 추가하고
H4 공통 계약은 유지하기로 했다. 이하 구현·실측 결과는 수행 후 기록한다.

## 구현 및 작은 입력 검증

- production `run`에 `npm`/`cpu`/`gpu` 선택을 추가했다. 기본값 npm과 기존 집계 알고리즘은
  유지하며, 이번 비교는 두 개선 경로 모두 `weighted-events-v2`를 명시한다.
- 정규화가 입력 후보를 제외·변형하지 않았는지, rank별 버전과 등장 날짜가 일치하는지,
  Node/npm 라이브러리/options/동률 정책이 같은지 확인한 후 숫자 계산을 수행한다.
- 요구조건은 최대 1024개씩 처리한다. 조회 커서는 삽입 연결과 분리했다. 2,701조건의
  1024/1024/653 분할과 실제 2,051조건·4,102구간 삽입 검사로 배치 경계의 누락을 확인했다.
- PyArrow는 현 환경에 설치되어 있지 않았다. 새 의존성을 추가하지 않고 DuckDB의 타입을
  지정한 열별 `UNNEST` 삽입을 사용했다. 행마다 SQL을 호출하거나 JSON을 다시 만들지 않는다.
- 요구조건 0개인 패키지는 후보 검증만 수행한다. GPU 숫자 계산을 가짜로 실행하지 않는다.
- CPU는 NumPy만 사용하고 PyTorch를 import하지 않는다. GPU 경로는 CUDA 요청 실패를
  CPU 성공으로 바꾸지 않는다. GPU 시간 항목은 합계, 메모리 항목은 최고값으로 기록한다.
- backend·batch·GPU 예산·라이브러리/장치 정보·연결 코드 SHA를 plan/provenance에 기록한다.
  기존 H4 생성 계약은 보존했다. 새로운 plan을 과거 완료 결과에 덮어씌우지 않는다.

합성 입력에서 npm/CPU/GPU의 13개 비교 그룹(입력 4종, 파티션 4종, cache 3종, 날짜별 2종)을
모두 비교했다. 날짜별 quality의 실행 plan SHA는 제외하고, 각 실행의 독립 검증이 해당
실행 ID·생성 이력·파일 SHA를 별도로 검사한다. CPU의 파티션/날짜 부분 재개, GPU의 파티션
재개, 두 경로의 완료 후 재개, backend/설정/runtime/code 변경 거부와 출력 변조 거부를 확인했다.

GPU를 켠 전체 회귀 재실행: **281개 검사, 오류 0, skip 1, 121.261초**. skip은 생성 코드가
다른 과거 32개 저장 fixture를 현재 코드로 직접 여는 테스트 클래스다. 그 원본은 코드 변경
전에 기존 생성 계약으로 검증했으며, 새 합성 fixture의 입력 loader·CUDA 검사는 실제 실행했다.
Python 62개 파일의 구문 검사도 통과했다.

첫 전체 회귀에서는 기존 실험 도구의 `status.json` 교체 중 Windows `PermissionError`
한 건이 발생했다(281개, 121.642초). 해당 검사는 단독 재실행에서 통과했고 이후 전체 재실행도
통과했다. 새 실제 측정 도구의 진행 파일은 같은 일시 잠금에 대해 최대 0.45초 재시도한다.
실패 로그는 보존하며 이를 계산 결과 불일치로 기록하지 않는다.

## 실제 32개 실행

새 출력 루트: `data/vd-i32`. 실행 중 코드는 고정했다. 입력을 한 번 준비한 뒤 CPU 실행·검증,
GPU 실행·검증, 이전 결과/CPU/GPU의 행 단위 대조를 순서대로 수행한다. 각 단계는 새 Python
프로세스이며 장치 초기화도 실행 시간에 포함한다. 프로세스와 작업 폴더의 자원은 1초 간격
표본으로 기록한다. 시간 경과에 따른 종료 제한은 없다.

이번 표본은 32개 target에 해당하는 **모든 적격 source 선언**을 사용하며 요구조건을
일부만 잘라 쓰지 않는다. 전체 99,996개 target 계산과 DB 적재는 수행하지 않는다.
아래는 이 실행에서 수집한 실제 측정값과 최종 파일 검증 증거다.

### 측정 결과

아래 시간은 **32개 target의 모든 요구조건과 229개 스냅샷**에 대한 값이다. 최신 날짜 하나나
패키지 하나의 시간이 아니다. CPU/GPU가 같은 준비 결과를 사용하므로 공통 준비 시간 64.301초를
각 경로의 합계에 한 번씩 더했다. 실제 준비 실행 횟수는 1회다.

| 단계 | 이전 CPU 측정 | 개선 CPU | GPU |
| --- | ---: | ---: | ---: |
| 공통 입력 준비 | 68.401초 | 64.301초 | 64.301초 |
| 해석·집계·Parquet 저장 | 230.669초 | 74.687초 | 71.502초 |
| 별도 파일 검증 | 16.764초 | 17.148초 | 17.288초 |
| **합계** | **315.835초** | **156.135초** | **153.091초** |

이전 CPU 측정은 [20번의 동일 32개 표본](20-daily-verification-throughput.md)이다.
이번 새 CPU/GPU 경로는 각각 한 번 순차 측정했다. 입력·최종 출력 값은 같지만 시점·캐시와
장치 초기화 비용이 달라 1~2초 차이를 안정된 성능 차이라고 일반화하지 않는다.

- 이전 흐름 대비 전체 시간은 개선 CPU **50.56%**, GPU **51.53%** 감소했다.
- 개선 CPU에서 GPU로 바꾼 추가 전체 감소는 **3.044초, 1.95%**였다.
- 숫자 계산 부분은 CPU **6.169초 → GPU 0.720초**, 약 **8.57배**다.
- 후보 조회·Node 정규화·숫자 계산·구간 변환·DuckDB 전달까지 포함한 해석 경로는
  **20.049초 → 14.566초**로 **27.35%** 감소했다. 기존 22번의 resolver-only 9.863초와는
  측정 범위가 다르다. 이번에는 실제 count 집계로 전달하는 비용이 포함된다.

| 새 실행 내부 단계 | 개선 CPU | GPU |
| --- | ---: | ---: |
| 해석 전체 | 20.049초 | 14.566초 |
| count·파티션 품질 집계 | 16.999초 | 16.903초 |
| 전역 병합·공통 cache | 3.691초 | 3.379초 |
| 날짜별 저장·종료 검사 | 25.618초 | 26.181초 |

위 내부 단계 표는 입력 준비·별도 검증 및 실행 초기화·파티션 파일 저장 등의 나머지 비용을
제외한 분해다. GPU가 담당한 숫자 계산이 1초 미만이 되면서 공통 입력 준비, CPU 집계와
날짜별 저장·검증이 전체 시간의 대부분을 차지했다. 따라서 이 표본에서는 GPU 추가보다
앞서 적용한 CPU 알고리즘과 요청/전달 구조 개선의 전체 효과가 컸다.

### 정확성·재개·자원 증거

원본→개선 CPU, 개선 CPU→GPU의 13개 그룹을 각각 양방향 `EXCEPT ALL`로 대조했다.
중복 행도 포함해 차이가 없으며, 첫 번째 대조에 입력 선언 10,118,750행 자체도 포함했다.
최종 GPU가 이전 CPU와 같은 값임은 두 대조의 연결로 확인된다.

| 주요 결과 | 수량 |
| --- | ---: |
| 선택 패키지 | 32개 |
| 후보 버전 | 141,607개 |
| 고유 요구조건 | 40,701개 |
| 요구조건별 버전·상태 구간 | 502,119행 |
| 양수 count 구간 | 49,111행 |
| 날짜별 양수 count 결과 | **1,875,271행** |
| 날짜별 품질 | 229행 |

모든 입력/원본 결과의 보호 파일 **1,323개 SHA가 그대로**다. CPU와 GPU의 각 `verify_run`도
27개 파티션·229개 스냅샷 검사를 통과했다. 실제 GPU 완료 결과를 다시 `--resume`한 검사는
**18.693초**에 완료됐고 새 계산 파티션 0개, 완료 파일 **1,317개 SHA 및 run manifest 동일**을
확인했다. 재개 검사와 이전 결과 대조(약 50초 관측)는 위 처리 시간 합계에서 제외했다.

관측 process-tree RSS 최고값은 입력 준비 **3.96 GiB**, CPU 계산 **1.56 GiB**, GPU 계산
**1.92 GiB**였다. 입력 준비 scratch는 **1.05 GiB**, CPU/GPU 계산의 관측 scratch는 0이다.
GPU peak allocated는 **70.69 MiB**, reserved는 **134 MiB**였다. 시스템 메모리·임시 디스크는
1초 표본이므로 순간 최고값을 놓칠 수 있다. GPU 지표는 각 CUDA 호출이 기록한 최고값이다.

GPU가 실제 저장한 최신 스냅샷 예: `axios@1.20.0 = 1,132,689`,
`lodash@4.18.1 = 2,606,910`, `react@18.3.1 = 802,275`.
선정 target을 참조하는 전체 적격 source 버전의 성공 관계 수다. 패키지 이름 수나 다운로드 수가 아니다.

- [주요 결과·코드 SHA·비교표](evidence/production-backends-results.json)
- [단계별 원본 보고서·실행 계약](evidence/production-backends-run-report.json)
- [기존 생성 코드로 검증한 원본과 보호 파일](evidence/production-backends-baseline.json)
- [전체 회귀 성공 로그](evidence/production-backends-tests.log), [첫 회귀의 Windows 파일 잠금 오류](evidence/production-backends-tests-first.log)
- [실제 GPU 완료 재개](evidence/production-backends-resume.json), [GPU 저장값 예시](evidence/production-backends-examples.json)

### 실행 및 결과 조회

기존 데이터 파일을 가진 환경에서 새 비교는 다음처럼 실행한다. 출력 폴더는 존재하지 않는
새 경로를 지정한다. Python 환경에 DuckDB·NumPy·CUDA 지원 PyTorch와 기존 npm runtime이
필요하다. 이번 로컬 실행은 Miniforge Python과 `.venv-bq/Lib/site-packages`의 DuckDB를 사용했다.

```powershell
$env:PYTHONPATH = 'C:\Users\SSAFY\workspace\S15P21A506;C:\Users\SSAFY\workspace\S15P21A506\.venv-bq\Lib\site-packages'
$selectionPath = 'docs/worklogs/S15P21A506-193/evidence/daily-throughput-selection.json'
$referencePath = 'docs/worklogs/S15P21A506-193/evidence/production-backends-baseline.json'
$selectionDigest = (Get-FileHash -LiteralPath $selectionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$referenceDigest = (Get-FileHash -LiteralPath $referencePath -Algorithm SHA256).Hash.ToLowerInvariant()
& 'C:\Users\SSAFY\miniforge3\python.exe' -B -m pipeline.version_dependents.historical_production_backend_benchmark `
  --output data/vd-i32-next --selection $selectionPath --selection-sha $selectionDigest `
  --reference $referencePath --reference-sha $referenceDigest
```

이번 실제 파일은 `data/vd-i32/{cpu,gpu}/run_manifest.json`에서 추적한다. 각 manifest의
`cache.directory` 아래 `history/snapshot=<날짜>/complete.json`에 성공 attempt ID가 있으며,
그 attempt의 `counts.parquet`가 `(package_id, version, snapshot_at, snapshot_timestamp,
dependents_count)`를 담는다. 공통 `cache/target_population.parquet`로 0인 대상을 복원할 수 있다.
빠르게 볼 예제는 위 `production-backends-examples.json`에 담았다.

## 남은 범위

이번 단계는 **CPU/GPU 실제 집계 연결과 32개 전 날짜 검증 완료**다. 결과는 성공 관계만 센
PARTIAL이며 `ready_for_load=false`를 유지한다. 전체 선정 패키지 계산·DB 적재·commit·push는
수행하지 않았다. 전체 99,996개 시간은 이번 32개 평균으로 확정할 수 없다. 특히 제외된 극단
3개 패키지와 더 큰 입력/병합의 처리량·메모리를 확인한 뒤 전체 실행 범위를 확대해야 한다.

## 병렬 구조 변경 전 커밋

2026-09-11 사용자가 위 완료 작업의 관련 파일 커밋을 요청했다. production 연결 코드,
비교 실행 도구, 테스트, 문서와 작은 검증 증거를 한 커밋으로 고정한다. 앞 절의 commit 미실행은
측정 완료 당시 상태다. 병렬 실행 구조 구현, 전체 선정 패키지 계산과 push는 이번에 수행하지 않는다.

측정 코드 6개, 회귀 로그, 원본 보고서 사본, CPU/GPU run manifest의 SHA가 기록과 일치함을
다시 확인했다. 측정 당시 끝 줄 CRLF가 있는 Python 파일 3개와 보고서·로그에는 경로별 Git
속성을 적용해 원본 바이트를 보존한다. 과거 manifest나 측정값을 새 지문으로 덮어쓰지 않는다.

커밋 전 실제 CUDA를 포함한 production 연결 테스트 13개를 재실행해 27.400초에 모두 통과했다.
CPU/GPU 완료 결과의 전체 생성 계약도 현재 코드와 일치한다. 기존 281개 회귀·실제 32개 측정은
위 원본 증거를 유지하며, 이번 재검사와 구분한다.
[커밋 검증](evidence/production-backends-commit-validation.json),
[13개 테스트 로그](evidence/production-backends-commit-tests.log).
