# 로컬 파이프라인 개선 최종 검증 — 2026-09-24

## 요구사항별 결과

| 요구사항 | 확인한 증거 | 결과 |
| --- | --- | --- |
| 실제 Raw → Curated 생성 및 MinIO 게시 | C:/pgb6/final-curated-proof.json: 전체 stage 파일 GET/SHA 검증, frozen source 불변, bundle 82b66503…351bc277 | 통과. 완료된 앞 단계와 명시적 복구 receipt를 연결한 실행이며 처음부터 다시 실행한 소요 시간으로 보고하지 않음 |
| 실제 PostgreSQL 적재 성공 | C:/pgb7/baseline-verification.json, weekly-verification.json, live SQL: b831r3/w914b3 PUBLISHED 및 actual=expected, current9/14 | 통과. 새 빈 DB bootstrap → fsync on 재시작 → weekly |
| 메모리 초과 방지 | 실제 전처리/loader 종료0, OOMKilled=false, 제한된 container/JVM/DuckDB; bootstrap TSV64MiB 묶음 | 통과한 실제 입력의 근거. 모든 미래 입력의 성공을 보장하는 의미 아님 |
| 처리 공간50GB 이하 | 공통 cap28GB+17GB+4GB+로그예약0.5GB=49.5GB. 역할별 한 개 volume/container 계약과 role 위조·상한 초과·실제 ENOSPC 시험 | 통과. 실제 전처리 연계 실행 표본27.53GB, 두 보존DB를 포함한 재적재 표본22.34GB. 영구 raw/최종 결과 제외 |
| 작업 후 임시 공간 정리 | baseline/weekly scratch.ext4 부재를 read-only mount에서 재확인; live staging65536bytes. 전처리 scratch 제거 증거/fixture cleanup | 통과. PostgreSQL 정상 복구에 필요한 WAL은 삭제 대상 아님 |
| 실패/재시도 정합성 | PostgreSQL 통합27개 PASS: 중복/FK/날짜/parent/NULL/rollback,256byte분할 결과 oracle 일치/즉시 삭제/예외콜백1회 | 통과. 최초 bootstrap 실패는 전체 rollback 후 처음부터 재시작 |
| 중요한 기존 데이터 보존 | 기존15441 성공 DB·원본 MinIO·legacy volume 보존; 별도15442 최종 검증DB; 원래worktree preexisting untracked3개만 유지 | 통과. 실패 evidence도 보존 |
| 서버에 올리기 위한 준비 | bounded runtime Dockerfiles/배포절차/DB staging 설정, 기존curated-dispatch Compose 연결, Linux dispatcher24 tests PASS | 로컬 준비 완료. 실제 서버 적용은 요청대로 실행하지 않음 |
| 기존 모니터링 유지 | deploy 변경은 data/compose.yaml만, timer/수집설정 변경 없음. PIPELINE_RESOURCES 60초/완료·실패/SQL단계/DB_RESULT stdout, 기존MinIO상태경로 유지 | 로컬 연결 검증. 서버 대시보드에서 표시되는지는 서버 반영 때 확인 |
| develop 충돌 검사 | C:/pgb6/develop-compat-final.json; origin/develop29153b3…8c97, 임시index merge-tree | 검사 완료. 아래5개 충돌 있음. 실제 HEAD/index/브랜치 병합 없음 |

## 최종 실제 적재 결과

- 8/31 초기 적재: 3시간49분6초. 9/14 weekly:25분3초. 검증 포함 합계4시간15분3초.
- 최종 package11,323,796 / version55,026,921.
- 9/14 package_snapshot11,312,204 / package_version_snapshot7,935,685 / dependents NULL0.
- DB 처리 영역 표본 최고14,783,070,208bytes(17GB cap), loader388,112,384bytes(4GB cap).
- 성공 JAR SHA256:5f22a6b3ff491c6932d90cc672666afbe38393fa3106dca924e250924bbd6d29. 현재145개 소스/설정 해시가 빌드 proof와 일치.
- 원천부터 단계별 실제 실행·게시 성공과 새 DB 전체 재생을 조합해 검증했다. 최신 코드로 전체 raw를 처음부터 끝까지 재실행한 단일 시간 기록은 아니다.

## 병합 때 해결할 충돌

- deploy/prod/README.md
- pipeline/minio/README.md
- pipeline/preprocessing/package_snapshot/README.md
- develop의 pipeline/package_snapshot/downloads_reload.py: 이동된 preprocessing 경로에 배치 필요
- develop의 pipeline/package_snapshot/test_downloads_reload.py: 같은 경로 이동 필요

요청한 로컬 개선·실제 성공 검증은 완료했다. 커밋/실제 병합/서버 배포는 하지 않았다. 서버용 자격증명·volume 이전·dashboard 실표시는 서버 반영 작업의 검증 범위다.
