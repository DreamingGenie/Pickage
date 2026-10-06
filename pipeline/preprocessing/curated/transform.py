"""Local, disk-backed relational transform; no network or serving-DB writes."""
from pathlib import Path
import json
import time

import duckdb

from pipeline.preprocessing.curated.repository import normalize_repository_url

_VERSION_BUCKET_ROWS = 1_000_000


class ValidationError(ValueError):
    """A quality gate failed. Messages contain counts, never raw field values."""


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _source(con, name, files):
    if not files:
        raise ValidationError(f"No input files: {name}")
    paths = ','.join(_literal(Path(p).resolve().as_posix()) for p in files)
    con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet([{paths}], hive_partitioning=false)")


def _require_zero(con, label, query):
    count = con.execute(query).fetchone()[0]
    if count:
        raise ValidationError(f"{label}: {count} invalid rows/groups")


def _export(con, directory, name, query):
    target = directory / name
    target.mkdir(parents=True, exist_ok=False)
    con.execute(f"COPY ({query}) TO {_literal(target.as_posix())} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 65536, "
                "PER_THREAD_OUTPUT true, FILE_SIZE_BYTES '256MB')")
    # DuckDB still writes a readable, typed Parquet for empty outputs.
    return sorted(target.glob('*.parquet'))


def transform(con, versions, requirements, previous_ids, snapshot, output,
              previous_packages=None):
    """Write validated ERD projections and full ID registry to a fresh directory.

    Callers provide exact manifest-listed, checksum-verified files. Each call
    requires a fresh DuckDB connection and an empty output directory.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET TimeZone='UTC'")
    _source(con, 'raw_versions', versions)
    _source(con, 'raw_requirements', requirements)
    for table in ('raw_versions', 'raw_requirements'):
        _require_zero(con, f'{table} snapshot mismatch',
                      f"SELECT count(*) FROM {table} WHERE SnapshotAt IS NULL "
                      f"OR CAST(SnapshotAt AS DATE) <> DATE {_literal(snapshot)}")
    vtime = con.execute('SELECT min(SnapshotAt), max(SnapshotAt) FROM raw_versions').fetchone()
    rtime = con.execute('SELECT min(SnapshotAt), max(SnapshotAt) FROM raw_requirements').fetchone()
    if vtime[0] is None or vtime[0] != vtime[1] or (rtime[0] is not None and rtime != vtime):
        raise ValidationError('Inputs must describe the same exact SnapshotAt')
    report = dict(zip(['input_versions', 'release_versions', 'nonrelease_versions',
                       'unknown_release_versions', 'excluded_future_versions'], con.execute("""
        SELECT count(*), count(*) FILTER(WHERE is_release=true),
          count(*) FILTER(WHERE is_release=false), count(*) FILTER(WHERE is_release IS NULL),
          count(*) FILTER(WHERE is_release=true AND published_at>SnapshotAt)
        FROM raw_versions
    """).fetchone()))
    report['snapshot_timestamp'] = vtime[0].isoformat()
    print('Transform: filtering versions', flush=True)
    con.execute("""CREATE VIEW eligible AS SELECT *,sha256(source_repo) AS repo_key FROM raw_versions
        WHERE is_release=true AND (published_at IS NULL OR published_at<=SnapshotAt)""")
    _require_zero(con, 'Version required fields/lengths', """SELECT count(*) FROM eligible
        WHERE Name IS NULL OR trim(Name)='' OR length(Name)>300 OR contains(Name,chr(0))
        OR Version IS NULL OR trim(Version)='' OR length(Version)>100 OR contains(Version,chr(0))
        OR ordinal IS NULL OR ordinal<0
        OR contains(Deprecated,chr(0))""")
    _require_zero(con, 'Duplicate version keys', """SELECT count(*) FROM
        (SELECT Name,Version FROM eligible GROUP BY ALL HAVING count(*)>1)""")
    report['versions'], report['missing_published_at'] = con.execute(
        'SELECT count(*),count(*) FILTER(WHERE published_at IS NULL) FROM eligible').fetchone()
    report['nul_descriptions'] = con.execute(
        'SELECT count(*) FROM eligible WHERE contains(Description,chr(0))').fetchone()[0]
    if not report['versions']:
        raise ValidationError('No eligible versions; refusing empty publication')
    con.execute('CREATE TABLE names AS SELECT DISTINCT Name AS name FROM eligible')
    if previous_ids:
        _source(con, 'old_ids_source', previous_ids)
        _require_zero(con, 'Invalid existing package ID mapping', """SELECT count(*) FROM old_ids_source
            WHERE name IS NULL OR trim(name)='' OR length(name)>300 OR contains(name,chr(0))
            OR package_id IS NULL OR package_id<1 OR package_id>2147483647
            OR package_id<>floor(package_id)""")
        for col in ('name','package_id'):
            _require_zero(con, 'Duplicate existing package ID mapping',
                          f'SELECT count(*) FROM (SELECT {col} FROM old_ids_source GROUP BY ALL HAVING count(*)>1)')
        con.execute('CREATE TABLE old_ids AS SELECT package_id::INTEGER AS package_id,name::VARCHAR AS name FROM old_ids_source')
    else:
        con.execute('CREATE TABLE old_ids(package_id INTEGER, name VARCHAR)')
    if previous_packages:
        _source(con, 'old_packages_source', previous_packages)
        old_package_columns = [r[0] for r in con.execute('DESCRIBE old_packages_source').fetchall()]
        if 'package_id' not in old_package_columns or 'name' not in old_package_columns:
            raise ValidationError('Invalid existing package mapping')
        if 'repo_url' in old_package_columns:
            con.execute('CREATE TABLE old_packages AS SELECT * FROM old_packages_source')
        else:
            con.execute('CREATE TABLE old_packages AS SELECT *, NULL::VARCHAR AS repo_url FROM old_packages_source')
    else:
        con.execute('CREATE TABLE old_packages(package_id INTEGER, name VARCHAR, repo_url VARCHAR)')
    maximum = con.execute('SELECT coalesce(max(package_id),0) FROM old_ids').fetchone()[0]
    con.execute('CREATE TABLE new_names AS SELECT name FROM names ANTI JOIN old_ids USING(name)')
    report['new_packages'] = con.execute('SELECT count(*) FROM new_names').fetchone()[0]
    if maximum + report['new_packages'] > 2147483647:
        raise ValidationError('package_id exceeds PostgreSQL INT capacity')
    con.execute(f"""CREATE TABLE package_ids AS SELECT * FROM old_ids UNION ALL
        SELECT ({maximum}+row_number() OVER(ORDER BY name))::INTEGER package_id,name FROM new_names""")
    report['registry_packages'] = con.execute('SELECT count(*) FROM package_ids').fetchone()[0]

    print('Transform: normalizing repository candidates', flush=True)
    con.execute('CREATE TABLE distinct_repos AS SELECT DISTINCT repo_key,source_repo FROM eligible WHERE source_repo IS NOT NULL')
    # A native Python DuckDB UDF introduces an otherwise unnecessary NumPy
    # dependency. Stream distinct URLs through the stdlib normalizer instead.
    normalized_path = output.parent / 'normalized_repositories.jsonl'
    rows = con.execute('SELECT repo_key,source_repo FROM distinct_repos')
    with normalized_path.open('x', encoding='utf-8') as stream:
        while batch := rows.fetchmany(8192):
            for key, raw in batch:
                stream.write(json.dumps({'repo_key': key, 'repo_url': normalize_repository_url(raw)}) + '\n')
    con.execute(f"""CREATE TABLE normalized_repos AS SELECT * FROM read_json(
        {_literal(normalized_path.as_posix())},format='newline_delimited',
        columns={{repo_key:'VARCHAR',repo_url:'VARCHAR'}})""")
    report['invalid_or_unsupported_repo_values'] = con.execute(
        'SELECT count(*) FROM normalized_repos WHERE repo_url IS NULL').fetchone()[0]
    report['ordinal_tie_groups'] = con.execute("""SELECT count(*) FROM
        (SELECT Name,ordinal FROM eligible GROUP BY ALL HAVING count(*)>1)""").fetchone()[0]
    con.execute("""CREATE TABLE chosen_repos AS
        SELECT e.Name AS name,e.Version AS version,e.ordinal,n.repo_url,e.repo_key AS source_repo_sha256
        FROM eligible e JOIN normalized_repos n USING(repo_key)
        WHERE n.repo_url IS NOT NULL
        QUALIFY row_number() OVER(PARTITION BY e.Name ORDER BY e.ordinal DESC,
            e.published_at DESC NULLS LAST,e.Version ASC)=1""")
    con.execute("""CREATE TABLE packages AS
        SELECT i.package_id,n.name,CASE WHEN old.package_id IS NOT NULL THEN old.repo_url ELSE r.repo_url END AS repo_url FROM names n
        JOIN package_ids i USING(name) LEFT JOIN chosen_repos r USING(name)
        LEFT JOIN old_packages old USING(package_id)""")
    report['packages'], report['packages_without_repo'] = con.execute(
        'SELECT count(*),count(*) FILTER(WHERE repo_url IS NULL) FROM packages').fetchone()
    # These relations are only inputs to repository selection.  Drop their
    # materialized copies before building the dependency projections so the
    # DuckDB work file does not retain two repository-normalization stages.
    con.execute('DROP TABLE distinct_repos')
    con.execute('DROP TABLE normalized_repos')
    if normalized_path.is_file():
        normalized_path.unlink()

    print('Transform: assembling declared dependency JSON', flush=True)
    con.execute("""CREATE MACRO bad_dependencies(a) AS (
        a IS NULL OR len(list_filter(a,x -> x IS NULL OR x.Name IS NULL OR trim(x.Name)=''
          OR contains(x.Name,chr(0)) OR x.Requirement IS NULL))>0
        OR len(list_distinct(list_transform(a,x -> x.Name)))<>len(list_distinct(a))
    )""")
    con.execute("""CREATE MACRO dependency_map(a) AS
        map_from_entries(list_transform(list_sort(list_distinct(a)),
            x -> struct_pack(k:=x.Name,v:=x.Requirement)))""")
    version_buckets = min(16, max(1, (report['versions'] + _VERSION_BUCKET_ROWS - 1) // _VERSION_BUCKET_ROWS))
    requirements_sql = """SELECT Name,Version,
        bad_dependencies(Dependencies) OR bad_dependencies(PeerDependencies)
            OR bad_dependencies(OptionalDependencies) invalid,
        CASE WHEN invalid THEN NULL ELSE json_object(
            'dependencies',dependency_map(Dependencies),
            'peerDependencies',dependency_map(PeerDependencies),
            'optionalDependencies',dependency_map(OptionalDependencies)) END dependency
        FROM matched_requirements"""
    report['invalid_requirements'] = report['missing_requirements'] = 0
    version_projection = """SELECT
        e.Version::VARCHAR AS version,p.package_id,e.published_at,e.ordinal::BIGINT AS ordinal,
        CASE WHEN contains(e.Description,chr(0)) THEN NULL ELSE e.Description END::VARCHAR AS description,
        to_json(e.Licenses) AS licenses,
        e.Deprecated::VARCHAR AS deprecated,r.dependency
        FROM eligible_bucket e JOIN packages p ON e.Name=p.name
        LEFT JOIN requirements_bucket r ON e.Name=r.Name AND e.Version=r.Version"""
    issues_projection = """SELECT e.Name,e.Version,
        CASE WHEN r.Name IS NULL THEN 'MISSING_REQUIREMENTS' ELSE 'INVALID_REQUIREMENTS' END reason
        FROM eligible_bucket e LEFT JOIN requirements_bucket r ON e.Name=r.Name AND e.Version=r.Version
        WHERE r.Name IS NULL OR r.invalid"""
    version_target = output / 'version/data'
    version_target.mkdir(parents=True, exist_ok=False)
    issues_target = output / 'quality/dependency_issues'
    issues_target.mkdir(parents=True, exist_ok=False)
    version_files = []
    dependency_issue_count = 0
    for bucket in range(version_buckets):
        bucket_started = time.monotonic()
        # Bound BOTH sides before the semijoin. Partitioning COPY output alone
        # still builds a hash table for the entire snapshot and spills it.
        con.execute(f"CREATE VIEW eligible_bucket AS SELECT * FROM eligible "
                    f"WHERE hash(Name) % {version_buckets} = {bucket}")
        con.execute(f"""CREATE VIEW matched_requirements AS
            SELECT r.* FROM (SELECT * FROM raw_requirements
                WHERE hash(Name) % {version_buckets} = {bucket}) r
            SEMI JOIN eligible_bucket e
                ON r.Name=e.Name AND r.Version=e.Version AND r.SnapshotAt=e.SnapshotAt""")
        _require_zero(con, 'Duplicate requirements keys', """SELECT count(*) FROM
            (SELECT Name,Version FROM matched_requirements GROUP BY ALL HAVING count(*)>1)""")
        requirements_name = f'requirements-json-{bucket}'
        requirement_files = _export(con, output.parent, requirements_name, requirements_sql)
        _source(con, 'requirements_bucket', requirement_files)
        invalid = con.execute('SELECT count(*) FROM requirements_bucket WHERE invalid').fetchone()[0]
        missing = con.execute("""SELECT count(*) FROM eligible_bucket e
            ANTI JOIN requirements_bucket r ON e.Name=r.Name AND e.Version=r.Version""").fetchone()[0]
        report['invalid_requirements'] += invalid
        report['missing_requirements'] += missing
        requirements_seconds = time.monotonic() - bucket_started
        timings = {}
        for name, target_dir, query in (
                (f'version-bucket-{bucket}', version_target, version_projection),
                (f'dependency-issues-{bucket}', issues_target, issues_projection)):
            export_started = time.monotonic()
            generated = _export(con, output.parent, name, query)
            if target_dir == issues_target:
                actual = con.execute('SELECT count(*) FROM read_parquet(?,hive_partitioning=false)',
                                     [[str(path) for path in generated]]).fetchone()[0]
                if actual != invalid + missing:
                    raise ValidationError('Export count mismatch: quality/dependency_issues')
                dependency_issue_count += actual
            for index, path in enumerate(generated):
                target = target_dir / f'part-{bucket:03d}-{index:06d}.parquet'
                path.replace(target)
                if target_dir == version_target:
                    version_files.append(target)
            (output.parent / name).rmdir()
            timings['version' if target_dir == version_target else 'quality'] = time.monotonic() - export_started
        con.execute('DROP VIEW requirements_bucket')
        con.execute('DROP VIEW matched_requirements')
        con.execute('DROP VIEW eligible_bucket')
        for path in requirement_files:
            path.unlink()
        (output.parent / requirements_name).rmdir()
        print(f'Transform: version bucket {bucket + 1}/{version_buckets} complete '
              f'requirements_seconds={requirements_seconds:.3f} '
              f'version_seconds={timings["version"]:.3f} quality_seconds={timings["quality"]:.3f}', flush=True)
    version_paths = [str(f) for f in version_files]
    version_literals = ','.join(_literal(Path(p).resolve().as_posix()) for p in version_paths)
    con.execute(f'CREATE VIEW final_versions_output AS SELECT * FROM read_parquet([{version_literals}], hive_partitioning=false)')
    _require_zero(con, 'Output FK', 'SELECT count(*) FROM final_versions_output ANTI JOIN packages USING(package_id)')
    final_count = con.execute('SELECT count(*) FROM final_versions_output').fetchone()[0]
    if final_count != report['versions'] or final_count + report['excluded_future_versions'] != report['release_versions']:
        raise ValidationError('Version count reconciliation failed')
    _require_zero(con, 'Output repository length', 'SELECT count(*) FROM packages WHERE length(repo_url)>200')
    _require_zero(con, 'Output duplicate version keys', """SELECT count(*) FROM
        (SELECT package_id,version FROM final_versions_output GROUP BY ALL HAVING count(*)>1)""")
    _require_zero(con, 'Changed existing IDs', """SELECT count(*) FROM old_ids o
        LEFT JOIN package_ids p USING(name) WHERE p.package_id IS DISTINCT FROM o.package_id""")
    print('Transform: writing validated Parquet outputs', flush=True)
    exports = {
        'package/data': 'SELECT * FROM packages',
        'package_ids/data': 'SELECT * FROM package_ids',
        'quality/repository_selection': """SELECT p.package_id,r.version,r.ordinal,r.repo_url,r.source_repo_sha256
            FROM chosen_repos r JOIN packages p USING(name)""",
        'quality/excluded_versions': """SELECT Name,Version,SnapshotAt,published_at,
            'PUBLISHED_AFTER_SNAPSHOT' reason FROM raw_versions
            WHERE is_release=true AND published_at>SnapshotAt""",
        'quality/metadata_issues': """SELECT Name,Version,'description' AS field,
            'NUL_IN_DESCRIPTION' AS reason FROM eligible WHERE contains(Description,chr(0))""",
    }
    output_counts = {'version/data': final_count, 'quality/dependency_issues': dependency_issue_count}
    for name, query in exports.items():
        files = _export(con, output, name, query)
        if not files:
            raise ValidationError(f'No Parquet produced: {name}')
        paths = [str(f) for f in files]
        actual = con.execute('SELECT count(*) FROM read_parquet(?,hive_partitioning=false)', [paths]).fetchone()[0]
        expected = con.execute(f'SELECT count(*) FROM ({query})').fetchone()[0]
        if actual != expected:
            raise ValidationError(f'Export count mismatch: {name}')
        output_counts[name] = actual
    report['output_counts'] = output_counts
    return report
