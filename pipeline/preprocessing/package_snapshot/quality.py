"""Shared quality schema and read-only adapters for immutable pre-v2 artifacts."""
from __future__ import annotations

from pipeline.preprocessing.package_snapshot.quality_schema import COMMON_SCHEMA, DOWNLOAD_FIELDS, HISTORY_FIELDS, LEGACY_HISTORY_SCHEMA, LEGACY_OBSERVED_SCHEMA, QUALITY_SCHEMA, QUALITY_SCHEMA_ID, SELECTION_FIELDS, history_quality_projection, require_schema


def normalize_quality(con, manifest, *, producer):
    """Expose v2 columns, selecting legacy format by explicit loader and exact schema."""
    if producer not in ("observed", "history"):
        raise ValueError("unknown quality producer")
    expected = QUALITY_SCHEMA
    marker = manifest.get("quality_schema")
    if marker == QUALITY_SCHEMA_ID:
        require_schema(con, "quality_raw", expected)
        con.execute("CREATE TEMP VIEW quality AS SELECT * FROM quality_raw")
    elif marker is not None:
        raise ValueError("unsupported quality schema version")
    elif producer == "observed":
        require_schema(con, "quality_raw", LEGACY_OBSERVED_SCHEMA)
        con.execute("CREATE TEMP VIEW quality AS SELECT q.*,s.stars,s.open_issues,"
                    "NULL::TIMESTAMPTZ first_published_at,NULL::TIMESTAMPTZ selected_published_at "
                    "FROM quality_raw q LEFT JOIN package_snapshot s USING(package_id)")
    else:
        history_quality_projection(con, manifest["interval"])
    require_schema(con, "quality", expected)


def validate_quality(con, manifest, *, producer):
    """Both loaders enforce identical common-field meaning after normalization."""
    if producer not in ("observed", "history"):
        raise ValueError("unknown quality producer")
    instant = manifest["interval"]["snapshot_timestamp"]
    invalid = con.execute("""SELECT EXISTS(
        SELECT 1 FROM package_snapshot s
        FULL JOIN quality q USING(package_id)
        FULL JOIN package_identity p ON p.package_id=coalesce(s.package_id,q.package_id)
        WHERE s.package_id IS NULL OR q.package_id IS NULL OR p.package_id IS NULL
          OR q.name IS DISTINCT FROM p.name
          OR q.snapshot_at IS DISTINCT FROM s.snapshot_at
          OR q.snapshot_at IS DISTINCT FROM ?::DATE
          OR ROW(q.download_sum,q.stars,q.open_issues)
             IS DISTINCT FROM ROW(s.downloads,s.stars,s.open_issues)
          OR q.download_sum<0 OR q.stars<0 OR q.open_issues<0
          OR q.observed_days IS NULL OR q.valid_days IS NULL
          OR q.observed_days<0 OR q.valid_days<0 OR q.valid_days>q.observed_days
          OR q.expected_days<0 OR q.observed_days>q.expected_days
          OR q.quality_reasons IS NULL
          OR (q.download_sum IS NULL) IS DISTINCT FROM (q.valid_days=0)
          OR (q.null_reason IS NOT NULL) IS DISTINCT FROM (q.valid_days=0)
          OR q.data_status IS DISTINCT FROM CASE WHEN q.valid_days=0 THEN 'UNAVAILABLE'
             WHEN q.valid_days=q.expected_days THEN 'COMPLETE' ELSE 'PARTIAL' END
          OR (q.expected_days IS NULL AND (q.observed_days<>0 OR q.valid_days<>0
              OR q.null_reason IS DISTINCT FROM 'NO_PREVIOUS_SNAPSHOT'))
          OR q.repository_reason IS NULL OR q.repository_reason NOT IN
             ('SELECTED','NO_VALID_REPOSITORY','NO_EXACT_OBSERVATION',
              'PROJECT_METRIC_CONFLICT','INVALID_METRIC_VALUE')
          OR q.repository_mapping_status IS DISTINCT FROM
             CASE WHEN q.repository_repo_url IS NULL THEN 'NO_SELECTED_REPOSITORY'
                  WHEN q.repository_observed_timestamp IS NULL THEN 'NO_EXACT_PROVIDER_PATH_MATCH'
                  ELSE 'MATCHED' END
          OR (q.repository_reason='SELECTED' AND
              (q.repository_repo_url IS NULL OR q.repository_observed_timestamp IS NULL))
          OR (q.repository_reason='NO_VALID_REPOSITORY' AND q.repository_repo_url IS NOT NULL)
          OR (q.repository_reason='NO_EXACT_OBSERVATION' AND
              (q.repository_repo_url IS NULL OR q.repository_observed_timestamp IS NOT NULL))
          OR (q.repository_reason<>'SELECTED' AND (q.stars IS NOT NULL OR q.open_issues IS NOT NULL))
          OR q.repository_snapshot IS DISTINCT FROM CAST(q.snapshot_at AS VARCHAR)
          OR try_cast(q.repository_snapshot_timestamp AS TIMESTAMPTZ) IS DISTINCT FROM ?::TIMESTAMPTZ
          OR (q.repository_observed_timestamp IS NOT NULL
              AND q.repository_observed_timestamp<>?::TIMESTAMPTZ)
          OR (? AND (q.first_published_at IS NOT NULL OR q.selected_published_at IS NOT NULL))
    )""", [manifest["snapshot"], instant, instant, producer == "observed"]).fetchone()[0]
    if invalid:
        raise ValueError("service and quality values disagree with common contract")
