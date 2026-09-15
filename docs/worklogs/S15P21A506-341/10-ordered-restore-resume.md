# 인덱스 우선 복원 재개

최종 상태: 2026-09-15 01:48:59 KST에 복원을 완료했다. 재개 실행은 3시간 16분 54초 걸렸다. 이후 서비스 DB 전환도 완료했다. 아래 시작/중단 기록은 당시 이력이며, 현재 결과는 [최종 결과](12-final-result.md)와 [전환 기록](11-service-cutover.md)을 따른다.

## 변경 범위와 승인

2026-09-14 사용자가 인덱스 우선 완료 → VACUUM/ANALYZE → 실제 계획 확인 → 남은 외래키/마이그레이션 순서 실행을 승인했다. 이미 COPY가 끝난 후보 DB 데이터를 보존한다. 서비스 DB 전환과 유예된 원본 전수 대조는 포함하지 않는다.

## 작업 계획

1. 동일 덤프의 schema-only 참조 DB를 이용해 완료 객체의 정의와 연결 상태를 대조하는 별도 재개 도구를 만든다. 기존 새 DB 전용 복원 가드는 유지한다.
2. 작은 독립 DB에서 부분 복원, 재개, 재실행, 정의 불일치 거부를 확인한다.
3. 기존 runner와 pg_restore worker를 종료하고 후보 DB 연결이 사라진 뒤 실제 카탈로그를 다시 확인한다. 진행 중 FK 문장만 취소되며 완료 데이터/객체는 보존한다.
4. 미완료 인덱스와 부모 연결을 먼저 완성하고 VACUUM/ANALYZE를 실행한다. 단계/객체별 결과를 남긴다.
5. 대표 날짜의 실제 FK 대조 계획과 Heap Fetches/임시 I/O를 기록한다. 개선 경로가 확인되면 남은 FK, Flyway 및 구조 검사를 진행한다. 확인되지 않으면 원인을 기록하고 멈춘다.

## 검증 기준과 위험

- status.json만으로 완료를 추측하지 않는다. 아카이브 식별과 실제 DB 객체 정의/유효성/부모 연결을 확인한다.
- parent PK의 중간 invalid 상태는 자식 연결 중에만 허용하고 FK 시작 전에는 전부 valid여야 한다.
- 기존 작업과 재개 작업이 동시에 실행되지 않아야 한다. 데이터 COPY는 재실행하지 않는다.
- 서버 PostgreSQL은 2GiB 제한이다. 메모리/worker 수를 무작정 늘리지 않는다.
- 현재 진행 중인 FK의 내부 진행은 재사용되지 않는다. 앞선 4~10시간은 가정이며 새 실측과 구분한다.
- 완료 상태도 전체 값 대조가 유예되어 RESTORED_UNVERIFIED이며 ready_for_service=false이다.

## 실제 진행 결과

- `resume_postdata.py`: 아카이브의 호스트/컨테이너 SHA, reference TOC receipt, 실제 constraint/index/attachment 정의를 비교한다. 누락 객체를 개별 실행하고 완료 시각/소요 시간을 기록한다. 이름이나 체크포인트만으로 완료를 인정하지 않는다.
- `stop_for_ordered_resume.py`: 기존 runner/transfer PID와 helper 마운트를 확인하고 종료한다. 기존 PID 종료 및 후보 DB 연결 0개를 확인한 후에만 STOPPED 기록을 남긴다.
- `finish_resumed_restore.py`: 준비 → 실제 benchmark gate → FK → 기존 동결 Flyway V2~V6 → 구조 검사로 이어진다. 대표 날짜는 첫/중간/마지막이며 양쪽 Index Only Scan, Heap Fetches=0, Sort 없음이 확인되지 않으면 NEEDS_REVIEW로 멈춘다. 전체 실행 시간제한은 없다. 대표 검사만 각각 120초로 제한한다.
- 관련 단위 테스트 38개 통과. 별도 로컬 PostgreSQL 테스트에서 200행/2개 날짜, 일부 PK만 완료된 후보를 재개했다. 준비 4.953초, FK 3.313초, 완료 재실행 1.297초. 기존 version PK OID 보존, PVS 200행 및 count 합계 10,100 보존, 완료 후 FK 삭제 변조 감지 통과. 이는 작은 기능 시험이며 전체 성능 예상의 근거로 사용하지 않는다.
- 성공 경로 시험에만 해당 로컬 테스트 DB의 `enable_seqscan=off`를 사용했다. 작은 데이터의 기본 Seq Scan 계획에서는 ready_for_fk=false가 확인됐다. 서버의 planner 설정을 강제하지 않았다.
- 기존 작업이 보유한 잠금 때문에 카탈로그 정의 조회와 pg_partition_tree 진단도 대기했다. 해당 진단만 취소하고, 중단 전 파티션 확인을 직접 pg_inherits 조회로 바꿨다. 중단 후 정의 대조는 정상 완료됐다.
- 2026-09-14 13:28:13 UTC(22:28:13 KST): 기존 PID 3728695/3729785 종료, 후보 DB 연결 0개 확인. 진행 중 FK 문장을 취소했으며 COPY는 재실행하지 않았다.
- 중단 직후: 정의 불일치/예상 밖 객체/누락 테이블 연결 모두 0개. 누락 PK 229개, 해당 인덱스 229개, 인덱스 연결 229개. FK 460개는 부모 2개와 그에 딸린 자식 458개의 카탈로그 항목 수이며, 실제 복원 명령은 부모 FK 2개이다.
- 2026-09-14 13:29:00 UTC(22:29:00 KST): 새 detached runner PID **3937096** 시작. 작업 폴더 `/home/ubuntu/service-data-migration/341/server-ordered-resume-20260914-01`. 기존 후보 DB `pickage_import_341_full_restore_3478b33b2289`를 사용한다.
- 첫 시작은 아카이브 확인 후 `no_candidate_backends`가 자동 VACUUM worker도 이전 복원 연결로 취급해 NEEDS_REVIEW로 종료됐다. 인덱스/외래키 실행 전이며 데이터 변경은 없었다. 일반 client backend만 검사하도록 수정하고, 실제 서버의 자동 VACUUM 실행 중에 수정된 가드가 통과하는 것을 확인했다. 기존 실행 코드와 실패 기록은 01 폴더에 보존했다.
- 수정한 코드는 새 `server-ordered-resume-20260914-02` 폴더에서 PID **3939296**으로 독립 실행했다. **현재 확인 대상은 02 폴더**이다. 입력 아카이브와 후보 DB, 원래 중단 receipt를 재사용하며 COPY는 반복하지 않는다.
- 마지막 시작 확인: PID 3939296 실행 중, status=RUNNING, error 없음. 아카이브 해시 확인 중이며 아직 post-data 객체 실행 전이다. 업로드한 실행 코드 4개 SHA가 로컬 코드와 일치함을 확인했다. 이후 지속 조회는 중단했다. 시험용 로컬 컨테이너만 정지하고 시험 결과 파일은 보존했다.

## 실행 당시 상태 파일과 최종 결과

새 폴더의 `server-result.json`은 전체 단계, `postdata/resume-status.json`은 객체별 실행 결과, `postdata/maintenance-status.json`은 VACUUM 대상/완료 개수, `postdata/benchmark.json`은 실제 계획이다. 이전 폴더 상태는 STOPPED_FOR_ORDERED_RESUME로 남기고 새 폴더를 가리킨다. 원본 상태 사본과 stop receipt도 새 폴더에 보존했다.

시작 확인 이후 지속적인 에이전트 폴링 없이 실행했다. 인덱스/정비/대표 계획/FK/Flyway/구조 검사와 최종 ANALYZE가 모두 끝났으며 최종 상태는 RESTORED_UNVERIFIED이다. 이는 원본 전수 값 대조를 유예했다는 뜻이다. 이후 DB가 서비스 이름 `pickage`로 변경됐으므로 이 과거 후보 이름으로 재개 실행기를 다시 실행하지 않는다.
