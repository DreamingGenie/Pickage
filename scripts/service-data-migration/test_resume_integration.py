"""Prepare a small partial restore in an already isolated test container."""
import argparse
from pathlib import Path
import subprocess
import transfer


def prepare(container, work):
    def sql(db, statement):
        result = subprocess.run(['docker', 'exec', '-i', container, 'psql', '-X', '-U', 'postgres',
                                 '-d', db, '-v', 'ON_ERROR_STOP=1', '-At'],
                                input=statement.encode(), capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        return result.stdout

    source = 'pickage_import_341_smoke_source'
    reference = 'pickage_import_341_smoke_reference'
    candidate = 'pickage_import_341_smoke_candidate'
    for db in (source, reference, candidate):
        sql('postgres', 'CREATE DATABASE ' + db)
    sql(source, '''
CREATE SCHEMA vd193_reload_20260912_ready01;
CREATE TABLE package(package_id int PRIMARY KEY, name text UNIQUE);
CREATE TABLE version(package_id int NOT NULL REFERENCES package, version varchar(100) NOT NULL, PRIMARY KEY(package_id,version));
CREATE TABLE snapshot(snapshot_at date PRIMARY KEY);
CREATE TABLE package_snapshot(package_id int REFERENCES package,snapshot_at date REFERENCES snapshot,PRIMARY KEY(package_id,snapshot_at));
CREATE TABLE package_version_snapshot(package_id int NOT NULL,version varchar(100) NOT NULL,snapshot_at date NOT NULL,dependents_count int NOT NULL DEFAULT 0 CHECK(dependents_count>=0),PRIMARY KEY(package_id,version,snapshot_at),CONSTRAINT version_fk FOREIGN KEY(package_id,version) REFERENCES version, CONSTRAINT snapshot_fk FOREIGN KEY(snapshot_at) REFERENCES snapshot) PARTITION BY RANGE(snapshot_at);
CREATE TABLE vd193_reload_20260912_ready01.d20260824 PARTITION OF package_version_snapshot FOR VALUES FROM ('2026-08-24') TO ('2026-08-25');
CREATE TABLE vd193_reload_20260912_ready01.d20260831 PARTITION OF package_version_snapshot FOR VALUES FROM ('2026-08-31') TO ('2026-09-01');
INSERT INTO package SELECT i,'pkg-'||i FROM generate_series(1,100) i;
INSERT INTO version SELECT i,'1.0.0' FROM generate_series(1,100) i;
INSERT INTO snapshot VALUES('2026-08-24'),('2026-08-31');
INSERT INTO package_snapshot SELECT package_id,snapshot_at FROM package CROSS JOIN snapshot;
INSERT INTO package_version_snapshot SELECT package_id,version,snapshot_at,package_id FROM version CROSS JOIN snapshot;
''')
    subprocess.run(['docker', 'exec', container, 'pg_dump', '-U', 'postgres', '-d', source,
                    '-Fd', '-f', '/work/archive', '--no-owner', '--no-privileges'], check=True)
    transfer.write_manifest(work / 'archive', source_db=source, jobs=1, compression='gzip:1')
    for db, flags in [(reference, ['--schema-only']),
                      (candidate, ['--section=pre-data', '--section=data'])]:
        subprocess.run(['docker', 'exec', container, 'pg_restore', '-U', 'postgres', '-d', db,
                        '--no-owner', '--no-privileges', '--exit-on-error', *flags, '/work/archive'], check=True)
    sql(candidate, 'ALTER TABLE package ADD CONSTRAINT package_pkey PRIMARY KEY(package_id); '
                   'ALTER TABLE version ADD CONSTRAINT version_pkey PRIMARY KEY(package_id,version);')
    transfer.write_json(work / (candidate + '.restore-status.json'), {
        'candidate_db': candidate, 'status': 'FAILED', 'phases': [{'name': 'pre-data'}, {'name': 'data'}]})
    print('Fixture ready: 200 PVS rows, two committed PKs; no source/service mutation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.container.startswith('pickage-341-resume-test'):
        raise ValueError('Only a dedicated resume-test container is allowed')
    prepare(args.container, args.work_dir.resolve())
