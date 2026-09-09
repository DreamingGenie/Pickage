-- 조회 인덱스 · 유사 패키지 · 적재 추적.
--
-- 팀에 공유된 뒤에는 이 파일을 고치지 않는다. 고치면 체크섬이 어긋나 기동이 실패한다.
-- 변경은 새 파일(V3__…)로만 한다.
--
-- V1 의 다섯 테이블은 건드리지 않는다. 새 ERD 의 해당 부분이 V1 과 완전히 같아서
-- (컬럼·PK·UK·FK 전부) 옮길 것이 없다.


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


-- =========================================================================
-- 3. 적재 추적 (ETL)
-- =========================================================================
--
-- API 는 이 세 테이블을 읽지 않는다. 파이프라인이 쓰고 읽는다.
-- 그래도 Flyway 가 소유한다 — 스키마 정의가 한 곳에 있어야 로컬과 운영이
-- 구조적으로 갈라질 수 없고, `docker compose --profile api up` 한 번으로
-- 파이프라인이 붙을 DB 가 완성된다.

CREATE TABLE public.etl_load_execution (
    execution_id       VARCHAR(200) PRIMARY KEY,
    dataset            VARCHAR(100) NOT NULL,
    status             VARCHAR(20)  NOT NULL CHECK (status IN ('PREPARING','FAILED','PUBLISHED')),
    snapshot_at        DATE         NOT NULL,
    snapshot_timestamp TIMESTAMP    NOT NULL,
    curated_run_id     VARCHAR(200) NOT NULL,
    run_prefix         TEXT         NOT NULL,
    manifest_sha256    VARCHAR(64)  NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    contract_sha256    VARCHAR(64)  NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    input_metadata     JSONB        NOT NULL,
    expected_counts    JSONB        NOT NULL,
    actual_counts      JSONB,
    error_message      TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
    active_attempt_id  VARCHAR(200) NOT NULL,
    -- etl_dataset_current 의 FK 가 이 조합을 참조한다. PK 가 execution_id 하나뿐이라
    -- 나머지 세 열까지 묶어 참조하려면 이 UNIQUE 가 있어야 한다.
    UNIQUE (dataset, execution_id, snapshot_at, manifest_sha256)
);

CREATE TABLE public.etl_load_attempt (
    attempt_id     VARCHAR(200) PRIMARY KEY,
    execution_id   VARCHAR(200) NOT NULL REFERENCES public.etl_load_execution(execution_id),
    status         VARCHAR(20)  NOT NULL CHECK (status IN ('PREPARING','FAILED','PUBLISHED','REVERIFIED')),
    phase          VARCHAR(50)  NOT NULL,
    actual_counts  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    quality_report JSONB        NOT NULL DEFAULT '{}'::jsonb,
    error_message  TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
    completed_at   TIMESTAMPTZ,
    UNIQUE (execution_id, attempt_id),
    -- 진행 중이면 완료 시각이 없고, 끝났으면 반드시 있다.
    -- 두 값이 어긋난 행은 애초에 들어가지 못한다.
    CHECK ((status = 'PREPARING' AND completed_at IS NULL)
        OR (status <> 'PREPARING' AND completed_at IS NOT NULL))
);

-- ⚠ 순환 FK.
--
-- execution.active_attempt_id → attempt, attempt.execution_id → execution 이라
-- 어느 쪽을 먼저 넣어도 상대가 아직 없다. DEFERRABLE INITIALLY DEFERRED 는 검사 시점을
-- COMMIT 으로 미뤄 그 교착을 푼다.
--
-- **그래서 두 행은 같은 트랜잭션 안에서 넣어야 한다.** 파이프라인이 자동커밋으로
-- 나눠 넣으면 첫 INSERT 에서 바로 실패한다 — 이 제약을 지우지 말고 트랜잭션을 묶을 것.
ALTER TABLE public.etl_load_execution
ADD CONSTRAINT fk_etl_active_attempt
FOREIGN KEY (execution_id, active_attempt_id)
REFERENCES public.etl_load_attempt(execution_id, attempt_id)
DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE public.etl_dataset_current (
    dataset         VARCHAR(100) PRIMARY KEY,
    execution_id    VARCHAR(200) NOT NULL,
    snapshot_at     DATE         NOT NULL,
    manifest_sha256 VARCHAR(64)  NOT NULL,
    manifest        JSONB        NOT NULL,
    published_at    TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (dataset, execution_id, snapshot_at, manifest_sha256)
        REFERENCES public.etl_load_execution(dataset, execution_id, snapshot_at, manifest_sha256)
);

-- 같은 입력(manifest)이 이미 적재됐는지 확인하는 경로.
CREATE INDEX ix_etl_load_execution_input
    ON public.etl_load_execution(dataset, manifest_sha256, status);

-- 한 실행의 시도 이력을 시간 순으로 훑는 경로.
CREATE INDEX ix_etl_load_attempt_execution
    ON public.etl_load_attempt(execution_id, created_at);

COMMENT ON TABLE public.etl_dataset_current
IS 'DB에 원자적으로 게시한 dataset별 현재 입력. MinIO _current.json과 별도';

-- ⚠ 시간대 없음이 의도다.
--
-- 원천이 timezone 없는 마이크로초 값을 주므로 그대로 보존한다.
-- version.published_at 도 같은 TIMESTAMP 타입이지만 **규칙이 다르다** —
-- 그쪽은 API 가 ISO 8601 UTC 로 내보내야 하는 값이다(명세 0.5). 둘을 같은
-- 변환 규칙으로 다루면 안 된다.
COMMENT ON COLUMN public.etl_load_execution.snapshot_timestamp
IS 'Curated report 공급자 관측 시각: 원천의 timezone 없는 마이크로초 값 보존';
