"""Database independent SQL checks for the validation run.

The statements intentionally contain no connection or execution code.  A
runner may execute each statement against PostgreSQL or DuckDB after creating
the schemas described by :mod:`schema`.
"""

from __future__ import annotations


def _check(identifier: str, description: str, sql: str) -> dict[str, str]:
    return {"id": identifier, "description": description, "sql": sql.strip()}


CHECKS = (
    _check("package_identity", "package의 필수 식별자·이름·길이와 PK/UK 중복을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.package p
        WHERE p.package_id IS NULL OR p.package_id <= 0
           OR p.name IS NULL OR TRIM(p.name) = '' OR LENGTH(p.name) > 300
           OR LENGTH(p.repo_url) > 200
           OR EXISTS (SELECT 1 FROM public.package x GROUP BY x.package_id HAVING COUNT(*) > 1 AND x.package_id = p.package_id)
           OR EXISTS (SELECT 1 FROM public.package x GROUP BY x.name HAVING COUNT(*) > 1 AND x.name = p.name)
    """),
    _check("package_snapshot_integrity", "package_snapshot의 필수 키·비음수 지표·PK 및 package/snapshot 참조를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.package_snapshot ps
        WHERE ps.package_id IS NULL OR ps.snapshot_at IS NULL
           OR ps.downloads < 0 OR ps.stars < 0 OR ps.open_issues < 0
           OR EXISTS (SELECT 1 FROM public.package_snapshot x GROUP BY x.package_id, x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.package_id = ps.package_id AND x.snapshot_at = ps.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM public.package p WHERE p.package_id = ps.package_id)
           OR NOT EXISTS (SELECT 1 FROM public.snapshot s WHERE s.snapshot_at = ps.snapshot_at)
    """),
    _check("package_snapshot_population", "package_snapshot이 package 모집단과 snapshot별로 정확히 일치하는지 검사합니다.", """
        SELECT
          (SELECT COUNT(*) FROM validation.package_population p
           LEFT JOIN public.package_snapshot s USING (package_id, snapshot_at)
           WHERE s.package_id IS NULL)
        + (SELECT COUNT(*) FROM public.package_snapshot s
           LEFT JOIN validation.package_population p USING (package_id, snapshot_at)
           WHERE p.package_id IS NULL)
        ::BIGINT
    """),
    _check("version_integrity", "version의 필수 키·길이·ordinal·PK와 package 참조를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.version v
        WHERE v.package_id IS NULL OR v.version IS NULL OR TRIM(v.version) = '' OR LENGTH(v.version) > 100
           OR v.ordinal IS NULL OR v.ordinal < 0 OR v.dependency IS NULL
           OR EXISTS (SELECT 1 FROM public.version x GROUP BY x.package_id, x.version
                     HAVING COUNT(*) > 1 AND x.package_id = v.package_id AND x.version = v.version)
           OR NOT EXISTS (SELECT 1 FROM public.package p WHERE p.package_id = v.package_id)
    """),
    _check("snapshot_integrity", "snapshot의 필수 날짜와 PK 중복을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.snapshot s
        WHERE s.snapshot_at IS NULL
           OR EXISTS (SELECT 1 FROM public.snapshot x GROUP BY x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.snapshot_at = s.snapshot_at)
    """),
    _check("package_version_snapshot_integrity", "package_version_snapshot의 키·비음수 지표·PK 및 복합 FK를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.package_version_snapshot pvs
        WHERE pvs.package_id IS NULL OR pvs.version IS NULL OR pvs.snapshot_at IS NULL
           OR pvs.dependents_count IS NULL OR pvs.dependents_count < 0
           OR EXISTS (SELECT 1 FROM public.package_version_snapshot x
                     GROUP BY x.package_id, x.version, x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.package_id = pvs.package_id
                                    AND x.version = pvs.version AND x.snapshot_at = pvs.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM public.version v
                          WHERE v.package_id = pvs.package_id AND v.version = pvs.version)
           OR NOT EXISTS (SELECT 1 FROM public.snapshot s WHERE s.snapshot_at = pvs.snapshot_at)
    """),
    _check("snapshot_context_integrity", "검증 snapshot의 날짜·정확한 시각·중복과 날짜 불일치를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.snapshot_context c
        WHERE c.snapshot_at IS NULL OR c.snapshot_timestamp IS NULL
           OR CAST(c.snapshot_timestamp AS DATE) <> c.snapshot_at
           OR EXISTS (SELECT 1 FROM validation.snapshot_context x GROUP BY x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.snapshot_at = c.snapshot_at)
           OR EXISTS (SELECT 1 FROM validation.snapshot_context x GROUP BY x.snapshot_timestamp
                     HAVING COUNT(*) > 1 AND x.snapshot_timestamp = c.snapshot_timestamp)
           OR NOT EXISTS (SELECT 1 FROM public.snapshot s WHERE s.snapshot_at = c.snapshot_at)
    """),
    _check("snapshot_context_coverage", "snapshot 근거가 비어 있지 않고 서비스 날짜를 모두 포함하는지 검사합니다.", """
        SELECT (SELECT COUNT(*) FROM public.snapshot s
                WHERE NOT EXISTS (SELECT 1 FROM validation.snapshot_context c
                                  WHERE c.snapshot_at = s.snapshot_at))
             + CASE WHEN NOT EXISTS (SELECT 1 FROM validation.snapshot_context) THEN 1 ELSE 0 END
    """),
    _check("package_population_integrity", "검증 package 모집단의 NULL·중복·package 및 snapshot 참조를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.package_population p
        WHERE p.package_id IS NULL OR p.snapshot_at IS NULL
           OR EXISTS (SELECT 1 FROM validation.package_population x GROUP BY x.package_id, x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.package_id = p.package_id AND x.snapshot_at = p.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM public.package x WHERE x.package_id = p.package_id)
           OR NOT EXISTS (SELECT 1 FROM validation.snapshot_context c WHERE c.snapshot_at = p.snapshot_at)
    """),
    _check("target_population_integrity", "검증 target 모집단의 NULL·중복·참조를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.target_population t
        WHERE t.package_id IS NULL OR t.version IS NULL OR TRIM(t.version) = '' OR t.snapshot_at IS NULL
           OR EXISTS (SELECT 1 FROM validation.target_population x GROUP BY x.package_id, x.version, x.snapshot_at
                     HAVING COUNT(*) > 1 AND x.package_id = t.package_id AND x.version = t.version
                                    AND x.snapshot_at = t.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM public.version v WHERE v.package_id = t.package_id AND v.version = t.version)
           OR NOT EXISTS (SELECT 1 FROM validation.package_population p
                          WHERE p.package_id = t.package_id AND p.snapshot_at = t.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM validation.snapshot_context c WHERE c.snapshot_at = t.snapshot_at)
    """),
    _check("expected_package_metrics", "expected package 지표가 package_snapshot과 같은 모집단·값을 가지는지 검사합니다.", """
        SELECT
          (SELECT COUNT(*) FROM validation.expected_package_metrics e
           WHERE e.package_id IS NULL OR e.snapshot_at IS NULL
              OR e.downloads < 0 OR e.stars < 0 OR e.open_issues < 0
              OR EXISTS (SELECT 1 FROM validation.expected_package_metrics x
                         GROUP BY x.package_id, x.snapshot_at
                         HAVING COUNT(*) > 1 AND x.package_id = e.package_id AND x.snapshot_at = e.snapshot_at))
        + (SELECT COUNT(*) FROM validation.package_population p
           LEFT JOIN validation.expected_package_metrics e USING (package_id, snapshot_at)
           WHERE e.package_id IS NULL)
        + (SELECT COUNT(*) FROM validation.expected_package_metrics e
           LEFT JOIN validation.package_population p USING (package_id, snapshot_at)
           WHERE p.package_id IS NULL)
        + (SELECT COUNT(*) FROM validation.expected_package_metrics e
           JOIN public.package_snapshot s USING (package_id, snapshot_at)
           WHERE e.downloads IS DISTINCT FROM s.downloads
              OR e.stars IS DISTINCT FROM s.stars OR e.open_issues IS DISTINCT FROM s.open_issues)
        + (SELECT COUNT(*) FROM public.package_snapshot s
           LEFT JOIN validation.expected_package_metrics e USING (package_id, snapshot_at)
           WHERE e.package_id IS NULL)
        ::BIGINT
    """),
    _check("target_pvs_missing", "target 모집단에 필요한 package_version_snapshot 행 누락을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.target_population t
        LEFT JOIN public.package_version_snapshot p
          ON p.package_id = t.package_id AND p.version = t.version AND p.snapshot_at = t.snapshot_at
        WHERE p.package_id IS NULL
    """),
    _check("target_pvs_extra", "target 모집단 범위에서 벗어난 package_version_snapshot 행을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.package_version_snapshot p
        LEFT JOIN validation.target_population t
          ON t.package_id = p.package_id AND t.version = p.version AND t.snapshot_at = p.snapshot_at
        WHERE t.package_id IS NULL
    """),
    _check("resolved_edges_integrity", "resolved edge의 target 참조·snapshot 참조와 source 버전의 필수 식별자를 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.resolved_edges e
        WHERE e.source_package_id IS NULL OR e.source_version IS NULL
           OR e.target_package_id IS NULL OR e.target_version IS NULL OR e.snapshot_at IS NULL
           OR NOT EXISTS (SELECT 1 FROM public.version v
                          WHERE v.package_id = e.source_package_id AND v.version = e.source_version)
           OR NOT EXISTS (SELECT 1 FROM validation.target_population t
                          WHERE t.package_id = e.target_package_id AND t.version = e.target_version
                            AND t.snapshot_at = e.snapshot_at)
           OR NOT EXISTS (SELECT 1 FROM validation.snapshot_context c WHERE c.snapshot_at = e.snapshot_at)
    """),
    _check("resolved_edges_direct_count", "중복 edge는 dedup하고 source package-version의 direct 관계 수만 검사합니다.", """
        SELECT COALESCE((
          WITH expected AS (
            SELECT e.snapshot_at, e.target_package_id, e.target_version,
                   COUNT(DISTINCT (e.source_package_id, e.source_version)) AS direct_count
            FROM validation.resolved_edges e
            GROUP BY e.snapshot_at, e.target_package_id, e.target_version
          ), actual AS (
            SELECT t.snapshot_at, t.package_id AS target_package_id, t.version AS target_version,
                   COALESCE(e.direct_count, 0) AS expected_count,
                   p.dependents_count AS actual_count
            FROM validation.target_population t
            LEFT JOIN expected e ON e.snapshot_at = t.snapshot_at
               AND e.target_package_id = t.package_id AND e.target_version = t.version
            LEFT JOIN public.package_version_snapshot p ON p.snapshot_at = t.snapshot_at
               AND p.package_id = t.package_id AND p.version = t.version
          )
          SELECT COUNT(*) FROM actual
          WHERE actual_count IS NULL OR actual_count IS DISTINCT FROM expected_count
        ), 0)::BIGINT
    """),
    _check("version_snapshot_eligibility", "source/target version의 published_at NULL 및 snapshot 이후 시각을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM (
          SELECT t.snapshot_at, t.package_id, t.version
          FROM validation.target_population t JOIN public.version v USING (package_id, version)
          JOIN validation.snapshot_context c USING (snapshot_at)
          WHERE v.published_at IS NULL OR v.published_at > c.snapshot_timestamp
          UNION
          SELECT e.snapshot_at, e.source_package_id, e.source_version
          FROM validation.resolved_edges e JOIN public.version v
            ON v.package_id = e.source_package_id AND v.version = e.source_version
          JOIN validation.snapshot_context c USING (snapshot_at)
          WHERE v.published_at IS NULL OR v.published_at > c.snapshot_timestamp
        ) bad
    """),
    _check("source_quality_integrity", "source_quality의 상태·count 유효성과 COMPLETE/PARTIAL 계약을 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.source_quality q
        WHERE q.snapshot_at IS NULL OR q.calculation_status IS NULL OR q.resolution_status IS NULL
           OR q.calculation_status <> 'COMPLETE'
           OR q.resolution_status NOT IN ('COMPLETE', 'PARTIAL')
           OR q.unresolved_count IS NULL OR q.unresolved_count < 0
           OR (q.resolution_status = 'COMPLETE' AND q.unresolved_count <> 0)
           OR NOT EXISTS (SELECT 1 FROM validation.snapshot_context c WHERE c.snapshot_at = q.snapshot_at)
           OR EXISTS (SELECT 1 FROM validation.source_quality x GROUP BY x.snapshot_at
                      HAVING COUNT(*) > 1 AND x.snapshot_at = q.snapshot_at)
    """),
    _check("source_quality_zero_contract", "PVS dependents_count=0은 계산 완료·target 모집단 포함 조건에서만 허용되는지 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM public.package_version_snapshot p
        WHERE p.dependents_count = 0
          AND (NOT EXISTS (SELECT 1 FROM validation.source_quality q
                           WHERE q.snapshot_at = p.snapshot_at AND q.calculation_status = 'COMPLETE')
               OR NOT EXISTS (SELECT 1 FROM validation.target_population t
                              WHERE t.snapshot_at = p.snapshot_at AND t.package_id = p.package_id
                                AND t.version = p.version))
    """),
    _check("source_quality_snapshot_coverage", "모든 검증 snapshot에 유효한 source_quality 행이 있는지 검사합니다.", """
        SELECT COUNT(*)::BIGINT FROM validation.snapshot_context c
        LEFT JOIN validation.source_quality q ON q.snapshot_at = c.snapshot_at
        WHERE q.snapshot_at IS NULL
    """),
)


__all__ = ["CHECKS"]
