"""Verified full historical source, streamed to one PostgreSQL COPY date at a time."""
from __future__ import annotations

import json
from pathlib import Path
import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _path
from .historical_db_prepare import _source
from . import historical_parallel_input as inputs


def copy_text(con, query, columns, path):
    """Escape PostgreSQL TEXT fields in SQL, without materializing Python rows."""
    fields = []
    for name in columns:
        value = f'cast("{name}" as varchar)'
        for old, new in ((92, 'chr(92)||chr(92)'), (9, "chr(92)||'t'"),
                         (10, "chr(92)||'n'"), (13, "chr(92)||'r'")):
            value = f'replace({value},chr({old}),{new})'
        fields.append(value)
    con.execute('COPY (SELECT ' + ','.join(fields) + ' FROM (' + query +
                ") q) TO ? (FORMAT CSV, DELIMITER '\t', QUOTE '', ESCAPE '', HEADER false, NULL '\\N')",
                [str(path)])


def file_record(path, role, rows):
    return {'role': role, 'sha256': file_sha256(path), 'bytes': path.stat().st_size, 'rows': rows}


def dense_date(con, index, day, stamp):
    """Reject invalid positives before restoring genuine zero-count targets."""
    con.execute('CREATE OR REPLACE TEMP TABLE day_positive AS SELECT * FROM counts WHERE snapshot_at=?', [day])
    if con.execute('SELECT EXISTS(SELECT 1 FROM day_positive p LEFT JOIN targets t USING(package_id,version) '
                   'WHERE t.package_id IS NULL OR t.birth_index>? OR p.dependents_count IS NULL '
                   'OR p.dependents_count<=0 OR p.dependents_count>2147483647 '
                   'OR p.snapshot_timestamp IS DISTINCT FROM ?::TIMESTAMPTZ)', [index, stamp]).fetchone()[0]:
        raise ValueError('Invalid positive count or target publication date')
    if con.execute('SELECT EXISTS(SELECT 1 FROM day_positive GROUP BY package_id,version HAVING count(*)>1)').fetchone()[0]:
        raise ValueError('Duplicate positive key')
    con.execute('CREATE OR REPLACE TEMP TABLE day_counts AS SELECT t.package_id,t.version,?::DATE snapshot_at,'
                'coalesce(p.dependents_count,0)::INTEGER dependents_count FROM targets t '
                'LEFT JOIN day_positive p USING(package_id,version) WHERE t.birth_index<=?', [day, index])
    row = con.execute('SELECT count(*),count(*) FILTER(WHERE dependents_count>0),'
                      'count(*) FILTER(WHERE dependents_count=0),coalesce(sum(dependents_count),0),'
                      'coalesce(max(dependents_count),0) FROM day_counts').fetchone()
    return dict(zip(('target_versions','positive_target_versions','zero_target_versions','distinct_edges','max_dependents_count'), row))


class FullSource:
    def __init__(self, run_dir, digest, output):
        self.root, self.output = _path(run_dir), _path(output)
        self.digest = digest
        self.con = duckdb.connect(config={'threads': 4, 'memory_limit': '4GB', 'max_temp_directory_size': '32GB'})
        try:
            self.con.execute("SET TimeZone='UTC'")
            self.con.execute('SET enable_progress_bar=false')
            self.prepared, self.im, self.source = _source(self.con, self.root, digest)
            for protected in (self.root.parent, self.prepared):
                if self.output.is_relative_to(protected) or protected.is_relative_to(self.output):
                    raise ValueError('DB work directory overlaps preserved source')
            if self.output.exists():
                raise ValueError('Use a fresh attempt work directory')
            self.output.mkdir(parents=True)
            self.con.execute('SET temp_directory=?', [str(self.output / 'scratch')])
            self.calendar = self.im['calendar']
            h1, raw = inputs._inputs(self.im['h1_dir'], self.im['h1_manifest_sha256'])
            self.lineage = {'population': {'run_id': raw['curated_run_id'],
                'manifest_sha256': raw['curated_manifest_sha256'], 'snapshot': raw['snapshot'],
                'snapshot_timestamp': raw['snapshot_timestamp']},
                'calendar': {'manifest_sha256': h1['calendar_manifest']['sha256']}}
            self.pins = {self.root/'run_manifest.json': digest,
                         self.prepared/'input_manifest.json': self.source['input_manifest_sha256']}
            files = {'target_names': [], 'target_population': []}
            for key, part in self.im['partitions'].items():
                if part['status'] == 'EMPTY':
                    continue
                if part['status'] != 'READY':
                    raise ValueError('Input partition is not ready')
                for role in files:
                    r = part['files'][role]
                    if r['name'] != f'partition={key}/{role}.parquet':
                        raise ValueError('Unexpected input path')
                    path = self.prepared/r['name']
                    if {**inputs._record(path, self.con), 'name': r['name']} != r:
                        raise ValueError('Prepared input changed')
                    files[role].append(str(path))
                    self.pins[path] = r['sha256']
            for role, paths in files.items():
                self.con.read_parquet(paths, hive_partitioning=False).create_view(role)
            self.con.execute('CREATE TEMP TABLE identities AS SELECT package_id,name FROM target_names WHERE package_id IS NOT NULL')
            self.con.execute('CREATE UNIQUE INDEX identities_id ON identities(package_id)')
            self.con.execute('CREATE UNIQUE INDEX identities_name ON identities(name)')
            self.con.execute('CREATE TEMP TABLE targets AS SELECT package_id,name,version,birth_index FROM target_population')
            self.con.execute('CREATE UNIQUE INDEX targets_key ON targets(package_id,version)')
            if self.con.execute('SELECT EXISTS(SELECT 1 FROM targets t LEFT JOIN identities i USING(package_id) '
                                'WHERE i.name IS DISTINCT FROM t.name OR t.version IS NULL OR '
                                't.birth_index IS NULL OR t.birth_index<0 OR t.birth_index>=?)', [len(self.calendar)]).fetchone()[0]:
                raise ValueError('Target identity or birth index is invalid')
            self.expected = {k: self.con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                             for k,t in (('identities','identities'),('versions','targets'))}
            if self.expected['versions'] != self.im['rows']['target_population']:
                raise ValueError('Target count differs from input manifest')
            self.unmapped_names = self.im['rows']['target_names'] - self.expected['identities']
            cursor = self.con.execute('SELECT * FROM source_quality')
            names = [d[0] for d in cursor.description]
            quality = [dict(zip(names, row)) for row in cursor.fetchall()]
            self.quality = {str(r['snapshot_at']): json.loads(json.dumps(r, default=str)) for r in quality}
            if len(self.quality) != len(self.calendar):
                raise ValueError('Quality calendar coverage mismatch')
            self.identity_file, self.version_file = self.output/'identities.tsv', self.output/'versions.tsv'
            copy_text(self.con, 'SELECT * FROM identities ORDER BY package_id', ('package_id','name'), self.identity_file)
            copy_text(self.con, 'SELECT package_id,version FROM targets ORDER BY package_id,version', ('package_id','version'), self.version_file)
            self.identity_record = file_record(self.identity_file, 'identities', self.expected['identities'])
        except Exception:
            self.con.close()
            raise

    def close(self):
        self.con.close()

    def recheck(self):
        for path, digest in self.pins.items():
            if file_sha256(path) != digest:
                raise ValueError('Pinned source changed: ' + str(path))
        inputs._inputs(self.im['h1_dir'], self.im['h1_manifest_sha256'])
        # Also validates every published positive/quality receipt and code contract.
        _source(self.con, self.root, self.digest)

    def prepare_date(self, day):
        rows = [(i,r) for i,r in enumerate(self.calendar) if r['snapshot_at'] == day]
        if len(rows) != 1:
            raise ValueError('Date is outside source calendar')
        index, calendar = rows[0]
        actual = dense_date(self.con, index, day, calendar['snapshot_timestamp'])
        quality = self.quality[day]
        if (quality['calculation_status'] != 'COMPLETE' or quality['resolution_status'] != 'PARTIAL'
                or quality['ready_for_load'] is not False or any(quality[k] != v for k,v in actual.items())):
            raise ValueError('Dense output differs from published source quality')
        path = self.output/'counts.tsv'
        copy_text(self.con, 'SELECT * FROM day_counts ORDER BY package_id,version',
                  ('package_id','version','snapshot_at','dependents_count'), path)
        records = [self.identity_record, file_record(path, 'counts', actual['target_versions'])]
        manifest = {**self.source, 'lineage': self.lineage, 'calendar': [calendar],
                    'scope': {'selection_sha256': self.im['selection']['chosen_names_sha256'],
                              'selection_count': self.im['selection']['chosen_count']},
                    'snapshot_at': day, 'snapshot_timestamp': calendar['snapshot_timestamp'],
                    'quality': quality, 'files': records}
        metadata = {'dataset': 'version-dependents', 'snapshot': day,
                    'snapshot_timestamp': calendar['snapshot_timestamp'],
                    'curated_run_id': self.root.parent.name, 'run_prefix': str(self.root),
                    'manifest_sha256': sha256(manifest), 'manifest': manifest,
                    'counts': {'identities': self.expected['identities'], 'package_version_snapshot': actual['target_versions']}}
        self.recheck()
        return metadata, {'identities': self.identity_file, 'counts': path}
