# S15P21A506-341 — 서비스 데이터 서버 이관

현재 상태: **로컬 구현·작은 실제 데이터 검증 완료. 전체 덤프·전송·서버 변경 미실행.**

- 브랜치: `data/feat/S15P21A506-341-service-data-server-migration`
- [이관 계획](01-transfer-plan.md): 대상, 마이그레이션 정합성, 실험·전송·복원·검증·전환 순서
- [작업 기록](02-work-log.md): 요청 범위, 확인한 사실, 진행 결과와 미실행 항목
- [로컬 검증 결과](03-local-validation.md): 새 마이그레이션, 표본 복원과 실패 차단 검사
- [이관 도구 실행 방법](../../../scripts/service-data-migration/README.md)

서버에 옮길 사용자 데이터는 `package`, `version`, `snapshot`, `package_snapshot`,
`package_version_snapshot` 다섯 논리 테이블이다. 마지막 테이블의 날짜별 자식 파티션도 포함한다.
Jira 연결 키는 사용자가 만든 현재 브랜치에서 확인했으며 원격 Jira 상태는 변경하지 않았다.
