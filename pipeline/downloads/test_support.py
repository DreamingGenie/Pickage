"""Small download inputs with real zero, imputed gap and NOT_FOUND coverage."""
import gzip
import json
from pathlib import Path

import duckdb


def make_source(root: Path, source_run: str = 'source-1') -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / 'targets_top100k_20260902.csv').write_text(
        'rank,name,downloads_last_month,dependent_packages_count,status\n'
        '1,alpha,1000,10,\n2,beta,20,1,\n3,missing,0,0,\n4,missing,0,0,\n', encoding='utf-8')
    raw = root / 'raw' / f'run={source_run}'
    raw.mkdir(parents=True)
    metadata = {'run': source_run, 'mode': 'backfill', 'end': '2026-08-31',
                'targets': 'targets_top100k_20260902.csv'}
    (raw / 'run.json').write_text(json.dumps(metadata), encoding='utf-8')
    (raw / 'manifest.json').write_text(json.dumps({**metadata, 'final': True}), encoding='utf-8')
    dates = [f'2026-08-{n}' for n in range(28, 32)]
    values = {'alpha': [0, 2500, 2300, 2200], 'beta': [0, 0, 1, 0]}
    fetched = '2026-09-02T00:00:00+00:00'
    with gzip.open(raw / 'part-00000.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for rank, name in enumerate(('alpha', 'beta', 'missing'), 1):
            row = {'name': name, 'rank': rank, 'kind': 'single', 'start': dates[0],
                   'end': dates[-1], 'tier': 'A', 'fetched_at': fetched, 'task_id': str(rank),
                   'status': 'not_found' if name == 'missing' else 'ok',
                   'downloads': None if name == 'missing' else
                   [{'day': day, 'downloads': value} for day, value in zip(dates, values[name])]}
            stream.write(json.dumps(row) + '\n')
    (raw / 'checkpoint.sqlite').write_bytes(b'excluded fixture state')
    with duckdb.connect() as con:
        con.execute('CREATE TABLE daily(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,tier VARCHAR,fetched_at TIMESTAMP)')
        for i, day in enumerate(dates):
            con.execute('DELETE FROM daily')
            con.executemany('INSERT INTO daily VALUES (?,?,?,?,?)', [
                ('alpha', None if i == 0 else values['alpha'][i], i == 0, 'A', '2026-09-02 00:00:00'),
                ('beta', values['beta'][i], False, 'A', '2026-09-02 00:00:00')])
            directory = root / 'parquet' / 'downloads' / f'date={day}'
            directory.mkdir(parents=True)
            con.execute('COPY daily TO ? (FORMAT PARQUET)', [str(directory / 'part-0.parquet')])
        con.execute('CREATE TABLE statuses(name VARCHAR,tier VARCHAR,status VARCHAR,first_date DATE,last_date DATE,last_fetched_at TIMESTAMP)')
        con.executemany('INSERT INTO statuses VALUES (?,?,?,?,?,?)', [
            (name, 'A', 'NOT_FOUND' if name == 'missing' else 'READY', dates[0], dates[-1], '2026-09-02 00:00:00')
            for name in ('alpha', 'beta', 'missing')])
        con.execute('COPY statuses TO ? (FORMAT PARQUET)', [str(root / 'parquet/downloads_status.parquet')])
