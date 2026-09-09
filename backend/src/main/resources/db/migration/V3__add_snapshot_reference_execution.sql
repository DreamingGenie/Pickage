-- A calendar execution has many observed snapshots, not one representative date.
ALTER TABLE public.etl_load_execution
    ALTER COLUMN snapshot_at DROP NOT NULL,
    ALTER COLUMN snapshot_timestamp DROP NOT NULL,
    ALTER COLUMN curated_run_id DROP NOT NULL,
    ADD CONSTRAINT ck_etl_execution_snapshot_scope CHECK (
        (dataset = 'snapshot-reference' AND snapshot_at IS NULL
            AND snapshot_timestamp IS NULL AND curated_run_id IS NULL)
        OR (dataset <> 'snapshot-reference' AND snapshot_at IS NOT NULL
            AND snapshot_timestamp IS NOT NULL AND curated_run_id IS NOT NULL)
    ),
    ADD CONSTRAINT uq_etl_execution_dataset UNIQUE (dataset, execution_id);

-- NULL on historical attempts means the validation contract was not recorded.
ALTER TABLE public.etl_load_attempt
    ADD COLUMN validation_contract_sha256 VARCHAR(64)
        CHECK (validation_contract_sha256 ~ '^[0-9a-f]{64}$');

CREATE TABLE public.etl_snapshot_reference (
    execution_id VARCHAR(200) NOT NULL,
    dataset VARCHAR(100) NOT NULL DEFAULT 'snapshot-reference'
        CHECK (dataset = 'snapshot-reference'),
    snapshot_at DATE NOT NULL REFERENCES public.snapshot(snapshot_at),
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    previous_snapshot_at DATE,
    interval_days INTEGER GENERATED ALWAYS AS (snapshot_at - previous_snapshot_at) STORED,
    PRIMARY KEY (execution_id, snapshot_at),
    FOREIGN KEY (dataset, execution_id)
        REFERENCES public.etl_load_execution(dataset, execution_id),
    FOREIGN KEY (execution_id, previous_snapshot_at)
        REFERENCES public.etl_snapshot_reference(execution_id, snapshot_at),
    CHECK ((snapshot_timestamp AT TIME ZONE 'UTC')::DATE = snapshot_at),
    CHECK (previous_snapshot_at IS NULL OR previous_snapshot_at < snapshot_at)
);

CREATE INDEX ix_etl_snapshot_reference_date ON public.etl_snapshot_reference(snapshot_at);

COMMENT ON TABLE public.etl_snapshot_reference IS
    'Projects 기준 목록의 실행별 날짜/원천 시각/직전 날짜 계보. 지표 준비 완료를 의미하지 않음';
COMMENT ON COLUMN public.etl_load_attempt.validation_contract_sha256 IS
    '이번 시도에서 검증한 코드·스키마 계약. 최초 게시 execution.contract_sha256은 보존';
