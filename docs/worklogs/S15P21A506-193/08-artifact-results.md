# 08. Parquet 저장 결과와 확인 방법

**스냅샷별 count·입력 이력·품질 정보를 저장하고 DB 없이 재검증하는 기능을 구현했다.**
아래 파일과 수치는 기능 확인을 위한 합성 데이터다. 실제 7번 결과를 집계한 수치가 아니다.

## 생성한 예제

예제 루트:
`C:\Users\SSAFY\workspace\S15P21A506\data\version-dependents\demo-20260910T071525695186Z`

각 `snapshot=<날짜>/run_id=synthetic-v1/` 안에 다음 네 파일이 있다.

| 파일 | 내용 |
| --- | --- |
| `counts.parquet` | 패키지 ID·버전·snapshot 날짜·정확한 시각·dependents_count |
| `lineage.parquet` | 관계·source·target 입력 이력 3행. run·manifest SHA·정책 SHA와 원본 검증 상태 |
| `quality.parquet` | 입력 행 수·고유/중복 관계 수·target 수·0인 target 수·최대 count·합계 등 1행 |
| `run_manifest.json` | 파일별 행 수·스키마·크기·SHA, 시간·입력 이력·품질·코드 해시 |

직접 Parquet를 읽은 결과:

| target ID | 버전 | 2026-08-31 count | 2026-09-07 count |
| ---: | --- | ---: | ---: |
| 10 | 3.0.0 | 3 | 1 |
| 20 | 1.0.0 | 0 | 0 |

8월 입력 관계 4개 중 중복 1개를 제거해 3개를 센다. 9월 합성 입력에는 관계를 1개만 넣었다.
두 날짜는 같은 run ID를 사용해도 다른 폴더에 저장되며 count가 섞이지 않는다.
source 모집단은 날짜마다 3개, target 모집단은 2개다. 두 날짜 모두 정확한 원천 시각은 합성 예제의 12:00:00 UTC다.

## 저장 파일만 재검증하기

현재 워크스페이스에서 아래 명령을 실행하면 원본 입력·DB 없이 8월 예제를 재검증한다.
SHA는 최초 생성 시 반환되어 [예제 증거](evidence/artifact-demo.json)에 보관된 값이다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents verify `
  --run-dir 'data/version-dependents/demo-20260910T071525695186Z/snapshot=2026-08-31/run_id=synthetic-v1' `
  --manifest-sha256 '31342cf869dc08e5c479e291867de82763cc638c7b4054888f2b6abd9db5cbf5' `
  --snapshot-at '2026-08-31' `
  --snapshot-timestamp '2026-08-31T12:00:00Z'
```

9월 manifest SHA는 `288debe2b499fb65da055a268fba8b57360c29a4c2a5a66f370d27f2a408f9ae`다.
경로·날짜·시각을 모두 해당 snapshot으로 지정한다. 두 run은 이미 별도 Python 프로세스로 각각 검증했다.

새 예제를 생성하거나 Python에서 실제 호출 구조를 확인하는 방법은
[모듈 안내](../../../pipeline/version_dependents/README.md)의 저장·검증 절에 있다.

## 검증 범위와 남은 작업

- 최종 전체 테스트 **39개 통과**, 12.383초. 기존 집계 20개와 파일 저장·검증 19개다.
- 두 날짜 분리, PARTIAL 차단, 누락·변조·잘못된 시간/키/값/타입, 2500년 microsecond, 기존 결과 보존·동시 실행·저장 중 실패를 검사했다.
- 저장 파일을 검사한 후에만 manifest를 쓴다. 기존 run은 덮어쓰지 않는다. 실패한 새 run은 남겨 두고 새 ID로 재시도한다.
- 결과 전체를 Python 리스트로 읽지 않는다. 파일 검증의 DuckDB 메모리 한도는 512MB·스레드 2이며 별도 임시 폴더를 사용한다. 집계 연결의 자원 설정은 호출자 책임이다. 실제 수천만 행 성능·최대 메모리는 측정하지 않았다.

현재 저장 계층은 원본 입력의 manifest·정책·전체 모집단을 승인하는 기능이 아니다.
항상 `input_verification=NOT_PERFORMED`, `verification_scope=LOCAL_ARTIFACT_ONLY`, `ready_for_load=false`를
기록한다. 로컬 `artifact_status=COMPLETE`는 파일 저장 완료이며 정상 게시용 `_SUCCESS`는 생성하지 않는다.
원본의 미해석·peer/optional 제외 품질을 다시 조사하거나 임의의 0으로 채우지 않는다.

실제 입력 디렉터리는 `requirements`와 `versions_full` 모두 `2026-08-31`만 확인했다.
다른 날짜를 계산하려면 그 날짜의 입력이 필요하다. 기존 7번 run은 PARTIAL·정상 완료 기록 부재·전체 target 미검증으로
정상 계산 승인 조건을 충족하지 못했다. **생산 입력 어댑터·실제 전체 계산·DB 적재·push는 수행하지 않았다.**

증거: [테스트 요약](evidence/artifact-validation.json), [테스트 로그](evidence/artifact-tests.log),
[CLI 실행과 저장 행 대조](evidence/artifact-demo.json), [입력 조사](07-input-contract.md).
