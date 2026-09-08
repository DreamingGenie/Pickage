CREATE TABLE public.etl_load_execution (
    execution_id VARCHAR(200) PRIMARY KEY,
    dataset VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('PREPARING','FAILED','PUBLISHED')),
    snapshot_at DATE NOT NULL,
    snapshot_timestamp TIMESTAMP NOT NULL,
    curated_run_id VARCHAR(200) NOT NULL,
    run_prefix TEXT NOT NULL,
    manifest_sha256 VARCHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    contract_sha256 VARCHAR(64) NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    input_metadata JSONB NOT NULL,
    expected_counts JSONB NOT NULL,
    actual_counts JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    active_attempt_id VARCHAR(200) NOT NULL,
    UNIQUE (dataset,execution_id,snapshot_at,manifest_sha256)
);

CREATE TABLE public.etl_load_attempt (
    attempt_id VARCHAR(200) PRIMARY KEY,
    execution_id VARCHAR(200) NOT NULL REFERENCES public.etl_load_execution(execution_id),
    status VARCHAR(20) NOT NULL CHECK (status IN ('PREPARING','FAILED','PUBLISHED','REVERIFIED')),
    phase VARCHAR(50) NOT NULL,
    actual_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    UNIQUE (execution_id,attempt_id),
    CHECK ((status='PREPARING' AND completed_at IS NULL) OR (status<>'PREPARING' AND completed_at IS NOT NULL))
);

ALTER TABLE public.etl_load_execution ADD CONSTRAINT fk_etl_active_attempt
    FOREIGN KEY (execution_id,active_attempt_id)
    REFERENCES public.etl_load_attempt(execution_id,attempt_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE public.etl_dataset_current (
    dataset VARCHAR(100) PRIMARY KEY,
    execution_id VARCHAR(200) NOT NULL,
    snapshot_at DATE NOT NULL,
    manifest_sha256 VARCHAR(64) NOT NULL,
    manifest JSONB NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (dataset,execution_id,snapshot_at,manifest_sha256)
        REFERENCES public.etl_load_execution(dataset,execution_id,snapshot_at,manifest_sha256)
);

CREATE INDEX ix_etl_load_execution_input ON public.etl_load_execution(dataset,manifest_sha256,status);
CREATE INDEX ix_etl_load_attempt_execution ON public.etl_load_attempt(execution_id,created_at);

COMMENT ON TABLE public.etl_dataset_current IS 'DB에 원자적으로 게시한 dataset별 현재 입력. MinIO _current.json과 별도';
COMMENT ON COLUMN public.etl_load_execution.snapshot_timestamp IS 'Curated report 공급자 관측 시각: 원천의 timezone 없는 마이크로초 값 보존';
