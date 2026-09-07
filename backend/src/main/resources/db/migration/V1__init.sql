-- 초기 스키마 (ERD 확정본).
--
-- 팀에 공유된 뒤에는 이 파일을 고치지 않는다. 고치면 체크섬이 어긋나 기동이 실패한다.
-- 변경은 새 파일(V2__…, V3__…)로만 한다.
--
-- ERD 도구가 생성한 DDL 을 그대로 둔다. 손으로 다듬으면 다음에 ERD 가 바뀌었을 때
-- 무엇이 실제 변경인지 구분이 안 된다.

CREATE TABLE "package" (
    "package_id" INT NOT NULL,
    "name" VARCHAR(300) NOT NULL,
    "repo_url" VARCHAR(200) NULL
);

CREATE TABLE "package_snapshot" (
    "package_id" INT NOT NULL,
    "snapshot_at" DATE NOT NULL,
    "downloads" BIGINT NULL,
    "stars" INT NULL,
    "open_issues" INT NULL
);

CREATE TABLE "version" (
    "version" VARCHAR(100) NOT NULL,
    "package_id" INT NOT NULL,
    "published_at" TIMESTAMP NULL,
    "ordinal" BIGINT DEFAULT 0 NOT NULL,
    "description" TEXT NULL,
    "licenses" JSON NULL,
    "deprecated" TEXT NULL,
    "dependency" JSON NULL
);

COMMENT ON COLUMN "version"."dependency"
IS '유저에게 의존성 보여주는 용도, 따로 계산할때 쓰진 않음';

CREATE TABLE "snapshot" (
    "snapshot_at" DATE DEFAULT DATE '2026-08-31' NOT NULL
);

COMMENT ON COLUMN "snapshot"."snapshot_at"
IS 'BigQuery의 snapshot 테이블 값을 기준으로 함';

CREATE TABLE "package_version_snapshot" (
    "package_id" INT NOT NULL,
    "version" VARCHAR(100) NOT NULL,
    "snapshot_at" DATE NOT NULL,
    "dependents_count" INT DEFAULT 0 NOT NULL
);

ALTER TABLE "package"
ADD CONSTRAINT "PK_PACKAGE"
PRIMARY KEY ("package_id");

ALTER TABLE "package"
ADD CONSTRAINT "UK_PACKAGE_NAME"
UNIQUE ("name");

ALTER TABLE "package_snapshot"
ADD CONSTRAINT "PK_PACKAGE_SNAPSHOT"
PRIMARY KEY ("package_id", "snapshot_at");

ALTER TABLE "version"
ADD CONSTRAINT "PK_VERSION"
PRIMARY KEY ("package_id", "version");

ALTER TABLE "snapshot"
ADD CONSTRAINT "PK_SNAPSHOT"
PRIMARY KEY ("snapshot_at");

ALTER TABLE "package_version_snapshot"
ADD CONSTRAINT "PK_PACKAGE_VERSION_SNAPSHOT"
PRIMARY KEY ("package_id", "version", "snapshot_at");

ALTER TABLE "package_snapshot"
ADD CONSTRAINT "FK_package_TO_package_snapshot_1"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id");

ALTER TABLE "package_snapshot"
ADD CONSTRAINT "FK_snapshot_TO_package_snapshot_1"
FOREIGN KEY ("snapshot_at")
REFERENCES "snapshot" ("snapshot_at");

ALTER TABLE "version"
ADD CONSTRAINT "FK_package_TO_version_1"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id");

ALTER TABLE "package_version_snapshot"
ADD CONSTRAINT "FK_version_TO_package_version_snapshot_1"
FOREIGN KEY ("package_id", "version")
REFERENCES "version" ("package_id", "version");

ALTER TABLE "package_version_snapshot"
ADD CONSTRAINT "FK_snapshot_TO_package_version_snapshot_1"
FOREIGN KEY ("snapshot_at")
REFERENCES "snapshot" ("snapshot_at");
