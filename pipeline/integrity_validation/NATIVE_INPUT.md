# 작은 native 입력 연결

기존 작업과 병렬로 진행하는 **연결 코드 준비**다. 실제 대용량 산출물을 복사·조회하지 않고,
손으로 만든 작은 native 형식 예제로 검사한다. 기존 합성 SQL 검사와 별도 CLI를 사용한다.
이 단계의 성공은 입력 연결 확인이며 9번 전체 완료·DB 적재·공개 승인이 아니다.

## 지원 형식

| 요청 dataset | 재사용하는 기존 선택 함수 | 읽는 메타데이터 |
| --- | --- | --- |
| `package-version` | `pipeline.postgresql.input.select_run` | 원문 run_manifest.json, JSON _SUCCESS |
| `package-snapshot-observed` | `pipeline.postgresql.package_snapshot.load.select_run` | 원문 run_manifest.json, 텍스트 _SUCCESS, JSON _INPUT.json |

run·snapshot의 정확한 UTC 시각·manifest SHA·기대 건수를 요청 파일에 별도로 지정한다.
native 완료 표식과 내부 계약을 검사한 뒤 이 요청 값과 대조한다. JSON 중복 키도 거부한다.
요청과 원문 manifest의 시각은 기존 snapshot 정책으로 검사한다. 소수점 7자리 이상이나 초 단위
시간대 offset처럼 정책 밖인 표현을 조용히 잘라 맞추지 않고 거부한다.
요청 pin 자체가 승인된 원천에서 왔는지는 이 도구가 증명하지 않는다.
메타데이터는 로컬 파일 매핑만 제공하는 읽기 전용 계층을 통해 전달한다. 원격 client는 만들지 않는다.

historical package_snapshot, snapshot calendar, historical dependents는 이번 지원 형식이 아니다.
변경 중인 8번 적재 모듈을 복사하거나 전체 파일을 읽는 native validator를 호출하지 않는다.
historical manifest를 observed 입력으로 이름만 바꿔 넣어도 거부한다.

## 작은 예제 실행

이 worktree 루트에서 기존 DuckDB가 설치된 Python으로 실행한다. 각 출력 경로는 새 경로여야 한다.

```powershell
python -B -m pipeline.integrity_validation.native_fixture --output data/native-package-example
python -B -m pipeline.integrity_validation.native_input --request data/native-package-example/request.json --output data/native-package-report

python -B -m pipeline.integrity_validation.native_fixture --dataset package-snapshot-observed --output data/native-snapshot-example
python -B -m pipeline.integrity_validation.native_input --request data/native-snapshot-example/request.json --output data/native-snapshot-report
```

생성기는 manifest에 `synthetic_demo=true`를 넣는다. observed 예제의 quality 값은 스키마 테스트용
NULL이며 실제 품질 계약을 만족하는 데이터가 아니다. 기본 samples는 service·identity만 선택하고,
quality는 manifest 목록에 남긴다. 보고서는 읽지 않은 quality 파일을 검사했다고 표시하지 않는다.

## 요청 파일

생성된 `request.json`이 완전한 실행 예제다. 필드는 다음과 같으며, 빠진 필드·모르는 필드는 거부한다.

| 필드 | 의미 |
| --- | --- |
| `format_version`, `kind` | 정수 `1`, `native_metadata_bundle` |
| `dataset` | 위의 두 지원 형식 중 하나 |
| `snapshot`, `run_id` | 명시적으로 선택한 ISO 날짜와 native 실행 ID |
| `snapshot_timestamp` | 시간대가 있는 정확한 원천 시각. UTC 날짜가 snapshot과 같아야 함 |
| `manifest_sha256` | 별도로 선정한 원문 manifest의 소문자 64자리 SHA256 |
| `expected_counts` | package/version 각각의 건수 또는 package_snapshot 전체 건수 |
| `objects` | 정확한 native 논리 키 → request.json 디렉터리 아래의 상대 파일 경로 |
| `samples` | 검사할 native 파일의 `{key, path}` 목록. 빈 목록이면 메타데이터만 검사 |

`objects`에는 해당 run의 필요한 메타데이터 2개 또는 3개만 넣는다. 자동 탐색·최신 run 선택·glob은 없다.
sample key는 선택한 manifest의 서비스 파일 또는 observed quality 파일에 있어야 한다.
현재 코드를 해시해 과거 산출물의 생성 계약으로 채워 넣는 기능은 없다.
보고서의 `producer_declared_contracts`는 원문 값이고 `validator_sha256`는 기존 snapshot 시각 정책을
포함한 이번 검증 코드의 식별자다.

## 파일 검사와 제한

- 요청·메타데이터·선택 파일 각각 최대 2 MiB. 메타데이터 합계와 샘플 합계 각각 최대 8 MiB.
- 샘플 최대 16개·footer 합계 5,000행. DuckDB 1 thread·128 MB·spill 0 B.
- 읽기 전에 파일 종류·크기·상대 경로를 검사한다. 경로 탈출, wildcard, symlink·Windows reparse point를 거부한다.
- 선택 파일의 원문 SHA·크기, 기존 schema의 열 순서·타입, footer 건수를 검사한다.
- 원본 파일을 잘라 새 파일을 만들면 pinned 파일 SHA가 달라져 거부된다. 작은 원본 shard를 선택해야 한다.
- 전체 역할 파일을 선택했을 때만 합계 행 수를 manifest 총건수와 같다고 대조한다. 일부 선택은 일부로 표시한다.
- 선택한 작은 파일을 임시 복사해 해시·schema·footer가 같은 바이트를 검사하게 한다. 원천에는 쓰지 않는다.

행 값·키·FK·품질 의미·upstream 전체 lineage·생성 코드 일치·모집단 완전성·DB 검사는 별도 후속 검증이다.
이 단계의 native 입력을 기존 합성 SQL에 운영 정답으로 주입하지 않는다.

## 결과와 오류

새 출력 디렉터리에 `report.json`과 `report.md`를 만든다. 실제 읽은 metadata 키·SHA·크기,
선택한 파일별 검사 결과, 역할별 전체 파일 대비 검사 범위를 남긴다.

- 성공 종료 코드 `0`: 메타데이터 `MATCH`, samples `MATCH` 또는 `NOT_RUN`.
- 오류 종료 코드 `2`: stderr에 이유를 남긴다. 검증 오류에는 성공 보고서를 만들지 않는다.
- 기존 출력 디렉터리는 거부하며 이전 결과를 덮어쓰지 않는다.

항상 `ready_for_load=false`, `ready_for_publication=false`, `task_09_complete=false`다.
원문 producer의 `PASSED`는 원문 주장으로만 기록한다. 실제 원천을 검증해 다시 승인한 상태가 아니다.
