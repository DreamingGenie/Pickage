-- 커뮤니티 현황 결과 저장 (S15P21A506-314).
--
-- 팀에 공유된 뒤에는 이 파일을 고치지 않는다. 변경은 새 파일(V6__…)로만 한다.
--
-- package당 최신 결과 1행만 보관한다(구현계획 §데이터베이스 "저장 구조 결정"). 이슈·메시지를
-- 별도 관계형 테이블로 쪼개지 않는다 — 화면은 이 결과를 통째로 읽고 통째로 교체하는 7일짜리
-- 조회 자료이지, 이슈별 검색이나 장기 이력 분석용 원천 데이터가 아니다.
--
-- fresh_until·serve_until·요약 통계·표시 역할 같은 계산 가능한 값은 컬럼으로 만들지 않는다
-- (구현계획 §"컬럼으로 만들지 않는 값") — collected_at과 설정값으로 조회 시점에 계산한다.

CREATE TABLE "community_snapshot" (
    "package_id"      INT NOT NULL,
    "snapshot_id"     UUID NOT NULL,
    "payload_version" SMALLINT NOT NULL,
    "collected_at"    TIMESTAMPTZ NOT NULL,
    "data_status"     VARCHAR(30) NOT NULL,
    "result"          JSONB NOT NULL
);

COMMENT ON COLUMN "community_snapshot"."package_id" IS
    '패키지당 최신 결과 한 행만 보관한다(PK). package 삭제 시 함께 지운다';
COMMENT ON COLUMN "community_snapshot"."snapshot_id" IS
    '응답 버전 식별과 동시 갱신 결과 구분용. 원문·source ID는 여기 넣지 않는다';
COMMENT ON COLUMN "community_snapshot"."payload_version" IS
    '배포 후 오래된 result JSON 형식을 안전하게 판별한다. 1부터 시작';
COMMENT ON COLUMN "community_snapshot"."collected_at" IS
    '24시간 재사용·7일 제공·매시간 정리 배치 판정의 유일한 기준 시각';
COMMENT ON COLUMN "community_snapshot"."data_status" IS
    'AVAILABLE·PARTIAL·UNVERIFIED_REPOSITORY·AMBIGUOUS_SCOPE·UNSUPPORTED_HOST·NO_DISCUSSION_DATA 중 하나. 일시적 외부 호출 실패·진행 중 상태는 이 테이블에 저장하지 않는다';
COMMENT ON COLUMN "community_snapshot"."result" IS
    '검증된 저장소 식별자·이슈 최대 2개·논의 흐름·대표 메시지·제한 사유. 원문 본문·댓글·prompt·hash는 넣지 않는다';

-- =========================================================================
-- PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK
-- =========================================================================
-- 명명 규칙은 V1__init.sql·V4__index_similar_package.sql 그대로 따른다.

ALTER TABLE "community_snapshot"
ADD CONSTRAINT "PK_COMMUNITY_SNAPSHOT"
PRIMARY KEY ("package_id");

ALTER TABLE "community_snapshot"
ADD CONSTRAINT "UK_COMMUNITY_SNAPSHOT_SNAPSHOT_ID"
UNIQUE ("snapshot_id");

ALTER TABLE "community_snapshot"
ADD CONSTRAINT "FK_PACKAGE_COMMUNITY_SNAPSHOT"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id")
ON DELETE CASCADE;

ALTER TABLE "community_snapshot"
ADD CONSTRAINT "CK_COMMUNITY_SNAPSHOT_PAYLOAD_VERSION"
CHECK ("payload_version" > 0);

ALTER TABLE "community_snapshot"
ADD CONSTRAINT "CK_COMMUNITY_SNAPSHOT_DATA_STATUS"
CHECK ("data_status" IN (
    'AVAILABLE', 'PARTIAL', 'UNVERIFIED_REPOSITORY',
    'AMBIGUOUS_SCOPE', 'UNSUPPORTED_HOST', 'NO_DISCUSSION_DATA'
));

-- jsonb_typeof 로 최상위 형태만 강제한다. 내부 필드 스키마·배열 상한·문자열 길이는
-- 저장 전 애플리케이션의 typed payload DTO(Jackson)가 검증한다 — DB CHECK로는 표현할 수 없다.
ALTER TABLE "community_snapshot"
ADD CONSTRAINT "CK_COMMUNITY_SNAPSHOT_RESULT_OBJECT"
CHECK (jsonb_typeof("result") = 'object');

-- 24h 재사용·7d 제공 판정과 매시간 정리 배치(WHERE collected_at < ?)가 이 인덱스를 탄다.
CREATE INDEX idx_community_snapshot_collected_at
    ON "community_snapshot" ("collected_at");
