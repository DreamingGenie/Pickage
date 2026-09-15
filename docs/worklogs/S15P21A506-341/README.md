# S15P21A506-341 — 서비스 데이터 서버 이관

리뷰 후속: [제약 이름 통일 및 날짜 파티션 생성 책임](14-constraint-names-and-partitions.md). V7은 로컬 검증 후 별도 배포 대상이며, 아래 서버 이관 기록은 V6까지 적용한 시점의 결과다.

현재 상태: **서버 복원·인덱스·외래키·V6 마이그레이션 완료 후 서비스 DB 전환을 완료했다. 원본 전수 대조는 유예했다. 운영 API 이미지에는 패키지 조회 기능이 아직 없어 최신 백엔드 배포가 남아 있다.**

서비스 DB는 `pickage`(OID 22046), 이전 DB는 `pickage_before_341_20260915`로 보존했다.
[최종 결과·실측·후속 작업](12-final-result.md)을 먼저 읽고, [커밋 파일 분류](13-commit-scope.md), [서비스 전환 및 복구](11-service-cutover.md), [재개 순서·검증](10-ordered-restore-resume.md)을 참고한다.

- 브랜치: `data/feat/S15P21A506-341-service-data-server-migration`
- [이관 계획](01-transfer-plan.md): 대상, 마이그레이션 정합성, 실험·전송·복원·검증·전환 순서
- [작업 기록](02-work-log.md): 요청 범위, 확인한 사실, 진행 결과와 미실행 항목
- [로컬 검증 결과](03-local-validation.md): 새 마이그레이션, 표본 복원과 실패 차단 검사
- [이관 도구 실행 방법](../../../scripts/service-data-migration/README.md)
- [로컬 덤프 연결 준비](04-local-dump-access.md)
- [서버 표본 결과](05-server-pilot.md): 실제 V1 이력 보존, 표본 복원, 정렬 차이 해결, 자원 측정과 한계
- [큰 표본 처리량 측정](06-large-benchmark.md): 전체 원본 규모와 덤프·전송·복원 단계별 성능
- [전체 덤프 실행](07-full-dump.md): 같은 시점의 덤프/검증값, 실행 위치·상태·실패 경계

서버에 옮길 사용자 데이터는 `package`, `version`, `snapshot`, `package_snapshot`,
`package_version_snapshot` 다섯 논리 테이블이다. 마지막 테이블의 날짜별 자식 파티션도 포함한다.
Jira 연결 키는 사용자가 만든 현재 브랜치에서 확인했으며 원격 Jira 상태는 변경하지 않았다.

- [전체 서버 복원](08-full-server-restore.md): 원본 검증 유예, 서버 전송과 별도 후보 복원, 상태 확인 방법
