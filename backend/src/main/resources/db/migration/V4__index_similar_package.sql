-- 조회 인덱스 · 유사 패키지.
--
-- 팀에 공유된 뒤에는 이 파일을 고치지 않는다. 고치면 체크섬이 어긋나 기동이 실패한다.
-- 변경은 새 파일(V5__…)로만 한다.
--
-- V1 의 다섯 테이블은 건드리지 않는다. 새 ERD 의 해당 부분이 V1 과 완전히 같아서
-- (컬럼·PK·UK·FK 전부) 옮길 것이 없다.
--
--
-- ⚠ 이 파일은 V2__index_similar_etl.sql 을 대체한다 (S15P21A506-289).
--
-- 그 파일은 277 브랜치가 develop 을 머지해 오면서 **버전 2 를 두 번 쓰게 됐다** —
-- 267 의 V2__add_curated_load_execution.sql 과 같은 번호다. Flyway 는 같은 버전이 둘이면
-- 기동을 거부하므로 백엔드가 아예 뜨지 않았다.
--
-- 번호만 바꾸는 것으로는 풀리지 않았다. 두 파일이 **똑같이 etl_load_execution 을 만들어서**
-- 뒤에 붙는 쪽이 "relation already exists" 로 죽는다. 그래서 ETL 3종은 이 파일에서 통째로
-- 걷어냈다 — 이미 V2(267) 가 만들고 V3(269) 가 고쳐 둔 것이라 여기서 다시 만들 이유가 없고,
-- V3 의 변경(스냅샷 3열 NULL 허용·etl_snapshot_reference·validation_contract_sha256)까지
-- 되돌리게 된다.
--
-- 인덱스와 similar_package 만 남았다. 원래 파일의 판단은 그대로 옮겼다.


-- =========================================================================
-- 1. 조회 인덱스 (API 명세 §8)
-- =========================================================================
--
-- V1 에는 인덱스가 하나도 없었다. 시드 데이터로는 전부 순차 스캔이라 티가 안 나고,
-- 실제 규모로 적재한 뒤에야 느려진다.
--
-- 만들지 않는 것도 적어 둔다 — 나중에 "왜 없지" 하고 다시 추가하지 않도록:
--   * package(name)                     → UK_PACKAGE_NAME 이 이미 커버한다.
--                                          `= ANY(:names)` 도 이 인덱스를 그대로 쓴다.
--   * package_snapshot(package_id, …)   → PK (package_id, snapshot_at) 가 추이 조회를
--                                          그대로 커버한다.

-- 자동완성 폴백(§2.4)용.
--
-- **이 인덱스가 없으면 자동완성이 동작하지 않는다** — 기본 collation 에서
-- `LIKE 'q%'` 는 일반 B-tree 인덱스를 타지 않는다. UK_PACKAGE_NAME 이 있어도 소용없다.
-- text_pattern_ops 는 문자열을 바이트 순으로 비교하는 연산자 클래스라 접두사 검색이
-- 범위 스캔이 된다.
--
-- 그래서 중간 일치(`LIKE '%q%'`)는 v1 범위 밖이다. 그렇게 바꾸면 이 인덱스가 죽는다.
CREATE INDEX idx_package_name_prefix
    ON "package" ("name" text_pattern_ops);

-- 최신 버전 찾기(§3 latest_ver CTE)용.
--
-- 정렬 기준이 ordinal 인 것이 핵심이다(명세 0.6). 문자열로 정렬하면 4.9.0 이 4.19.2 보다
-- 뒤로 가고, 그 실수는 화면에 "최신 버전 4.9.0" 으로 조용히 나타난다.
-- DESC 로 만들어 두면 DISTINCT ON … ORDER BY ordinal DESC 가 역방향 스캔 없이 끝난다.
CREATE INDEX idx_version_pkg_ordinal
    ON "version" ("package_id", "ordinal" DESC);

-- 의존 수 추이(§5)·버전 분포(§6)용.
--
-- PK 가 (package_id, version, snapshot_at) 라서 snapshot_at 으로 자르는 조회를 못 탄다.
-- 두 번째 열이 version 이라 범위 조건이 거기서 끊긴다.
CREATE INDEX idx_pvs_pkg_snapshot
    ON "package_version_snapshot" ("package_id", "snapshot_at");


-- =========================================================================
-- 2. 유사 패키지 (기능-03 · UC4)
-- =========================================================================
--
-- API 명세는 UC4 를 "다음 단계"로 두었다(임베딩 파이프라인이 선행 조건).
-- 테이블만 먼저 만든다 — 조회 경로가 아직 없으므로 비어 있어도 무해하고,
-- 스키마를 ERD 와 맞춰 두면 파이프라인 쪽이 먼저 적재를 시작할 수 있다.
--
-- 요청 경로에 모델이 없다는 것이 이 테이블의 존재 이유다. 미리 계산해 두고
-- 조회는 DB 한 번으로 끝낸다.

CREATE TABLE "similar_package" (
    "package_id"         INT NOT NULL,
    "similar_package_id" INT NOT NULL,
    "rank"               INT NOT NULL,
    "score"              DOUBLE PRECISION NOT NULL,
    "model_ver"          VARCHAR(50) NOT NULL
);

COMMENT ON COLUMN "similar_package"."rank"      IS '순위';
COMMENT ON COLUMN "similar_package"."score"     IS '종합 점수(유사도+기타)';
COMMENT ON COLUMN "similar_package"."model_ver" IS '판정 모델 버전';

ALTER TABLE "similar_package"
ADD CONSTRAINT "PK_SIMILAR_PACKAGE"
PRIMARY KEY ("package_id", "similar_package_id");

-- 한 패키지 안에서 순위가 겹치지 않는다. 겹치면 목록 순서가 비결정적이 된다.
ALTER TABLE "similar_package"
ADD CONSTRAINT "UK_SIMILAR_PACKAGE_RANK"
UNIQUE ("package_id", "rank");

ALTER TABLE "similar_package"
ADD CONSTRAINT "FK_PACKAGE_SIMILAR_PACKAGE"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id");

ALTER TABLE "similar_package"
ADD CONSTRAINT "FK_PACKAGE_SIMILAR_PACKAGE_CANDIDATE"
FOREIGN KEY ("similar_package_id")
REFERENCES "package" ("package_id");

-- 자기 자신은 후보가 아니다. 임베딩 유사도는 자기 자신에서 항상 1.0 이 나오므로
-- 거르지 않으면 모든 목록의 1위가 자기 자신이 된다.
ALTER TABLE "similar_package"
ADD CONSTRAINT "CK_SIMILAR_PACKAGE_SELF"
CHECK ("package_id" <> "similar_package_id");

ALTER TABLE "similar_package"
ADD CONSTRAINT "CK_SIMILAR_PACKAGE_RANK"
CHECK ("rank" BETWEEN 1 AND 50);
