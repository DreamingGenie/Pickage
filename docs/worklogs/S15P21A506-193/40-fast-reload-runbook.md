# 40. 나중에 전체 재적재 시작하기

2026-09-13 09:46 KST 서비스 전환 완료: 새 부모는 `public.package_version_snapshot`이다.
이 문서의 기존 Check/Start/Resume은 전환 전 계약용이므로 현재 대상에 재실행하지 않는다.
[44 전환·복구 기록](44-service-table-cutover.md)을 현재 상태의 기준으로 사용한다.

2026-09-13 02:28 KST 완료: 229일/1,007,084,608행을 2시간 30분 28초에 적재·검증했다.
현재 실행은 종료되었으며 서비스 테이블 전환은 하지 않았다. 아래 시작·중단 안내는 실행 절차 기록이다.

2026-09-12 23:58 KST 갱신: 사용자 요청으로 이전 private 19일 데이터를 초기화하고 전체 시간 측정 실행을 새로 시작했다.
기본 config 위치는 유지하되 현재 `data/vd-db-reload-timed-20260912-2354/job/`을 가리킨다.
따라서 아래 기본 Status/Stop/Resume은 새 실행을 대상으로 한다. 이전 job 로그는 보존된 과거 기록이다.
현재 시간 기록과 실제 상태의 기준은 [42 전체 시간 측정](42-timed-full-reload.md)이다. 실행 중 Start를 다시 호출하지 않는다.

## 준비된 대상

- 원본: `data/vd-full-20260912-01/run`의 검증된 Parquet. 재집계하지 않는다.
- 전체 229일 / 1,007,084,608행. 기존에 넣은 43일도 새 대상에 다시 넣는다.
- 로컬 PostgreSQL: `pickage-267-validation` / `pickage_267_full_defaulted`.
- 새 대상: `vd193_reload_20260912_ready01.package_version_snapshot`.
- 설정: `data/vd-db-reload-ready-20260912-01/config.json`과 `prepared-plan.json`.
- 실행 기록: `data/vd-db-reload-ready-20260912-01/job/`.

기존 `public.package_version_snapshot`, 기존 43일 이력, 이전 재개 코드와 Parquet는 보존한다.
새 적재의 execution/attempt/current도 같은 새 schema에 기록한다.
최종 `READY_FOR_CUTOVER`는 **새 대상 전체 적재와 검증 완료**이며 서비스 테이블 교체 완료가 아니다.
`PILOT_VERIFIED`는 선정 날짜만 시험한 결과다.

## 명령

저장소의 PowerShell에서 사용한다. 명시적 `Start` 또는 `Resume`만 DB 적재를 실행한다.
인수를 생략하면 `Check`이며 전체 적재를 시작하지 않는다.

```powershell
# 시작 전 점검만 실행: 원본, 전체 키, DB 실체, 계약, 디스크, 기존 완료 상태
.\scripts\version-dependents-reload.ps1 -Action Check

# 전체 적재 시작: 백그라운드 실행, 전체 고정 시간 제한 없음
.\scripts\version-dependents-reload.ps1 -Action Start

# 실행 중 상황: 로컬 진행 기록만 읽으며 DB 계산을 방해하지 않음
.\scripts\version-dependents-reload.ps1 -Action Status

# 현재 날짜가 끝난 뒤 중단 요청
.\scripts\version-dependents-reload.ps1 -Action Stop

# 이동/재부팅/실패 후 재개: 중단 요청을 해제하고 완료 날짜부터 검증
.\scripts\version-dependents-reload.ps1 -Action Resume
```

시작 명령은 별도 창을 띄우지 않고 Python 프로세스를 실행한다. 채팅을 열어 둘 필요는 없다.
Python 경로 기본값은 현재 노트북의 `C:\Users\SSAFY\miniforge3\python.exe`다.
Docker Desktop과 PostgreSQL 컨테이너가 실행되어 있어야 한다.
실행 중 Windows의 자동 절전 진입을 억제하지만 재부팅·강제 종료·최대 절전까지 막는 기능은 아니다.

## 상태와 재개 의미

- `PREPARE_DATE`, `DATE_VERIFIED`: 현재 날짜, 검증된 날짜 수/행 수, 전체 날짜 수/행 수를 표시한다.
- `heartbeat.json`: 프로세스가 살아 있으면 30초마다 시각을 갱신한다. 계산량이 증가했다는 증명과는 다르다.
- `STOPPED`: 날짜 경계에서 요청대로 중단. 현재 날짜 처리 중 요청하면 그 날짜가 끝나기를 기다린다.
- `PAUSED_RESOURCE_LOW`: 다음 날짜 시작 전 디스크 여유가 설정 기준보다 작아져 멈춤.
- `FAILED`: 로그의 오류를 해결한 뒤 같은 설정으로 재개한다.
- `READY_FOR_CUTOVER`: 모든 날짜와 행 수·값·제약·실행 이력·최신 포인터 검증 완료.

Status는 **저장된 진행 기록**을 읽는다. 재부팅 후 예전 RUNNING 단계가 남을 수 있으므로 heartbeat 시각과 프로세스 상태를 함께 본다. Check는 DB까지 실제 검사하며 적재가 실행 중이면 중복 실행 잠금 때문에 거부된다.

하루 내부 실패는 해당 날짜를 rollback한다. 완료 날짜는 원본에서 입력을 다시 준비해 DB 값과 대조하며 다시 INSERT하지 않는다. 재개에는 이미 완료한 날짜를 검증하는 시간이 추가된다.
재부팅 후에도 운영체제 잠금은 해제된다. 이전 PID가 다른 프로세스에 재사용된 경우에는 시작 시각을 함께 확인하여 오인하지 않는다.

## 고정한 내용과 보존 규칙

- 입력 run manifest SHA, 생성/검증 코드 SHA, 날짜별 예상 행 수, DB 클러스터 ID·DB명과 새 schema를 고정했다.
- 코드나 입력이 바뀌면 자동으로 현재 해시를 덮어써서 재사용하지 않는다. 기존 실행과 변경 호환성을 검토하고 격리 검증 후 새 계획을 준비한다.
- 기존 중단 작업은 `data/vd-db-full-20260912-01`이다. 그곳의 `resume.ps1`은 이전 적재 방식이므로 이번 빠른 재적재 시작에는 사용하지 않는다.
- 날짜마다 일반 테이블에 COPY한 뒤 PK/FK를 만들고 검증해 날짜별 partition으로 연결한다. 제약을 없애거나 서비스의 원래 열 계약을 완화하지 않는다.
- 전역 입력과 키는 실행마다 한 번 준비한다. 개별 날짜의 TSV는 날짜별로 만들며 전체 관계를 다시 계산하지 않는다.
- 현재 최소 디스크 여유 기준은 호스트와 DB 데이터 파일시스템 각각 200GiB다. 자원 부족 시 다음 날짜 시작 전에 멈춘다.
- 최종 검사는 모든 날짜별 DB 행 수도 다시 읽는다. 진행 중 Status에는 이 비용이 없지만, 마지막 검증 시간은 전체 소요 시간에 포함해야 한다.

## 전체 적재 완료 후 서비스 전환

이번 시작 명령은 public 테이블을 삭제·이름 변경하지 않는다. 전체 결과가 만들어진 후 다음 전환 작업을 별도로 수행한다.

1. READY 보고서와 실제 새 대상의 229일/총행 수 및 원본 계약을 확인한다.
2. 기존 테이블의 외부 FK·뷰·함수·권한·소유자·API 조회와 실행 이력 연결을 조사한다. 테이블 이름만 바꾸면 기존 OID를 참조하는 객체가 자동으로 새 테이블을 바라보지 않는다.
3. 기존 데이터와 다른 쓰기 작업을 보존하는 전환 SQL 및 복구 SQL을 격리 환경에서 검증한다.
4. 필요한 짧은 쓰기 중단 구간에서 테이블과 관련 게시 이력을 함께 전환하고, 통계 갱신·서비스 조회를 확인한다.
5. 이전 테이블은 복구 가능하도록 보관하고, 제거는 별도 판단한다.

전환은 전체 적재를 시작하기 위한 선행 조건이 아니다. 현재 준비된 시작 명령으로 새 DB 대상 전체를 먼저 만들 수 있다.
