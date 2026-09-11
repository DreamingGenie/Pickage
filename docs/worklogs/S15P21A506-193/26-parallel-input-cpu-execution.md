# 26. 입력 분할과 CPU 병렬 실행 구현

## 요청·범위·계획

2026-09-11 사용자 승인으로 [25 계획](25-parallel-execution-plan.md)의 첫 구현 P0~P2를 진행한다.
기준 커밋은 `1ec693cfe2f77b2757d072a95a0c84abd2702ea2`이며 기존 32개×229일 결과를 보호한다.

변경 범위는 `pipeline/version_dependents/`의 새 병렬 입력·실행·검증 모듈과 관련 테스트 및 이 작업기록이다.
기존 생성 코드를 가능한 그대로 재사용하고 저장된 manifest에 새 지문을 덮어쓰지 않는다.
선정 target·전체 source·dependencies·NULL 제외·PARTIAL 정책은 유지한다.

1. 기존 입력과 CPU/GPU 완료 결과를 검증하고 원본 지문 목록을 보존한다.
2. 기존 논리 파티션별 입력 네 파일과 전역 검증 계약, 원본 변환·직접 준비 경로를 구현한다.
3. 독립 CPU worker와 coordinator 완료 발행·장애 복구를 구현한다.
4. 합성 데이터에서 입력·의미 결과·잘못된 입력·중단/재개를 검증한다.
5. 기존 32개 실제 입력으로 worker 1개 의미 대조 후 2/4개를 비교하고 단계별 시간·자원을 기록한다.

P3 결과 shard writer, P4 GPU 큐, 전체 선정 계산, EC2·Jira·DB 작업, commit·push는 이번 범위에 포함하지 않는다.

## 실제 수행·이슈·검증

### 구현 내용

- `historical_parallel_input.py`: 기존 128개 논리 partition을 물리 파일로 분리한다.
  `prepare()`는 H1/profile/raw를 읽고 바로 partition별 파일을 쓰며,
  `from_prepared()`는 기존 검증된 v1 입력을 변환한다. 기존 단일 Parquet를 중간 산출물로 다시 만들지 않는다.
- 각 `partition=NNN/`은 `target_names`, `target_population`, `lookups`, `declarations` 네 Parquet를 갖는다.
  빈 partition도 같은 스키마의 빈 파일 네 개와 `EMPTY` 상태를 기록한다.
- 준비 단계에서 전체 source 선언을 보존하고 입력 관계·중복·출생일·오류 상태·선정 목록을 검증한다.
  실행 시 coordinator가 전역 입력을 한 번 검증하고, worker는 자기 partition 네 파일만 검사·조회한다.
  종료 시에는 입력 바이트 지문을 재확인한다. 별도 최종 검증기는 전역 검증을 다시 수행한다.
- `historical_parallel_pool.py`: Windows spawn으로 CPU worker 1/2/4개를 유지한다.
  Node normalizer도 worker당 하나를 유지한다. 할당 전에 Windows Job Object에 넣으며,
  coordinator 또는 worker가 종료되면 해당 하위 Node까지 정리된다.
- `historical_parallel_worker.py`: 후보·조건·이름 자료를 작업 전용 DuckDB의 일반 테이블에 담는다.
  선언은 해당 partition Parquet view로 유지하고 기존 CPU 해석·가중치 집계 알고리즘을 재사용한다.
  각 작업은 별도 attempt 디렉터리에 네 결과 파일과 receipt를 저장한다.
- `historical_parallel.py`: coordinator만 run lock·assignment·complete pointer·최종 manifest를 발행한다.
  worker 수는 실행 이력이며 논리 plan에 넣지 않아 2→4개 변경 후 재개할 수 있다.
  완료 포인터를 우선 확인하고, 발행 직전 중단된 유효 candidate도 검사 후 채택한다.
  candidate가 여럿이면 네 결과 테이블의 실제 값이 모두 같을 때만 하나를 선택한다.
  외부 plan·변조된 파일·서로 다른 candidate는 실패시킨다.
- CPU 총 DuckDB thread 4개, 메모리 4GB, spill 예산 40GB를 worker 수로 나눈다.
  추가로 process tree RSS 12GiB·scratch 64GiB·여유 디스크 20GB를 확인한다.
  이 제한은 모든 프로세스를 합친 완전한 하드 메모리 격리가 아니라 1초 간격 보호 검사다.
  전체 실행 시간 제한은 없으며 Node 요청 한 건의 응답 제한은 기본 60초다.
- 최종 전역 품질 병합·날짜별 Parquet writer는 기존 구현을 사용한다.
  이번에는 P3 출력 writer 또는 P4 GPU 요청 큐를 구현하지 않았다.

### 오류와 해결

1. DuckDB의 별도 cursor가 TEMP TABLE `lookups`를 보지 못했다.
   각 worker 전용 DB의 일반 테이블로 바꾸고 별도 cursor 회귀 검사를 추가했다.
2. 처음 만든 partition manifest의 파일 목록이 같은 테이블 이름으로 덮어써졌다.
   `partition=NNN/table.parquet` 전체 상대 경로로 식별하도록 수정했다.
3. Windows 프로세스 생존 검사에 POSIX 방식 `os.kill(pid, 0)`을 사용하면 종료 동작이 될 수 있다.
   읽기 전용 Windows process handle/exit-code 검사로 고친 후 종료 테스트를 다시 실행했다.
4. 측정 helper가 모듈 이름 `__main__`으로 자식 프로세스를 시작해 실패했다.
   실제 모듈 이름을 명시했다. 실패 실행 `data/vd-p32`에는 계산 완료 결과가 없다.

### 완료한 검증

- 변경 전 기존 CPU/GPU run과 준비 입력을 원래 생성 코드로 재검증했다.
  `data/vd-p0/baseline.json`에 원본 JSON/Parquet 2,640개의 SHA 목록을 기록했다.
- 합성 입력·실제 Node CPU 계산·Windows process tree 테스트 **13개, 50.435초, 실패 0건**.
- worker 1개 결과 및 2→4개 재개 결과를 기존 CPU와 13개 의미 그룹으로 비교해 차이 0건.
  입력 네 그룹, partition 결과 네 그룹, 전역 cache 세 그룹, 날짜별 count/quality 두 그룹이다.
  생성 plan SHA처럼 실행마다 달라지는 lineage는 각 결과 자체의 검증기로 확인한다.
- candidate 발행 직전 / complete pointer 직후 중단, worker 강제 종료 후 재시도,
  완료 결과 재실행, 동일한 candidate 중복과 서로 다른 candidate 충돌, 파일 변조를 검사했다.
- H1/profile/raw의 작은 실제 Parquet와 selection CSV를 만든 direct `prepare()` 테스트에서
  외부 H1/profile/raw 인증 경계만 대체하고 테이블 생성·분할·전역 검증·네 입력 값 비교를 실제 수행했다.
  실제 32개 입력 준비에서는 이 경계도 대체하지 않는다.

### 실행 방법

입력 준비는 한 번 수행하고, 같은 입력 manifest SHA를 모든 worker 수 실험에 사용한다.
`from_prepared()` 변환 CLI 예시와 실행/재개 명령은 아래와 같다. 출력에는 새로운 짧은 경로를 사용한다.

```powershell
python -m pipeline.version_dependents.historical_parallel convert --prepared-dir <기존입력폴더> --manifest-sha256 <기존입력SHA> --output data/vd-p-input
python -m pipeline.version_dependents.historical_parallel run --prepared-dir data/vd-p-input --manifest-sha256 <분할입력SHA> --output data/vd-p-run --workers 2
python -m pipeline.version_dependents.historical_parallel run --prepared-dir data/vd-p-input --manifest-sha256 <분할입력SHA> --output data/vd-p-run --workers 4 --resume
python -m pipeline.version_dependents.historical_parallel verify --run-dir data/vd-p-run --manifest-sha256 <완료runSHA>
```

`run_manifest.json`은 모든 partition과 날짜가 끝난 경우에만 생성된다.
개별 partition의 완료 여부는 `partitions/NNN/complete.json`, 진행/실패 이력은 `progress.jsonl`에서 확인한다.
결과의 `PARTIAL`과 `ready_for_load=false`는 유지한다. 계산 완료 자체가 DB 적재 승인을 뜻하지 않는다.

### 실제 32개·229일 측정

실제 준비 입력: `data/vd-ps32`. 기존과 같은 32개 target, 141,607개 후보,
40,701개 요구조건, 전체 source의 선언 10,118,750개, 128개 partition 중 27개 READY.
실제 raw/H1/profile에서 직접 준비·분할·검증까지 **104.246초**였다.
입력 준비 비용은 worker 수별로 반복하지 않고 한 번만 합산한다.

| 구성 | 계산·저장 | 별도 결과 검증 | 준비까지 포함한 전체 |
| --- | ---: | ---: | ---: |
| 새 구조 1 worker | 99.125초 | 31.574초 | 234.946초 |
| 새 구조 2 workers | 75.285초 | 32.393초 | 211.925초 |
| 새 구조 4 workers | 63.605초 | 30.954초 | 198.805초 |

각 구성 **1회 관측**이며 1→2→4 순서로 별도 프로세스에서 실행했다.
준비 104.246초는 실제 한 번만 수행했고 표의 각 전체 값에 공통 비용으로 한 번씩 더했다.
기존 결과와의 개발용 13그룹 전수 대조 비용은 각각 27.721/28.725/27.707초이며,
표의 실제 전처리 합계에는 넣지 않았다. 별도 결과 검증은 표에 포함했다.

- 1→4-worker의 **계산·저장 시간은 35.8% 감소(1.56배)**했다.
  준비·검증을 모두 포함하면 새 구조 내부의 감소율은 **15.4%**다.
- 입력 4그룹·partition 4그룹·cache 3그룹·날짜별 2그룹을 각각 기존 CPU 결과와 비교해
  세 실행 모두 차이 0건. 229개 날짜의 양수 count는 **1,875,271행**으로 동일하다.
- 실행/검증/개발용 대조를 포함한 process tree RSS 관측 최고는 1/2/4 순서로 약
  **3.09/3.10/3.11GiB**였다. run 폴더 내부 spill은 관측되지 않았다.
  1초 표본이므로 순간 최고를 놓칠 수 있으며, 검증기의 시스템 임시 폴더는 이 디스크 수치에 포함하지 않았다.
  실제 디스크 read/write 바이트는 수집하지 않았다.
- worker들이 각자 사용한 시간을 더한 값은 실제 경과 시간과 다르다.
  예를 들어 partition 작업 시간의 합은 50.009/57.016/72.085초지만 서로 겹쳐 실행되어 실제 완료는 빨라진다.
- 최종 전역 cache 병합은 약 3.8초, 날짜 파일 저장·마지막 입력 지문 확인은 약 27~28초,
  독립 검증은 약 31~32초로 남았다. 이 부분에는 이번 CPU worker 병렬화 효과가 거의 없다.

### 판단과 다음 범위

**병렬 실행과 재개 구조는 구현·검증됐지만, 전체 전처리의 개선으로 채택할 근거는 아직 부족하다.**
앞선 [24 측정](24-cpu-gpu-production-integration.md)의 CPU 전체 156.135초보다
이번 4-worker 전체 198.805초가 길다. 기존 CPU 수치는 이번 실험에서 다시 측정한 대조군이 아닌 이전 관측값이다.
새 구조의 물리 입력 분할과 강화된 전역 검증 비용까지 포함한 비교임을 유지한다.

따라서 기존 production 기본 경로를 바꾸지 않고 새 병렬 경로를 명시적으로 선택하는 상태로 둔다.
다음 개선은 입력 분할 시 반복 스캔·다수 파일의 검사 비용, P3 날짜별 저장/검증 비용을 먼저 측정·개선하고,
같은 예산에서 교대 순서·반복 측정으로 전체 시간을 비교하는 것이다.
GPU 요청 큐를 겹치는 P4, 전체 선정 99,996개 계산, EC2, DB 적재는 실행하지 않았다.
**위 수치는 전체 약 10만 개의 예상 시간이 아니다.**

마지막 입력 검증은 전체 선정 모드의 `chosen_names=None` 경계와 manifest 이름·상태·경로 변조를 보강해
**5개, 8.542초, 실패 0건**이었다. 새 Python 8개 AST·공백 검사와 기존 산출물 **2,640개 SHA 불변**을 확인했다.
기존 생성 코드·기본 CLI·기존 결과 manifest는 수정하지 않았다. commit·push는 수행하지 않았다.

실행 경로: `data/vd-p32a/w1-r1`, `w2-r1`, `w4-r1`.
[전체 측정·정확성·보존 증거](evidence/parallel-cpu-results.json),
[13개 통합/프로세스 테스트](evidence/parallel-tests.log),
[최종 입력 5개 테스트](evidence/parallel-input-final-tests.log).

Windows 종료 동작의 근거: [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
실제 종료 여부는 위 Windows 프로세스 테스트로 별도 확인했다.
