# Phase 1 완료 기록 — S15P21A506-314 커뮤니티 Snapshot 저장·재시작 복원·TTL

Spec: [`../specs/S15P21A506-314.md`](../specs/S15P21A506-314.md) · 브랜치:
`api/feat/S15P21A506-314-community-snapshot-storage`

## 구현한 것

- `backend/src/main/resources/db/migration/V5__community.sql` — `community_snapshot` 테이블
  (package_id PK/FK ON DELETE CASCADE, snapshot_id UUID UNIQUE, payload_version CHECK>0,
  data_status CHECK 허용값, result JSONB CHECK object, collected_at 인덱스)
- `backend/src/main/java/com/ssafy/pickage/domain/community/`
  - `DataStatus`(enum), `CommunitySnapshotRow`(record), `CommunitySnapshotTtl`(순수 TTL 판정
    함수 — 24h fresh / 7d serve / 정리 대상)
  - `CommunitySnapshotRepository` — JdbcTemplate 기반(JPA 미사용), 269
    (`pipeline/snapshot/postgres.py`) 의 lock 기법(SET LOCAL timeout → advisory lock → 짧은
    트랜잭션)을 xact-scope·package별 키로 조정해 이식
  - `CommunitySnapshotCleanupJob`(`@Scheduled`, 매시간 최대 500행), `CommunityConfig`
    (`@EnableScheduling` + 이 도메인 전용 `ObjectMapper` 빈)
  - `CommunitySnapshotPayloadException`
  - `payload/` — `CommunityResultPayload`·`RepositoryPayload`·`TopicPayload`·
    `DiscussionStepPayload`·`MessagePayload` (저장 전용 typed record, 공개 API DTO와 별개)
- `backend/src/integrationTest/java/com/ssafy/pickage/support/DisposableTestDatabase.java` —
  269(`test_integration.py`/`test_history.py`)의 격리 DB 패턴(`pickage_<이슈번호>_test_<uuid>`,
  DROP 전 정규식 재검사)을 JDBC로 이식. 공용 `support` 패키지라 다른 도메인도 재사용 가능
- 단위 시험 9개(`CommunitySnapshotTtlTest` 6, `CommunityResultPayloadJsonTest` 4 — 리뷰 후
  회귀 시험 1개 추가), 통합 시험 10개(`CommunitySnapshotMigrationIntegrationTest` 6,
  `CommunitySnapshotRepositoryIntegrationTest` 4)

## Verify Loop 결과

- **Test**: `./gradlew clean test integrationTest` → `BUILD SUCCESSFUL`. 기존 테스트 전부
  회귀 없음(§5.0 기준선과 대조). `flyway_schema_history`로 "빈 DB 전체 migration"(매
  `DisposableTestDatabase`)과 "기존 DB upgrade"(V1~V4 있던 로컬 dev DB에 V5 추가)를 둘 다
  실제로 확인
- **Review**: `/code-review medium` — 2건 발견, 둘 다 반영
  1. (실제 버그) `CommunityConfig`의 `ObjectMapper`가 `WRITE_DATES_AS_TIMESTAMPS`를 끄지
     않아 시각 필드가 epoch 숫자로 저장될 뻔함 — 구현계획 §API "필드 규약"(UTC ISO 8601 Z)
     위반. `.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)` 추가, 회귀 시험 추가
  2. (시험 안정성) advisory lock 타임아웃 시험의 판정 창(1000~5000ms)이 CI 부하에서 흔들릴
     수 있음 — 판정 창을 넓히고(300ms~9000ms) 외부 `future.get` 타임아웃도 늘림
- **Verify(Jira 완료 판단 기준 대조)**:
  - [x] 정상·전체 요약 실패·365일 확장 결과가 재시작 후 같은 의미로 복원 —
        `upsert_후_조회하면_재시작_복원용_필드까지_전부_그대로_돌아온다`
  - [x] connection 고갈/lock 경합/statement 지연/취소된 늦은 task가 이전 결과를 덮어쓰지
        않음 — `같은_package의_advisory_lock을_이미_쥐고_있으면_2초_안에_실패한다`,
        `트랜잭션_중간_실패는_이전에_커밋된_행을_그대로_둔다`
  - [x] unsupported payload/policy는 재수집 대상, 지원 JSON 손상은 정제 구분 —
        `CommunitySnapshotPayloadException`(역직렬화 실패), CHECK 제약 시험 4개
  - [x] seed/실행 환경 의존성 미해결 시 통합 완료로 표시하지 않음 — `deploy/local/seed/*.sql`
        은 이번 Phase에서 건드리지 않았고 Spec §2에 "통합 seed gate 미통과"로 명시

## 자체 검증 중 발견해 Spec 밖에서 고친 것 (구현 중 새로 드러남)

Spec 작성 시점에는 몰랐고 구현하며 실제로 확인된 것 — "존중 기존 코드" 원칙을 코드 수준까지
끝까지 적용한 결과:

- **전역 `ObjectMapper` 빈이 프로젝트에 아예 없다.** `CommunitySnapshotRepository`가 이
  프로젝트 최초로 `ObjectMapper`를 직접 주입받는 코드였는데, 전체 앱 컨텍스트가 그 자리에서
  기동 실패했다. `CommunityConfig`에 도메인 전용 빈을 새로 정의해 해결(자세한 경위는 그
  클래스의 javadoc).
- **`org.postgresql.util.PGobject`는 컴파일 시점에 쓸 수 없다** — `build.gradle`이 postgres
  드라이버를 `runtimeOnly`로 선언해서다. `?::jsonb` SQL 캐스팅 + 표준 `setString`으로
  우회(레포지토리 javadoc 참고).
- **`pg_try_advisory_xact_lock`이 아니라 blocking `pg_advisory_xact_lock`을 써야
  `lock_timeout`이 의미가 있다** — try 버전은 timeout을 무시하고 즉시 반환한다.
- **테스트 컨텍스트에 `@EnableTransactionManagement`가 없으면 `@Transactional`이 조용히
  무시된다** — advisory lock 시험이 무한 대기하는 것으로 드러났다(고쳐서 통과).

## 남은 것 / 다음 Phase에 넘기는 것

- `payload_version` 값 계약(현재 1로 시작)과 실제 wire 계약 동결은 Phase 4(317)의 "C0" 단계를
  기다린다 — Spec §6에서 이미 열어 둔 항목
- `deploy/local/seed/*.sql` 3~5개 파일에 `community_snapshot` TRUNCATE 추가 — 인프라 경계,
  이번 Phase에서 손대지 않음
- Phase 2(213, 저장소 검증)·Phase 3(212, Issue·댓글 수집)은 이 Phase와 독립/순차로 착수 가능
  (`phases/README.md` 참고)

## 커밋 전 최종 확인

- `git diff --check` 통과 (공백/개행 문제 없음)
- 변경 파일이 Spec §2 "수정 가능 범위"를 벗어나지 않음(`domain/community/**`,
  `V5__community.sql`, 이 문서 세트만 변경)
