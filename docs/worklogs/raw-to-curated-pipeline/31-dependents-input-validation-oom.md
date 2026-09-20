# dependents 전체 입력 검증 OOM 수정

## 변경 범위·계획
- 2026-09-19 15:47 KST 복구 실행이 입력 검증 중 실패했다. 병렬 worker 시작 전이다.
- 앞 5개 단계 검증 54.972초, 원천 cache 검증 15.111초는 통과했다.
- 239,556,025개 declaration 전체에 source/version별 DISTINCT 집합 두 개를 만드는 검증 쿼리가 4GB 한도를 초과했다.
- DISTINCT 값 개수 > 1을 동일한 의미의 최솟값/최댓값 불일치 검사로 바꾼다. NULL birth 무시와 NULL error 별도 값 취급을 유지한다.
- 단위 테스트로 원래 쿼리와 결과를 비교하고, 실제 512개 입력 전체 검증을 2 threads / 4GB에서 실행한다.
- 기존 복구 소스/계획/증명/로그는 보존하고 v2 복구 출처를 별도로 고정한다. 원본 데이터 및 완료 checkpoint는 변경하지 않는다.
- 검증 통과 후 dependents부터 재시작하고 실제 worker 진입 여부를 확인한다. 운영 서비스는 변경하지 않는다.

## 결과
- 실제 production helper를 기존 SQL과 비교하는 81가지 nullable 값 조합 및 빈 입력 테스트를 포함해 수정 관련 14개 테스트 통과(7.835초). 병렬 계산·파이프라인 회귀 12개도 통과(83.586초).
- 실제 원본 manifest SHA `00e02d36d66b7380e1d453bf15a3d8fb73b3b3a1899d5fb18bc23cf502517bea`를 유지한 채 전체 `verify_inputs` 통과: 143.750초, 2 threads / 4GB / 임시파일 한도 100GB.
- 검증 행 수: declarations 239,556,025 / lookups 4,220,751 / target_names 99,996 / target_population 7,822,819. 128개 분할의 512개 파일을 검사했다. 명세·파일 해시, 구조/소유권, 전체 identity 및 source 일관성 검증을 생략하지 않았다.
- 증거: `C:/pg914r3/bounded-input-validation-v2-preflight.json`, `verify-input-v2.log`. 오류 로그는 비어 있다.
- 기존 `recovery-src`와 v1 계획·증명·원격 receipt는 보존했다. 새 코드는 `recovery-v2-src`, 복구 ID는 `bounded-input-validation-v2`이며 새 계획·증명 파일에 해시를 고정했다.
- 2026-09-19 16:13:55 KST `recover-v2-start.ps1` 실행. wrapper PID 9952, 실제 coordinator PID 44220. 현재 로그 `recover-20260919-161354.log`.
- 상태 화면은 최신 로그 5줄을 보여주고 이전 실행을 포함한 timing history임을 명시한다. 확인 명령은 기존 `powershell -ExecutionPolicy Bypass -File C:\pg914r3\status.ps1 -Watch` 그대로다.
- 16:17:38 KST 재시작 실행에서도 `INPUT_VERIFY source_consistency COMPLETE`, `INPUT_VERIFY COMPLETE`, `COMPUTE_PARTITIONS workers=2` 확인. 16:17:39에 partition 18과 87이 RUNNING으로 진입했다.
- execution receipt: coordinator 44220, worker 2개, 각 1 thread / 2000MB / 임시파일 한도 50000MB. 기존 총 2 threads / 4GB 요청을 유지했다.
- 여기까지 실제 입력 전체 검증과 worker 계산 진입을 확인한 것이다. 전체 분할 계산·결과 검증·DB 적재 완료는 아직 확인하지 않았다.

## 후속 실패와 커밋 시점 상태 (2026-09-20)
- 9/19 18:15:31 KST 128개 분할 모두 ACCEPTED, complete.json 128개 저장을 확인했다. 병렬 계산 구간은 16:17:38부터 약 1시간 58분이다.
- 18:16:24 최종 결과 병합의 `historical_production_quality.py:finalize_quality_weighted`에서 OOM으로 실패했다. `all_source_summary`를 source/version으로 GROUP BY하고 birth/error의 COUNT(DISTINCT)를 검사하는 별도 쿼리가 4GB 한도를 초과했다.
- 입력 검증 수정은 통과했으나 결과 병합의 같은 형태 쿼리는 아직 수정하지 않았다. 실제 데이터 불일치가 발견된 것은 아니다.
- 완료 분할/원본/복구 기록을 보존했다. 최종 검증 수정, 생성 계약을 보존하는 분할 재사용 복구, 최종 게시와 실제 DB 적재 검증은 남은 작업이다. 현재 실패 실행을 재시작하지 않았다.
- 사용자 요청에 따라 Spring 적재 구현, 전처리 병렬 연결, 격리 실험/상태 확인 도구, 지금까지의 복구 수정 및 작업 로그를 함께 커밋한다. 운영 배포·push·실험 데이터 파일은 포함하지 않는다.
