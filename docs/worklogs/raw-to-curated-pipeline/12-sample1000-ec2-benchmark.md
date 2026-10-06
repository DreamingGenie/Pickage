# 패키지 1,000개 EC2 재실험

## 변경 범위와 계획
사용자 요청에 따라 1,000개 패키지와 그 모든 버전을 같은 입력으로 고정해 기존 방식과 두 EC2 Spark를 비교한다. 기존 실험 기록을 보존하고 sample1000-ec2-20260916-a1 전용 디렉터리와 MinIO 접두사를 사용한다.

1. Spark 종료 후 applicationId 조회 오류를 수정하고 회귀 검증한다.
2. app worker pids 제한을 data와 같은 512로 맞춘다. CPU, RAM, swap, 운영 서비스 보호 감시는 유지한다.
3. 원천 hash 검증과 1,000개 표본 추출 후 Spark → 기존 방식 → 결과 정확 비교를 분리된 백그라운드 프로세스로 실행한다.
4. 입력 동일성, 단계별 시간, cgroup CPU/메모리와 오류를 보존한다. 표본 내 역의존 결과는 전체 지표가 아니다. 기존 방식 repository는 local Spark를 사용한다.

## 검증 및 실제 수행
진행 중. 운영 배포 변경, DB 적재, 공식 Curated 게시를 하지 않는다. 이번 요청의 완료 범위는 수정 검증과 실험 시작이며 성능 결과는 실행 종료 후 확정한다.

## 수정·검증 및 착수
- 종료 전에 Spark application_id를 저장해 성공/실패 보고서가 종료된 연결을 조회하지 않도록 수정했다. 중지된 context 재접근을 거부하는 fake 기반 회귀 테스트를 추가했다.
- app worker pids 상한을 256에서 512로 변경했다. CPU 1, 컨테이너 RAM 2816MiB, executor heap 2GiB, swap 0은 유지했다.
- 선택 크기 limit=1000 적용. 관련 테스트 58개 통과(표본/공유경로/app supervisor 10개, 비교/감시/telemetry 등 42개, lifecycle 및 cluster evidence 6개).
- 배포 ZIP SHA256 356c8b1bc4025322af5cd8fec35dc6b97acb330c857ea649ab8a3c50f69dbe3d. 두 호스트 SHA 일치 확인 후 독립 세션으로 기동했다. app PID 1381889, data PID 2801417.
- 원래 작업 폴더 상태는 기존 untracked pipeline/duckdb_ui.py만 존재함을 확인했다. 원래 브랜치/인덱스는 변경하지 않았다.
- 착수 검증: data status=RUNNING/prepare, prepare 로그 시작 확인. app은 master 대기 중. 양 호스트 guard issue=null/consecutive_issues=0, 운영 서비스 healthy. 표본 준비 후 Spark/기존 방식/비교가 자동으로 이어지며 아직 성능 결과는 없다.
