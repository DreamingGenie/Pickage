-- Durable staging for the Spring Curated publisher.  A staged file can be
-- reused after a process failure; service tables are changed only by the final
-- publication transaction.
CREATE TABLE public.etl_curated_stage_package (
    execution_id VARCHAR(200) NOT NULL,
    package_id INT NOT NULL,
    name VARCHAR(300) NOT NULL,
    repo_url VARCHAR(200),
    PRIMARY KEY (execution_id, package_id)
);

CREATE TABLE public.etl_curated_stage_version (
    execution_id VARCHAR(200) NOT NULL,
    version VARCHAR(100) NOT NULL,
    package_id INT NOT NULL,
    published_at TIMESTAMP,
    ordinal BIGINT NOT NULL,
    description TEXT,
    licenses JSONB,
    deprecated TEXT,
    dependency JSONB NOT NULL,
    PRIMARY KEY (execution_id, package_id, version)
);

CREATE TABLE public.etl_curated_stage_package_snapshot (
    execution_id VARCHAR(200) NOT NULL,
    package_id INT NOT NULL,
    snapshot_at DATE NOT NULL,
    downloads BIGINT,
    stars INT,
    open_issues INT,
    PRIMARY KEY (execution_id, package_id, snapshot_at)
);

CREATE TABLE public.etl_curated_stage_version_snapshot (
    execution_id VARCHAR(200) NOT NULL,
    package_id INT NOT NULL,
    version VARCHAR(100) NOT NULL,
    snapshot_at DATE NOT NULL,
    dependents_count INT NOT NULL CHECK (dependents_count >= 0),
    PRIMARY KEY (execution_id, package_id, version, snapshot_at)
);

CREATE TABLE public.etl_curated_load_file_receipt (
    execution_id VARCHAR(200) NOT NULL,
    role VARCHAR(40) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    contract_sha256 VARCHAR(64) NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot_at DATE NOT NULL,
    source_rows BIGINT NOT NULL CHECK (source_rows >= 0),
    loaded_rows BIGINT NOT NULL CHECK (loaded_rows >= 0),
    excluded_rows BIGINT NOT NULL CHECK (excluded_rows >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (execution_id, role, source_sha256)
);

CREATE INDEX ix_etl_curated_stage_package_execution
    ON public.etl_curated_stage_package(execution_id);
CREATE INDEX ix_etl_curated_stage_version_execution
    ON public.etl_curated_stage_version(execution_id);
