# DB 최종 반영 성능 개선 및 재시작

## 변경 범위와 계획
- 대상은 로컬 격리 실험 `C:/pg914r3`, PostgreSQL `pickage-real914-pg`뿐이다. 운영 서버는 변경하지 않는다.
- 2026-08-31 기준 Curated 23파일 준비는 완료됐지만 version 54,188,349행 UPSERT가 30분 statement timeout으로 실패했다. 중간 적재 receipt 22개는 보존되어 있다.
- 최초 적재는 빈 서비스 DB 확인 후 일반 INSERT, 주간 갱신은 값이 달라질 때만 UPDATE한다. 게시 트랜잭션 원자성과 FK 검증은 유지한다.
- 격리 DB shared_buffers 1GB, max_wal_size 8GB로 조정하고 중간 테이블 통계를 갱신한다. 실험 SQL 제한은 3시간으로 올리되 코드 기본 제한은 30분을 유지한다.
- 새 실행 파일과 이전 실행 파일의 변환 코드/DDL을 비교해 중간 결과 호환성을 검토한다. 구/신 contract, execution, manifest를 지정한 SHA 고정 proof로만 이전 receipt를 수용하며 기존 기록을 덮어쓰지 않는다.

## 검증과 실제 실행
- 실제 격리 DB에 shared_buffers=1GB, max_wal_size=8GB 적용 후 해당 컨테이너만 재시작했다. 네 staging 테이블 ANALYZE 완료. 컨테이너 4GB/2CPU 제한 유지.
- 단위 시험 17개 및 PostgreSQL 16 통합 시험 18개 통과(스킵 0). 최초/주간 게시, 변경 없는 행의 xmin 유지, 설명 변경 반영, 실패 롤백, 구 receipt 계약 보존을 확인했다.
- 첫 통합 시험에서 서비스 JSON 타입의 비교 연산 오류를 발견했다. licenses/dependency를 jsonb로 캐스팅하여 의미상 동등성을 비교하도록 수정한 뒤 전부 통과했다. 실제 DDL은 변경하지 않았다.
- 새 jar `C:/pg914r3/curated-loader-publish-20260921.jar`, SHA256 `495ec6e3436adfb2a9f74a32636c79aee27699284c31b5334a1d401cc696789d`.
- `C:/pg914r3/audit-loader-recovery.py`가 구/신 jar의 Reader 및 DDL 바이트 일치, Role/Current 바이트코드 일치, COPY·receipt 검증·해시 처리 7개 메서드 바이트코드 일치를 확인했다. 디버그 행 번호 때문에 중첩 클래스 바이너리는 달라져 bytecode로 비교했다.
- 호환성 근거: `loader-publication-compatibility.json`. 구 계약 `8bf994062ca9b4309a956ef222051b07dfb448e2b296312a6ec2f002d07b5328`, 신 계약 `4f7941b823eb3e7be03c6b94bdc854336d2bbdd5ce21ad7515f105c4ad3325cc`. 기존 receipt는 수정하지 않았다.
- proof `loader-publication-stage-reuse.json` SHA256 `0c41eb6094e825a3f9fefddca651b8d31d0ae143a7f910b873d84458e38b79cb`. 해당 baseline execution/manifest에만 적용한다. 누락/불일치 receipt는 새 계약으로 섞어서 채우지 않고 실패시킨다.
- 2026-09-21 16:44:09 KST `start-db-publication.ps1`로 백그라운드 재시작. Python PID 35776, Java PID 43404. `status.json`의 baseline:SPRING_DB_LOAD RUNNING 및 새 jar, 4GB DuckDB, proof/10800초 JVM 옵션 적용을 로그로 확인했다.
- 현재 파일 검증·COPY 변환 진행 중. 변환은 다시 수행하고 그 뒤 검증된 기존 중간 적재를 재사용한다. 실제 대규모 최종 반영 성공과 속도 개선 폭은 아직 미측정이다. baseline 성공 후 기존 실행기가 9/14 단계로 이어간다.
- 이전 status/launch/DB 로그는 `before-publication-20260921-164409-*`로 보존했다.
- 상태: `powershell -ExecutionPolicy Bypass -File C:\pg914r3\status.ps1 -Watch`
- 상세: `Get-Content C:\pg914r3\db-baseline.log -Tail 30 -Wait`
