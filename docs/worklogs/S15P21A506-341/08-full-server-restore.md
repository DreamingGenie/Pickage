# 전체 덤프 서버 전송과 별도 DB 복원

이 문서는 최초 복원 실행 당시 기록이다. 이후 인덱스 우선 방식으로 재개해 복원을 완료했고 서비스 전환까지 진행했다. 현재 결과는 [최종 결과](12-final-result.md)를 참고한다. 아래 미완료/미실행 표현은 최초 작성 시점의 범위다.

## 범위와 현재 상태

2026-09-14 사용자 요청으로 반복 중이던 로컬 원본 검증을 중단하고 전체 서버 복원을 진행한다. 원본 전수 검증과 서버 전수 값 비교는 유예하며 성공으로 표시하지 않는다. 기존 서비스 DB와 API 연결 전환은 이번 범위에 없다.

- 원본 덤프: `data/service-data-migration/341/local-dump-probe/full-20260914T065517Z/archive`
- 압축 크기: 10,233,114,532바이트, 234파일(233개 데이터 파일과 TOC).
- 로컬 전송 기록: `data/service-data-migration/341/server-full-20260914-01`
- 서버 실행 위치: `/home/ubuntu/service-data-migration/341/server-full-20260914-01`
- 원본 기준 시점: 2026-09-14 06:55:19 UTC. 서비스 지표의 229개 날짜와 별개인 PostgreSQL MVCC snapshot이다.
- 이전 실패 실행의 199개 receipt와 중단 실행의 5개 receipt는 원래 시점/이력을 그대로 보관한다. 서로 중복되므로 204개 완료로 합산하지 않는다.

## 실행 절차

1. SFTP로 directory archive의 파일을 서버에 전송한다. 기존 로컬 archive는 보존한다.
2. 전체 파일 SHA-256과 TOC 허용 목록을 검사한다. 덤프 검증 완료와 원본 전수 값 검증 완료는 구분한다.
3. 기존 `pickage`가 확인된 V1/빈 서비스 테이블 상태인지 확인하고 작은 백업을 만든다. 상태가 달라지면 멈춘다.
4. `pickage_import_341_full_restore_<고유값>` 후보를 생성하고 백업의 실제 V1 이력을 복원한다. Flyway V1 checksum을 확인한 후 후보의 빈 테이블만 제거한다.
5. `pg_restore --jobs 2`로 pre-data, data, post-data를 순서대로 실행한다. 기본 인덱스와 FK 생성/검증은 복원에 포함된다.
6. Flyway V2~V6, 파티션 구조 확인, ANALYZE를 수행한다.
7. 완료는 `RESTORED_UNVERIFIED`, `ready_for_service=false`로 기록한다. 서비스 전환이나 전수 데이터 일치를 뜻하지 않는다.

전체 모드는 `server_pilot.py --full-restore --work-dir <서버 폴더>`로 명시한다. 파일럿/벤치마크 번들은 받지 않으며 전체 복원 scope가 있는 manifest를 요구한다. 서버 시작 전 여유 공간 220GiB 이상을 요구한다. 이번 실행에서는 전송 경로와 PostgreSQL 데이터 볼륨이 같은 루트 디스크이고 전송 전 여유 공간이 약 294GiB임을 확인했다.

## 실행과 상태 확인

서버에서 SSH 종료와 독립적으로 실행한다. 전체 작업 시간제한은 두지 않는다. 에이전트가 지속해서 확인할 필요는 없다.

- `server-result.json`: 후보 DB 이름, 현재 단계, 단계별 시간, 최종 상태. 단계가 바뀔 때 갱신된다.
- `<후보DB>.restore-status.json`: pre-data/data/post-data 완료 이력. 긴 COPY 중에는 갱신되지 않을 수 있다.
- `restore.log`: 복원 오류와 출력.
- `server-run.log`: 실행기 오류와 최종 결과.
- `server.pid`: 서버 실행기 PID.

실패하면 해당 후보와 기록을 유지한다. 이 실행기는 부분 복원 DB에 그대로 이어 쓰는 기능이 없으므로 자동으로 덮어쓰거나 삭제하지 않는다. 서비스 DB는 유지된다.

## 검증 결과

전체 모드의 분기/검증 유예/상태 및 기존 파일럿 회귀 테스트를 실행한 뒤 시작한다. 실제 전체 서버 복원 결과는 실행 완료 후 확인하며, 준비 문서 작성 시점에 완료로 기록하지 않는다.


## 실제 시작 결과

- 234개 archive 파일과 검증/실행 번들 전송 완료. 서버 실행기 PID `3728695`로 SSH와 독립 실행을 시작했다.
- 같은 코드의 작은 실제 서버 표본으로 전체 모드 경로를 먼저 실행했다. `/home/ubuntu/service-data-migration/341/server-full-mode-smoke-20260914-01/server-result.json`의 최종 상태는 `RESTORED_UNVERIFIED`다. 후보 `pickage_import_341_full_restore_54745e5d7288`은 시험용으로 보존한다.
- 이 시험은 백업/V1 이력 복제 → 복원 → Flyway → 구조 확인 → ANALYZE 흐름을 실제 수행했으며 원본/서버 전수 값 비교는 실행하지 않았다.
- 준비 중 복원 결과 파일을 복원보다 먼저 읽는 순서 오류를 발견해 수정한 뒤 위 실제 시험을 통과했다.
- 관련 로컬 테스트 26개 통과. 전체 서버 복원 완료는 아직 확인하지 않았다.
