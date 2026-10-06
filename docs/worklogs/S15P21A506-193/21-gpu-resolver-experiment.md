# 21. RTX 4070 Laptop 버전 해석 실험

## 범위와 CPU 기준

2026-09-11 사용자가 현재 결과를 커밋하고 GPU 개선으로 넘어가도록 요청했다.
CPU 기준 커밋은 `ff1777f`이며 전체 249개 회귀 검사를 88.137초에 통과했다.
기존 32개 표본의 전체 시간은 315.835초, 후보 조회·요청 구성·해석·응답 정리는
174.184초였다. 이 시간은 GPU 실측값이나 이번 실험의 예상값이 아니다.

현재 단계는 별도 실험 코드와 작은 실제 입력에서 정확성·속도를 비교하는 것이다.
기존 production 실행기, H1/H5-A/H4 생성 계약, 완료 산출물, 집계 정책과 DB는 변경하지 않는다.
실험 결과는 `ready_for_load=false`이며 전체 패키지 계산·DB 적재·원격 push를 실행하지 않는다.
새 GPU 파일은 CPU 기준 커밋 이후의 별도 미커밋 변경으로 둔다.

## 실제 환경 확인

- RTX 4070 Laptop GPU: 8,188MiB, driver 591.44.
- 기존 `C:/Users/SSAFY/miniforge3/python.exe`: PyTorch 2.7.1+cu128, CUDA 12.8,
  `torch.cuda.is_available()=true`, NumPy 설치됨. 추가 패키지 설치 없이 이 환경을 사용한다.
- DuckDB는 기존 `.venv-bq/Lib/site-packages`에서 참조한다.
- Ubuntu WSL2는 있지만 Python 3.14에 GPU 라이브러리가 없으므로 이번 실행 경로에 사용하지 않는다.

## 계획과 정확성 기준

1. Node에서 기존 npm/npa 규칙을 유지하여 stable 후보의 rank와 최초 포함 날짜를 만든다.
   rank는 semver 순위가 높을수록 크며, 동일 순위에서는 원문 UTF-16 문자열이 작은 후보가
   더 큰 rank를 갖는다. 기존 unsupported/invalid 상태와 PARTIAL 정책은 바꾸지 않는다.
2. 각 조건의 OR/AND comparator를 후보 rank 구간의 합집합으로 변환한다.
   실제·합성 표본은 모든 후보에 대한 구간 포함 여부를 기존 `Range.test`와 전수 비교한다.
3. 동일 숫자 입력에서 CPU min-birth segment tree와 PyTorch CUDA 묶음 계산을 비교한다.
   GPU는 rank 구간 포함 여부를 계산하고 birth별 `amax`, 날짜별 `cummax`를 수행한다.
   작업 배열은 묶음으로 제한한다. 전체 조건×후보×날짜 배열은 만들지 않는다.
4. 기존 worker의 모든 날짜 interval과 CPU/GPU 결과의 상태·버전·범위·경계를 비교한다.
   0건 불일치, 반복 출력 동일성, 잘못된 입력 거부를 완료 기준으로 둔다.
5. 입력 읽기·Node 시작·정규화·CPU 계산·H2D·GPU 계산·D2H·interval 변환·검증을 구분한다.
   반복 횟수와 cold/warm 시간을 기록한다. CPU 최적화 효과와 GPU 추가 효과를 구분한다.

실험 표본은 기존 prepared 입력에서 명시적으로 선택한 패키지와 제한된 요구조건만 사용한다.
후보 이력과 229개 날짜는 유지한다. 실제 표본의 한계와 전체 실행 미측정 사실을 함께 기록한다.
생산 통합은 이 실험 결과를 검토한 이후 범위다. 실험이 느려도 결과를 숨기거나 CPU로 조용히
대체하지 않는다. CUDA가 없으면 GPU 검사를 명시적으로 건너뛰고 GPU 완료라고 표시하지 않는다.

## 검토와 선택 이유

독립 설계 검토에서 stable-only 범위, UTF-16 동률, 미해석 상태, CPU 범위 인덱스 대조,
날짜 전체 정확성, VRAM·전송 포함 계측을 필수 조건으로 확인했다.
CuPy RawKernel 새 설치보다 기존 PyTorch로 작은 실험을 하는 경로를 선택했다.
커스텀 CUDA와 생산 실행기 통합은 이번 첫 실험에서 제외한다.

공식 근거: [scatter_reduce_](https://docs.pytorch.org/docs/stable/generated/torch.Tensor.scatter_reduce_.html),
[cummax](https://docs.pytorch.org/docs/stable/generated/torch.cummax.html),
[CUDA synchronize](https://docs.pytorch.org/docs/stable/generated/torch.cuda.synchronize.html),
[GPU 메모리 계측](https://docs.pytorch.org/docs/stable/generated/torch.cuda.max_memory_allocated.html).

## 실제 진행과 결과

별도 normalizer·CPU 범위 인덱스·PyTorch GPU 계산 및 비교 실행기를 구현했다.
기존 npm worker와 직접 비교하는 합성 검사는 8개이며 실제 CUDA 반복 검사도 통과했다.
`^`, `~`, 비교 연산, OR/AND, hyphen, wildcard, build 동률, 원문 순서, 늦은 배포,
빈 후보, invalid/prerelease 후보, unsupported/invalid 선언과 미해석 상태를 포함한다.

마지막 전체 회귀는 **257개, 91.586초, PASS**다. 현재 실험 코드 SHA가 두 실제 측정의
생성 코드와 같고 CPU production 생성 계약도 그대로임을 별도 확인했다.

### 실제 입력과 방법

- `@lightdash/common`: 기존 32개 prepared 입력, 적격 후보 **7,371개**.
- `@octopusdeploy/type-utils`: H1 target population과 H5-A lookup workload, 적격 후보 **33,966개**.
- 각 패키지에서 고유 요구조건을 `sha256(requirement)` 순서(NULL 우선)로 59/256/1024개 선택했다.
  세 크기는 같은 순서의 앞부분이므로 서로 독립적인 표본이 아니다.
- 모든 후보의 birth와 **229개 날짜**를 사용했다. 패키지 전체 요구조건의 완료 결과는 아니다.
- 모든 sampled 조건×후보의 rank 구간 포함 여부를 npm `Range.test`와 전수 비교했다.
  두 패키지·세 크기의 합계 55,350,243회 비교가 모두 일치했다.
- 기존 worker 결과는 1회 측정했다. 개선 CPU/GPU는 **5회**, 실행 순서를 교대하고 같은
  회차의 공통 정규화 시간을 양쪽 합계에 동일하게 포함했다. 전 날짜 interval의 모든 필드를
  기존 worker와 비교했으며 불일치 0건, 반복 결과 SHA 동일이다.
- 입력 Parquet SHA를 실행 전후 비교했고 실제 읽은 표본 payload SHA도 기록했다.

### 해석 구간 시간

개선 CPU/GPU 시간은 **npm 정규화 왕복 + 숫자 계산 + 원래 interval 형식으로 변환**한 합계의
5회 중간값이다. GPU 열에는 CPU↔GPU 전송과 호스트 배열 준비가 포함된다.
기존 열은 이미 시작한 production worker에 대한 batch 구성·요청·응답의 단일 측정이므로
새 방식과 같은 반복 통계 조건은 아니다. 큰 개선을 전부 GPU 효과로 해석하지 않는다.

| 패키지 | 요구조건 | 기존 방식 1회 | 개선 CPU 중간값 | GPU 중간값 | 개선 CPU 대비 GPU 배속 |
| --- | ---: | ---: | ---: | ---: | ---: |
| lightdash/common | 59 | 0.660초 | 0.0437초 | 0.0345초 | 1.27배 |
| lightdash/common | 256 | 2.499초 | 0.1154초 | 0.0704초 | 1.64배 |
| lightdash/common | 1024 | 10.424초 | 0.4309초 | 0.2904초 | 1.48배 |
| octopusdeploy/type-utils | 59 | 3.210초 | 0.1648초 | 0.1347초 | 1.22배 |
| octopusdeploy/type-utils | 256 | 13.868초 | 0.3056초 | 0.2154초 | 1.42배 |
| octopusdeploy/type-utils | 1024 | 54.073초 | 0.8753초 | 0.5256초 | 1.67배 |

1024개 기준 GPU 시간의 범위(min~max)는 lightdash 0.2363~0.3687초,
type-utils 0.4631~0.6188초다. 1.48/1.67배를 전체 패키지의 보장 배속으로 사용하지 않는다.
기존 대비 큰 감소는 반복 후보 JSON 구성·재해석을 줄이고 범위 인덱스를 만든 효과를 포함한다.

### 세부 시간과 메모리

1024개 표본의 숫자 계산만 보면 CPU/GPU(전송 포함)는 lightdash **0.1863/0.0273초**,
type-utils **0.4804/0.1123초**다. 공통 npm 정규화는 각각 0.1600/0.2860초가 남는다.
각 값은 개별 단계 중간값이므로 이를 더한 값이 합계 중간값과 정확히 같지는 않다.
GPU compute는 앞뒤 동기화한 구간으로 GPU 연산과 호스트 실행 요청 비용을 포함한다.

| 1024개 표본 | 최고 tensor allocated | 최고 allocator reserved | 묶음당 조건 |
| --- | ---: | ---: | ---: |
| lightdash/common | 70.69MiB | 100MiB | 1024 |
| octopusdeploy/type-utils | 72.65MiB | 108MiB | 243 |

이는 PyTorch 메모리이며 화면·드라이버·다른 앱을 포함한 전체 VRAM 사용량이 아니다.
`workspace_mib=128`은 묶음 임시 배열 예산이다. rank/birth 및 전체 구간 경계 배열은 별도이므로
GPU 전체 메모리의 엄격한 128MiB 상한이 아니다. OR 구간이 많을 때의 패딩 비용도 생산 통합
전에 보강해야 한다.

입력 읽기와 SHA 확인은 패키지별 한 번 수행했다. 최초 읽기·해시는 lightdash 0.351초,
type-utils 1.924초였다. 전체 실험 함수는 각각 21.655초, 99.711초였다. 여러 크기·반복·기존
비교·검증이 포함된 시간이므로 패키지 한 개의 전처리 시간으로 사용하지 않는다.

CUDA 기본 준비 이후 최초 GPU 경로와 warm 반복을 분리했지만, Python/PyTorch import와
CUDA context 최초 준비 전체 시간은 별도 측정하지 않았다. `cold_gpu`는 완전한 새 프로세스
시작 시간이 아니다. 생산 cold-start 또는 10만 패키지 전체 ETA로 사용하지 않는다.

### 결과와 남은 작업

완료 범위는 **정확성이 일치하는 GPU 해석 실험 코드와 실제 두 패키지 표본 비교**다.
기존 production 코드 생성 계약·기본값·PARTIAL 상태·집계·저장 경로는 변경하지 않았다.
새 코드와 기록은 CPU 기준 커밋 이후 미커밋 변경으로 남긴다.

다음은 CPU/GPU 공통 어댑터를 production 경계에 연결하고 작은 실제 입력의
해석→가중치 집계→날짜 Parquet→재개/독립 검증을 확인하는 것이다. 다양한 패키지 크기에서
GPU 선택 조건과 메모리 상한도 정해야 한다. 전체 계산은 이번 단계에서 시작하지 않는다.

[lightdash 상세](evidence/gpu-lightdash-results.json),
[type-utils 상세](evidence/gpu-octopus-results.json),
[최종 검증](evidence/gpu-experiment-validation.json),
[테스트 로그](evidence/gpu-experiment-tests.log).

## 재현

기존 Node/npm, DuckDB, NumPy와 CUDA 가능한 PyTorch를 사용한다. production 필수 의존성은
추가하지 않았다. GPU 검사를 요청했는데 CUDA가 없으면 CPU 대체 성공으로 기록하지 않는다.
출력 폴더는 기존 폴더와 다른 새 경로를 사용한다.

```powershell
$env:PYTHONPATH = "$PWD;$PWD/.venv-bq/Lib/site-packages"
$env:VD_GPU_TESTS = '1'
& 'C:/Users/SSAFY/miniforge3/python.exe' -B -m unittest pipeline.version_dependents.test_historical_gpu
& 'C:/Users/SSAFY/miniforge3/python.exe' -B -m pipeline.version_dependents.historical_gpu_benchmark `
  --candidates-parquet data/vd-pilot-a/32/input/target_population.parquet `
  --lookups-parquet data/vd-pilot-a/32/input/lookups.parquet `
  --snapshot-count 229 --name '@lightdash/common' --limits 59 256 1024 `
  --output data/vd-gpu-lightdash-repeat
```
