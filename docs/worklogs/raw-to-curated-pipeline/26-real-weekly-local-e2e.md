# 2026-09-18 실제 9/14 스냅샷 전처리·Spring 적재 실험

## 변경 범위와 계획

서버 weekly ingest가 게시한 raw를 SSH 터널(19000)로 읽는다. 서버에는 쓰지 않는다.
기존 로컬 MinIO(9000), 기존 DB와도 분리한다. 전용 MinIO 19030/19031 및
PostgreSQL 15441에만 쓴다. 운영 배포·timer·DB·MinIO current 변경은 없다.

1. 원천 객체 목록, 크기, ETag와 생산자 manifest를 고정한다.
2. 8/31 full raw로 새 기준 bundle을 생성하고 빈 테스트 DB에 적재한다.
3. 그 bundle을 parent로 9/14 weekly 전처리와 Spring 적재를 실행한다.
4. 각 전처리 단계, 전체 전처리, raw 복사, DB 적재 시간을 나누어 기록한다.
5. 실패하면 후속 처리를 중단하고 오류/heartbeat/실행 로그를 보존한다.

8/31은 준비 비용이며 추가로 평가할 신규 스냅샷은 9/14 하나다. 기존 8/31 DB를
변경하거나 채택하는 시험은 아니다. 과거 개별 산출물의 SHA를 새 코드로 바꾸지 않는다.
baseline은 이전 날짜가 없는 첫 회차이므로 downloads는 NO_PREVIOUS_SNAPSHOT 정책을 따른다.
9/14는 실제 [8/31,9/14) 구간을 사용한다. 표본 추출 없이 전체 raw를 사용하며 dependents
대상은 각 downloads 생산자의 실제 target CSV로 고정한다.

## 확인한 입력과 환경

- 9/14 weekly 수집 SUCCEEDED, 버전/requirements 각각 79,675,829행, projects 5,308,147행.
- 8/31 버전/requirements 각각 78,559,731행, projects 5,234,999행.
- baseline raw 1,944객체 약 12.711GiB, weekly raw 973객체 약 9.383GiB.
- 두 날짜의 native Bronze 및 downloads manifest 승인 계약 검사를 통과했다.
- 기존 완료 curated-bundle이 없으므로 baseline부터 실제 생산자로 생성한다.
- 전처리는 DuckDB 2스레드, 메모리 한도 4GB, I/O workers 2. 원격 복사는 직렬로 제한한다.
- 실행 코드는 C:/pg914/src에 고정 복사하고 파일 SHA를 source-files.json에 남긴다.
- source 자격증명은 기존 로컬 비밀 파일에서만 읽고 로그/저장소에 복사하지 않는다.
- 테스트 DB는 저장소 V1~V8 SQL을 순서대로 적용한다. API/Flyway 자동 배포 검증은 아니다.

## 실행과 상태 확인

실행 자료는 `C:/pg914`에 보관한다. `start.ps1`이 숨김 독립 프로세스를 시작하므로
채팅이 끝나도 계속 실행한다. 컴퓨터·Docker·SSH 터널은 켜져 있어야 한다.

```powershell
powershell -File C:\pg914\status.ps1 -Watch
# 한 번만 보기
powershell -File C:\pg914\status.ps1
# 로그 위치
Get-Content C:\pg914\launch.json
```

- status.json: 현재 phase, PID, heartbeat, 복사량, 오류.
- timings.json: 단계별 벽시계 시간. PREPROCESS_TOTAL은 하위 stage를 포함하므로 합산하지 않는다.
- w/b831/status.json, w/w914/status.json: 생산자 단계 상태 및 검증 완료 시각.
- db-baseline.log, db-weekly.log 및 run/db-*/last-run.json: Spring 로그와 NULL 제외 건수.
- baseline-db-result.json, weekly-db-result.json: DB 게시/스냅샷 확인 결과.
- inventory.json 및 *-request.json: 재현에 필요한 고정 입력.

실패 후 원인을 해결하고 start.ps1을 다시 실행하면 같은 요청과 완료 체크포인트를 재검증한다.
전처리 생성 코드가 바뀐 실험은 기존 실행 ID에 덧붙이지 않는다. 자동 무한 재시도는 하지 않는다.
기존 결과는 지우지 않고 보존한다. 실험용 컨테이너도 완료 후 자동 삭제하지 않는다.

## 검증 범위와 결과

실행기 회귀 시험 3개 통과: 변경된 원천 거부, baseline 실패 시 DB/weekly 미실행,
baseline→weekly 적재 순서. 2026-09-18 12:05 KST 독립 프로세스 PID 37948로 시작했고
`baseline:COPY_RAW`에서 실제 원천 9객체(약 0.098GiB) 복사 및 heartbeat 갱신을 확인했다.
기존 원본 worktree의 변경사항은 기존 untracked 파일 두 개 그대로였다.

실제 전체 처리 결과·소요 시간은 실행 완료 후 위 상태/결과 파일로 판단한다.
실행 시작만으로 전처리 또는 DB 적재 성공을 주장하지 않는다. 로컬 CPU·디스크와 SSH
터널을 사용한 시간이며 운영 EC2 성능 수치로 해석하지 않는다.
