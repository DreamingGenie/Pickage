# raw → Curated 검증 기록 (2026-09-14)

## 실행 환경과 범위

- 기반 커밋: `464c75e`, 작업 브랜치: `codex/raw-to-curated-pipeline`.
- Windows Python 기존 `.venv-bq`의 DuckDB/boto3, 설치된 Node/semver/npm-package-arg를 사용했다.
- repository metrics는 기존 고정 Spark Docker 이미지를 사용했다. 로컬에 pyspark를 추가 설치하지 않았다.
- raw 입력은 작은 두 스냅샷 `2026-08-28`, `2026-08-31` fixture다. 실제 수집 API와 DB는 호출하지 않는다.
- 기존 사용 중인 MinIO와 별개로 임시 컨테이너 `pickage-orchestration-smoke-20260914`를 만들고,
  그 컨테이너의 `pickage-raw`, `pickage-curated` 버킷에서만 S3 실검증을 수행했다.

## 발견한 오류와 해결

1. fixture의 Projects 컬럼을 repository builder가 소비하는 `Type/project_name/StarsCount/OpenIssuesCount`로 수정했다.
2. Spark 출력 파일이 목록에 있지만 host에서 읽히지 않았다. 해당 경로는 262~272자였으며 Windows
   `stat/open`이 실패했다. 동기화 지연으로 단정하지 않고 MAX_PATH 문제를 확인했다.
   짧은 작업 경로/run ID로 실행했고, 실행기의 예상 Spark 출력 경로 검사를 추가했다.
3. MinIO 첫 스냅샷은 6개 단계와 bundle 게시가 완료됐으나 테스트 보고서 생성기가 package_snapshot과
   package_identity 파일을 함께 읽어 schema mismatch가 발생했다. role별로 파일을 선택하도록 보고서 생성기를 고쳤다.
4. 같은 날짜에서 후속 단계 실패 후 코드가 바뀌면 새 run ID가 필요하다. ID 부모의 날짜가 같아도
   기존 builder가 ID를 이어받을 수 있으므로 같은 날짜를 허용하고 미래 날짜만 거부하도록 수정했다.
5. 마지막 검토에서 checkpoint 재사용 시 run ID 검사가 빠진 것을 발견했다. 다른 run ID로 오염된
   checkpoint가 통과하는 회귀 테스트를 먼저 재현하고, stage/snapshot/run ID를 함께 검사하도록 수정했다.
   수정 후 이 테스트와 전체 대상 테스트가 통과했다.

## 검증 명령

저장소 루트의 기존 Python 환경에서 실행했다.

```powershell
python -B -m unittest tests.test_orchestration_intake tests.test_orchestration_runner tests.test_orchestration_stages tests.test_orchestration_dependents tests.test_orchestration_parent -q
python -B -m unittest tests.test_orchestration_integration -v
python -B -m unittest discover -s pipeline/curated -p 'test_*.py'
python -B -m pipeline.orchestration plan --request pipeline/orchestration/request.example.json
git diff --check
```

합성 executor 테스트는 실행 제어의 실패·재개를 검사한다. 실제 전처리 통합 테스트와 혼동하지 않는다.
실제 S3 smoke는 동일 fixture를 격리 MinIO에 업로드한 뒤 `runner.run()`으로 각 스냅샷의 6개 native 단계를 실행한다.

## 측정 결과

| 확인 | 결과 |
| --- | --- |
| orchestration 입력·실패·복구·참조 수·ID 부모 테스트 | 최종 31개 PASS, 8.223초 |
| 기존 package/version 회귀 | 31개 PASS, 5.212초 |
| FakeS3 + 실제 6단계 + Docker Spark | 두 날짜 통합/실패 테스트 2개 PASS, 176.164초 |
| 격리 실제 MinIO | m1(08-28), m2(08-31) 각각 6단계 및 완료 bundle PASS |
| 실제 MinIO 현재/이전 완료 run 재검증 | 둘 다 PASS, 현재 ID 포인터를 이전 날짜로 되돌리지 않음 |
| 실제 MinIO CLI status | COMPLETE, 종료 코드 0 |
| 예제 요청 CLI plan | 네트워크 없이 통과 |
| Python 구문 검사 | 변경 범위 17개 파일 AST parse PASS |
| diff/공백 검사 | git diff --check 및 신규 파일 trailing whitespace 검사 PASS |

실제 MinIO에서 받은 Parquet 값을 확인했다. package_id는 첫 날짜의 alpha=1을 유지하며 두 번째 날짜에
beta=2, gamma=3을 추가했다. 두 번째 날짜 `1.0.0` 버전 기준 결과는 다음과 같다.

| package | package_id | downloads | stars | open_issues | dependents_count |
| --- | --- | --- | --- | --- | --- |
| alpha | 1 | 4800 | 10 | 0 | 0 |
| beta | 2 | 1 | 20 | 1 | 1 |
| gamma | 3 | NULL | 30 | 2 | NULL |

다운로드의 실제 `[2026-08-28, 2026-08-31)` 구간을 확인했다. alpha의 imputed gap은 유효 0으로
바꾸지 않고 관측된 2500+2300만 합산한다. gamma는 선택 대상 밖이어서 NULL이다.
첫 날짜 alpha의 다운로드는 이전 날짜가 없는 정책에 따라 NULL, 참조 수는 실제 계산 결과 0이었다.

실제 MinIO smoke 및 FakeS3 전체 통합은 마지막 checkpoint run ID 보완 직전에 통과했다.
그 보완 뒤에는 해당 거부 경로와 전체 31개 대상 테스트를 재실행했다. Spark 전체 통합을 중복 실행하거나
기존 완료 manifest에 새 코드 SHA를 덮어쓰지 않았다. `m1/m2`는 원래 생성 코드의 검증 증거로 유지한다.

원본 실행 증거는 ignored `data/orchestration-verification/`에 보관한다:
`unit.log`, `curated-regression.log`, `real-minio.log`, `real-minio-second.log`,
`real-minio-report.json`, `m1-bundle.json`, `m2-bundle.json`, `cli-status.log`, `plan.json`.
테스트 MinIO는 검증 후 제거했다. 실제 사용자 MinIO/DB 컨테이너는 그대로 유지했다.

## 미실행 경계

- 운영 raw 전체 스냅샷 실행 및 처리 시간·메모리·임시 디스크 규모 측정.
- 운영 MinIO 버전에서의 호환성/장애 복구와 다중 호스트 실행.
- BigQuery 새 날짜 감지, 원본 수집, 스케줄러 배포, DB 적재 및 Java 코드.
- 8번에서 수행한 과거 전체 행 정합성 검증의 재실행.

작은 fixture 결과는 위 항목의 완료 증거가 아니다. bundle의 `db_loaded=false`를 유지한다.
