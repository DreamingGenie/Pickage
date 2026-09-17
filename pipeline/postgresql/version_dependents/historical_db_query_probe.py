"""Bounded read-only package/version history latency probe on a completed reload."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

from pipeline.postgresql.postgres import PgLoader
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.postgresql.version_dependents.historical_db_fast_publish import target_schema
from pipeline.postgresql.version_dependents.historical_db_reload import validate_generation, _verify_db_identity


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def stats(values):
    ordered = sorted(values)
    return {'n': len(values), 'median': statistics.median(values),
            'p95_nearest_rank': ordered[math.ceil(len(values) * .95)-1],
            'min': min(values), 'max': max(values)}


def nodes(node):
    yield node
    for child in node.get('Plans', []):
        yield from nodes(child)


def summarize(plan):
    root = plan['Plan']
    scans = [node for node in nodes(root) if node.get('Relation Name')]
    return {'planning_ms': plan['Planning Time'], 'execution_ms': plan['Execution Time'],
            'db_total_ms': plan['Planning Time'] + plan['Execution Time'],
            'rows': root['Actual Rows'], 'root_node': root['Node Type'],
            'scan_nodes': dict(Counter(node['Node Type'] for node in scans)),
            'relations_planned': len({node['Relation Name'] for node in scans}),
            'relations_executed': len({node['Relation Name'] for node in scans if node.get('Actual Loops', 0)>0}),
            'shared_hit_blocks': root.get('Shared Hit Blocks', 0),
            'shared_read_blocks': root.get('Shared Read Blocks', 0),
            'temp_read_blocks': root.get('Temp Read Blocks', 0),
            'temp_written_blocks': root.get('Temp Written Blocks', 0)}


def explain(db, query):
    plan = json.loads('\n'.join(db._send('EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) '+query)))[0]
    return summarize(plan), plan


def run(config_path, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    job = Path(config['output'])
    plan = json.loads(Path(config['plan']).read_text(encoding='utf-8'))
    timing = json.loads((job/'timing.json').read_text(encoding='utf-8'))
    if not timing.get('full_load_complete') or not timing.get('all_dates_newly_loaded'):
        raise ValueError('A complete fresh reload is required')
    validate_generation(plan['generation'])
    schema = target_schema(plan['schema'])
    parent = schema+'.package_version_snapshot'
    keys = json.loads((job/'key-verification.json').read_text(encoding='utf-8'))
    identity_record = keys['files']['identities']
    identity_path = Path(identity_record['path'])
    if file_sha256(identity_path) != identity_record['sha256']:
        raise ValueError('Identity input changed')
    identities = [(int(line.split('\t',1)[0]), line.split('\t',1)[1])
                  for line in identity_path.read_text(encoding='utf-8').splitlines()]
    popular = {'react','lodash','typescript','express','webpack','vue','next','jquery'}
    selected = [(i,n,'popular') for i,n in identities if n in popular]
    others = sorted(((i,n) for i,n in identities if n not in popular),
                    key=lambda row: hashlib.sha256(row[1].encode()).digest())[:8]
    selected += [(i,n,'name_sha_sample') for i,n in others]
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'status':'RUNNING',
              'target':parent, 'source_manifest_sha256':plan['source_run_manifest_sha256'],
              'cache_policy':'No cache clearing; first execution is not cold-cache evidence',
              'version_selection':'lexicographic first/middle/last from latest snapshot',
              'load_timing':timing, 'cases':[], 'empty_packages':[]}
    with PgLoader(plan['db_command'], output) as db:
        db._send("SET application_name='vd193-history-query-probe'; SET default_transaction_read_only=on; SET statement_timeout='30s';")
        _verify_db_identity(db, plan['db_identity'])
        if db._send("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND application_name='vd193-fast-reload';") != ['0']:
            raise RuntimeError('Reload is still active')
        saved = json.loads(db._send(f'SELECT plan FROM {schema}.reload_plan WHERE singleton;')[0])
        if saved != plan:
            raise ValueError('Database plan differs')
        receipt = json.loads(db._send(f"SELECT json_build_object('dates',count(*),'rows',sum(rows)) FROM {schema}.reload_partition;")[0])
        if receipt != {'dates':plan['expected_dates'],'rows':plan['expected_rows']}:
            raise ValueError('Database receipts incomplete')
        report['receipts'] = receipt
        report['environment'] = json.loads(db._send("SELECT json_build_object('version',version(),'shared_buffers',current_setting('shared_buffers'),'work_mem',current_setting('work_mem'),'block_size',current_setting('block_size'),'jit',current_setting('jit'),'max_parallel_workers_per_gather',current_setting('max_parallel_workers_per_gather'),'read_only',current_setting('default_transaction_read_only')); ")[0])
        report['partition_count'] = int(db._send(f"SELECT count(*) FROM pg_inherits WHERE inhparent='{parent}'::regclass;")[0])
        report['parent_indexes'] = db._send(f"SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid='{parent}'::regclass;")
        low, high = plan['dates'][0], plan['dates'][-1]
        query_base = f'SELECT snapshot_at,dependents_count FROM {parent} WHERE package_id={{package_id}} AND version={{version}} AND snapshot_at BETWEEN DATE {db._literal(low)} AND DATE {db._literal(high)} ORDER BY snapshot_at;'
        for package_id,name,stratum in selected:
            versions = json.loads(db._send(f"SELECT coalesce(json_agg(version ORDER BY version),'[]') FROM {schema}.d{high.replace('-','')} WHERE package_id={package_id};")[0])
            if not versions:
                report['empty_packages'].append(name)
                continue
            indexes = sorted({0,len(versions)//2,len(versions)-1})
            for index in indexes:
                version = versions[index]
                query = query_base.format(package_id=package_id, version=db._literal(version))
                first, first_plan = explain(db, query)
                warm = [explain(db,query)[0] for _ in range(3)]
                actual_times, expected = [], None
                for _ in range(3):
                    mark = time.perf_counter()
                    rows = db._send(query)
                    actual_times.append((time.perf_counter()-mark)*1000)
                    if expected is None:
                        expected = rows
                    elif rows != expected:
                        raise ValueError('Repeated results changed')
                dates = [row.split('|')[0] for row in expected]
                if dates != sorted(set(dates)) or len(dates)>len(plan['dates']) or len(dates)!=first['rows']:
                    raise ValueError('Result ordering/cardinality mismatch')
                if any(int(row.split('|')[1])<0 for row in expected):
                    raise ValueError('Negative dependent count')
                case = {'package_id':package_id,'name':name,'version':version,'stratum':stratum,
                        'latest_version_count':len(versions),'first':first,'warm':warm,
                        'select_receive_ms':actual_times,'returned_rows':len(expected),
                        'result':[{'snapshot_at':row.split('|')[0],'dependents_count':int(row.split('|')[1])} for row in expected]}
                if len(report['cases']) in (0,1,2):
                    write(output/f"plan-case-{len(report['cases'])}.json", first_plan)
                report['cases'].append(case)
            print(json.dumps({'packages_done':name,'cases':len(report['cases'])}),flush=True)
        representative = max(report['cases'], key=lambda case:case['returned_rows'])
        db._send('SET plan_cache_mode=force_generic_plan; PREPARE history_probe(integer,varchar,date,date) AS '
                 f'SELECT snapshot_at,dependents_count FROM {parent} WHERE package_id=$1 AND version=$2 AND snapshot_at BETWEEN $3 AND $4 ORDER BY snapshot_at;')
        execution = f"EXECUTE history_probe({representative['package_id']},{db._literal(representative['version'])},{db._literal(low)},{db._literal(high)});"
        generic_first, generic_plan = explain(db,execution)
        generic_warm = [explain(db,execution)[0] for _ in range(10)]
        received = db._send(execution)
        assert len(received)==representative['returned_rows']
        assert [{'snapshot_at':row.split('|')[0],'dependents_count':int(row.split('|')[1])} for row in received]==representative['result']
        report['prepared_generic'] = {'name':representative['name'],'version':representative['version'],
                                      'first':generic_first,'warm':generic_warm}
        write(output/'plan-prepared-generic.json',generic_plan)
        db._send('DEALLOCATE history_probe;')
    cases=report['cases']
    report['summary']={'packages':len({c['package_id'] for c in cases}),'cases':len(cases),
                       'first_db_ms':stats([c['first']['db_total_ms'] for c in cases]),
                       'warm_db_ms':stats([r['db_total_ms'] for c in cases for r in c['warm']]),
                       'warm_planning_ms':stats([r['planning_ms'] for c in cases for r in c['warm']]),
                       'warm_execution_ms':stats([r['execution_ms'] for c in cases for r in c['warm']]),
                       'select_receive_ms':stats([v for c in cases for v in c['select_receive_ms']]),
                       'rows':stats([c['returned_rows'] for c in cases]),
                       'first_reads':stats([c['first']['shared_read_blocks'] for c in cases]),
                       'warm_reads':stats([r['shared_read_blocks'] for c in cases for r in c['warm']]),
                       'all_scans':dict(sum((Counter(c['first']['scan_nodes']) for c in cases),Counter()))}
    report.update(status='COMPLETE', elapsed_seconds=time.perf_counter()-started,
                  ended_at=datetime.now(timezone.utc).isoformat())
    write(output/'result.json',report)
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    run(args.config,args.output)
