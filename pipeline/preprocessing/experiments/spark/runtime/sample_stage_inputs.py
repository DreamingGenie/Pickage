"""Prepare deterministic package-scoped inputs; never publish service datasets."""
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

SEED = 'pickage-real-sample-v1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''): h.update(block)
    return h.hexdigest()


def sample_manifest(source_manifest, output_dir, code_identity, limit=10000):
    import duckdb
    from pipeline.preprocessing.curated.repository import normalize_repository_url
    from pipeline.preprocessing.experiments.spark.job import verify_manifest
    if type(limit) is not int or limit < 2:
        raise ValueError('sample size must be at least 2 packages')
    source_path = Path(source_manifest).resolve(strict=True)
    source = json.loads(source_path.read_bytes())
    verify_manifest(source)
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    scratch = root/'scratch'; scratch.mkdir()
    stages = copy.deepcopy(source['stages'])
    produced, counts = [], {}
    with duckdb.connect(config={'memory_limit': '1GB', 'threads': 1}) as c:
        c.execute('SET temp_directory=?', [str(scratch)])
        def view(name, files, csv=False):
            values = files if isinstance(files, list) else [files]
            if csv:
                c.read_csv(values[0], header=True, all_varchar=True).create_view(name)
            else:
                c.read_parquet(values, hive_partitioning=False).create_view(name)
        def emit(label, query, csv=False):
            path = root/label; path.parent.mkdir(parents=True, exist_ok=True)
            fmt = "FORMAT CSV, HEADER true" if csv else "FORMAT PARQUET, COMPRESSION ZSTD"
            c.execute(f'COPY ({query}) TO ? ({fmt})', [str(path)])
            produced.append(path)
            if not csv:
                counts[label] = c.execute('SELECT count(*) FROM read_parquet(?,hive_partitioning=false)', [str(path)]).fetchone()[0]
            return str(path)
        dep, dl, repo, snap = (stages[k] for k in ('dependents','downloads','repository','package_snapshot'))
        view('packages',dep['files']['package'])
        view('dep_targets',dep['files']['targets'])
        view('dl_targets',dl['target_file'],csv=True)
        c.execute('CREATE TEMP TABLE target_names AS SELECT name FROM dep_targets UNION SELECT name FROM dl_targets')
        # Two strata make target calculations nontrivial without claiming a
        # population-representative random sample. Every ordering is explicit.
        c.execute('CREATE TEMP TABLE selected_names AS SELECT p.name FROM packages p SEMI JOIN target_names t USING(name) ORDER BY sha256(? || p.name),p.name LIMIT ?', [SEED, limit//2])
        n = c.execute('SELECT count(*) FROM selected_names').fetchone()[0]
        c.execute('INSERT INTO selected_names SELECT p.name FROM packages p ANTI JOIN selected_names s USING(name) ORDER BY sha256(? || p.name),p.name LIMIT ?', [SEED,limit-n])
        names = [r[0] for r in c.execute('SELECT name FROM selected_names ORDER BY name').fetchall()]
        if len(names)!=limit: raise ValueError('Not enough eligible packages for requested sample')
        print('SAMPLE_SELECTED', len(names), flush=True)
        c.execute('CREATE TEMP TABLE selected_packages AS SELECT p.* FROM packages p SEMI JOIN selected_names USING(name)')
        package = emit('package.parquet','SELECT * FROM selected_packages')
        ids = emit('package_ids.parquet','SELECT package_id,name FROM selected_packages')
        view('raw_versions',stages['package_version']['versions'])
        raw = emit('versions_full.parquet','SELECT r.* FROM raw_versions r SEMI JOIN selected_names s ON r.Name=s.name')
        view('raw_requirements',stages['package_version']['requirements'])
        requirements = emit('requirements.parquet','SELECT r.* FROM raw_requirements r SEMI JOIN selected_names s ON r.Name=s.name')
        view('versions',dep['files']['version'])
        versions = emit('version.parquet','SELECT v.* FROM versions v SEMI JOIN selected_packages p USING(package_id)')
        print('SAMPLE_VERSIONS',counts['versions_full.parquet'],counts['version.parquet'],flush=True)
        stages['package_version'].update(versions=[raw],requirements=[requirements],previous_ids=[ids])
        dep_targets = emit('dependents_targets.parquet','SELECT d.* FROM dep_targets d SEMI JOIN selected_names USING(name)')
        if not counts['dependents_targets.parquet']: raise ValueError('Empty sampled dependents target set')
        dep['files'].update(package=[package],version=[versions],versions_full=[raw],requirements=[requirements],targets=dep_targets)
        dl_target = emit('downloads_targets.csv','SELECT d.* FROM dl_targets d SEMI JOIN selected_names USING(name)',csv=True)
        view('dl_status',dl['status_file'])
        status = emit('downloads_status.parquet','SELECT d.* FROM dl_status d SEMI JOIN selected_names USING(name)')
        daily = []
        for index,path in enumerate(dl['daily_files']):
            date_match = re.search(r'(?:^|/)date=(\d{4}-\d{2}-\d{2})/',Path(path).as_posix())
            if not date_match: raise ValueError('Source daily input has no date partition')
            view('one_daily',path)
            daily.append(emit('daily/date='+date_match[1]+f'/part-{index:04d}.parquet', 'SELECT d.* FROM one_daily d SEMI JOIN selected_names USING(name)'))
            c.execute('DROP VIEW one_daily')
        dl.update(package_files=[package],daily_files=daily,target_file=dl_target,status_file=status,expected_package_rows=limit)
        view('selected_raw',raw)
        keys = set()
        for (url,) in c.execute('SELECT DISTINCT source_repo FROM selected_raw WHERE source_repo IS NOT NULL').fetchall():
            normalized = normalize_repository_url(url)
            if normalized:
                u = urlsplit(normalized); path=u.path.lstrip('/')
                if u.hostname in ('github.com','gitlab.com'):
                    keys.add(u.hostname+'|'+(path.lower() if u.hostname=='github.com' else path))
        c.execute('CREATE TEMP TABLE repo_keys(key VARCHAR)')
        if keys: c.executemany('INSERT INTO repo_keys VALUES (?)', [(k,) for k in sorted(keys)])
        view('projects',repo['files']['projects'])
        projects = emit('projects.parquet', """SELECT p.* FROM projects p SEMI JOIN repo_keys k ON
          CASE upper(p.Type) WHEN 'GITHUB' THEN 'github.com|' || lower(p.project_name)
          WHEN 'GITLAB' THEN 'gitlab.com|' || p.project_name END = k.key""")
        repo['files'] = {'package':[package],'version':[versions],'versions_full':[raw],'projects':[projects]}
        repo['counts'] = {'package':limit,'version':counts['version.parquet'], 'versions_full':counts['versions_full.parquet'],'projects':counts['projects.parquet']}
        # Keep this as a sample input descriptor; do not impersonate an official
        # producer manifest or overwrite the source lineage embedded in rows.
        group_paths = {'population_files':[package]}
        for group in ('download_files','repository_files','selection_files'):
            view('snapshot_source',snap[group])
            p = emit('snapshot/'+group+'.parquet','SELECT x.* FROM snapshot_source x SEMI JOIN selected_packages USING(package_id)')
            c.execute('DROP VIEW snapshot_source')
            group_paths[group]=[p]
        interval = copy.deepcopy(dl['interval'])
        interval['snapshot_timestamp']=source['source_request']['snapshot_timestamp']
        lineage = dl['lineage']
        snapshot_descriptor = {'scope':'SAMPLED_EXPERIMENT_INPUT', 'source_manifest_sha256':sha(source_path),
           'candidate':{'policy_sha256':lineage['policy_sha256']},
           'downloads':{'input_manifest_sha256':lineage['input_manifest_sha256'], 'policy_sha256':lineage['aggregation_policy_sha256']}, 'detail_files':[]}
        for group,paths in group_paths.items():
            snapshot_descriptor[group]=[{'path':p,'row_count':limit,'sha256':sha(p)} for p in paths]
        snap.update(**group_paths,population_rows=limit,detail_files=[],interval=interval,input_manifest=snapshot_descriptor)
        snap['input_manifest_sha256']=hashlib.sha256(json.dumps(snapshot_descriptor,sort_keys=True).encode()).hexdigest()
        target_rows = c.execute('SELECT count(*) FROM selected_names SEMI JOIN target_names USING(name)').fetchone()[0]
    inventory = [{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(produced))]
    sample = {'package_rows':limit,'seed':SEED,'sampling':'half_target_union_then_hash_order_fill',
              'selection_sha256':hashlib.sha256(json.dumps(names,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
              'target_union_packages':target_rows,'row_counts':counts,'all_versions_of_selected_packages':True,
              'graph_scope':'sampled_importers_only; not global dependents',
              'detail_quality_scope':'no unrelated full-population download detail files',
              'production_performance_claim':False}
    identity = {'source_manifest_sha256':sha(source_path),'sample':sample,'files':[(r['sha256'],r['bytes']) for r in inventory]}
    result = {'format_version':1,'scope':'FIXED_STAGE_INPUT_COMPARISON','source_request':source['source_request'],
              'source_manifest_sha256':sha(source_path),'code_identity':code_identity,'sample':sample,
              'input_identity':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
              'stages':stages,'input_files':inventory,'production_writes':False,'db_loaded':False}
    destination = root/'sample-manifest.json'
    with destination.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print('SAMPLE_READY',limit,'files',len(inventory),'bytes',sum(r['bytes'] for r in inventory),flush=True)
    return destination