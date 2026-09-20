# 병렬 dependents 적용 후 실제 데이터 재시작

## 변경 범위와 계획

사용자 요청: 실제 실험 재시작 및 직접 상태 확인 수단 제공.

- 이전 C:/pg914r2는 FAILED 기록과 frozen code/manifest 그대로 보존한다.
- 생성 계약이 바뀌었으므로 기존 checkpoint SHA를 새 코드로 바꾸지 않는다.
  C:/pg914r3, b831r3/w914r3 및 격리 MinIO 19050/19051로 새 전체 실행을 만든다.
- 기존 로컬 raw 사본을 서버의 고정 ETag와 비교하여 재사용한다. 서버에는 GET/HEAD/LIST만 한다.
- 총 DuckDB 4GB·2 threads, dependents worker 2개 및 128개 묶음을 사용한다.
- 8/31 baseline 전처리·로컬 Spring 적재 후 9/14 전처리·로컬 Spring 적재를 자동 실행한다.
- 새 코드·실행 환경·JAR을 고정하고 백그라운드 실행한다. 상태/로그/묶음 진행을 표시한다.
- 시작 후 실제 PID, heartbeat, 진행 증가를 확인한다. 실행 시작과 최종 성공을 구분한다.

## 수행 결과

- 2026-09-19 10:52:47 KST 실행 시작. 실제 Python PID 36832, launcher PID 41652.
- 새 독립 venv: Python 3.12.12 / DuckDB 1.5.5 / NumPy 2.2.6. 기존 venv는 변경하지 않았다.
- frozen source 523개(약 4.82MiB), 전체 SHA 검증 완료. `source-files.json`, `restart-evidence.json`에 기록했다.
- 기존 검증된 loader JAR SHA: `8cc5acf991923bef9dbad60236fac0f527cb23738b592be0b4052db8c9935893`.
- 서버 원천의 baseline 1,944개·weekly 973개 inventory 중 manifest/완료 marker의 크기·ETag와 접근을 확인했다. 데이터 객체는 복사 시 다시 확인한다.
- 새 MinIO `pickage-real914r3-minio`, localhost 19050/19051, CPU 1개·메모리 2GiB 제한. 기존 서버와 MinIO는 변경하지 않았다.
- 기존 격리 PostgreSQL localhost 15441에서 execution/package/snapshot이 모두 0건임을 확인했다. 이 테스트 DB에만 적재한다.
- 시작 직후 `RUNNING`, `baseline:COPY_RAW`, 실제 PID 생존, heartbeat 갱신 및 26/1,944개(0.305/12.711GiB) 진행을 확인했다. 오류 로그는 비어 있었다.
- 상태 화면: `powershell -NoProfile -ExecutionPolicy Bypass -File C:\pg914r3\status.ps1 -Watch`.
- stdout: `C:/pg914r3/run-20260919-105246.log`; stderr: `C:/pg914r3/error-20260919-105246.log`.
- 상태 화면을 Ctrl+C로 닫아도 백그라운드 작업은 계속된다. 실제 실행 종료와는 별개다.
- 전체 전처리·DB 적재 성공 및 최종 시간은 아직 미확정이다. 기존 5단계 완료 산출물은 생성 계약이 달라 이번 새 실행에서 다시 계산한다.
