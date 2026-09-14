# 9번 통합 검증 사전 구현

2026-09-14 후속 진행: 8번 완료 및 develop 병합 뒤 실제 로컬 DB와 원천 기록을 대조했다.
[실제 검증 계획](04-real-integration-plan.md), [실제 검증 결과](05-real-integration-results.md)를 따른다.
아래의 DB 미접속 범위는 2026-09-12 최초 준비 단계의 기록이다.

## 변경 범위

2026-09-12 사용자가 8번 DB 성능 실험과 병렬로 9번 검증 도구 준비를 승인했다.
Jira 티켓은 아직 없으며, 같은 대화에서 사용자가 연결을 나중으로 보류했다.
작업 기준은 `065fb8eceb97ad8207fc6fd941689c96f89e9c60`, 별도 브랜치는
`codex/09-integrity-validation`이다. 8번의 미커밋 적재 코드는 가져오지 않는다.

소유 경로는 `pipeline/integrity_validation/`, 이 작업 기록 폴더뿐이다.
기존 DDL, loader, 원천/산출물, 원래 worktree의 파일·인덱스는 수정하지 않는다.

## 작업 계획

1. 서비스 5개 테이블의 현재 DDL과 시간·모집단·직접 의존성 의미를 확인한다.
2. DB 접속 기능 없이 작은 합성 입력을 메모리에서 검사하는 도구를 만든다.
3. 공통 검증 SQL, 손으로 답을 정한 fixture, 오류 주입 테스트를 준비한다.
4. JSON/Markdown 보고서와 나중에 PostgreSQL에서 실행할 SQL을 생성한다.
5. 신규 테스트·문법·변경 범위와 원래 worktree 보호 상태를 확인한다.

## 완료 기준과 미실행 범위

- 정상 fixture 통과, 중복·복합 FK 오류·누락·미래 시각·NULL/0·직접 count 오류 탐지.
- source는 선정 target 목록으로 제한하지 않고 source의 여러 버전을 각각 센다.
- `calculation_status=COMPLETE`와 `resolution_status=PARTIAL`을 분리한다.
  현 8번의 PARTIAL 계산 결과를 완전한 원천 또는 운영 게시 승인으로 바꾸지 않는다.
- 보고서에 입력 SHA와 검사별 결과, PostgreSQL 미실행 및 전체 승인 run 미검증을 남긴다.
- 대량 DB 조회, Docker/DB 연결, Spark, 운영 이관, 실제 장애 주입은 이번에 실행하지 않는다.
- 이 단계 통과는 9번 전체 완료나 서비스 공개 승인에 해당하지 않는다.

## 실제 작업과 이슈

- 저장소·활성 작업 기록 확인, 원래 worktree의 파일/인덱스 해시 기준선 저장.
- 별도 worktree 생성 완료. Jira 도구 부재와 브라우저 로그인 필요를 확인했으며
  사용자 지시에 따라 Jira 연결을 보류했다. 임의 이슈 키는 만들지 않는다.
- 세부 구현·검증 결과는 작업 완료 후 [결과 기록](results.md)에 남긴다.
- 후속 승인에 따라 native 입력 연결 코드와 작은 예제를 추가했다.
  [입력 연결 계획](02-native-input-plan.md), [입력 연결 결과](03-native-input-results.md)를 따른다.

## 기준 자료

- 원래 저장소의 로컬 작업 초안: `docs/jira/db-loading/09-integrity-performance.md`
- [서비스 DDL](../../../backend/src/main/resources/db/migration/V1__init.sql)
- [8번 결정 기록](../S15P21A506-193/06-decisions.md)
- [공통 입력 검증](../../../pipeline/postgresql/input.py)
- [스냅샷 정책](../../../pipeline/snapshot/policy.py)

로컬 `docs/jira` 초안은 이번 worktree에 복사하거나 커밋하지 않는다.
