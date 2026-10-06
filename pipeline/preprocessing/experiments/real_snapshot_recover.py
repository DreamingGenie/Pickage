"""Explicit recovery of an unfinished baseline; original envelopes stay immutable.

Reviewed reader, coordinator and final quality validation changes are recorded.
The recovery controller is recorded separately from the original producers.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from pipeline.preprocessing.experiments.real_snapshot_run import Experiment, atomic, now
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.contracts import code_contract, STAGES
from pipeline.preprocessing.orchestration.storage import BUCKET, host_lock, required, sha, verify_descriptor, save_state
from pipeline.preprocessing.orchestration.weekly_parent import publish_current
from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional, upload_outputs
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.preprocessing.version_dependents import historical_parallel as parallel
from pipeline.preprocessing.version_dependents import historical_parallel_input as inputs
from pipeline.preprocessing.version_dependents.historical_production_input import connection
from pipeline.preprocessing.orchestration.dependents_parallel import _load_weekly_views, _materialize_stage_outputs
from pipeline.preprocessing.orchestration.dependents import PREFIX as DEPENDENTS_PREFIX

READER = 'pipeline/preprocessing/version_dependents/historical_artifact.py'
COMPATIBILITY = 'pipeline/preprocessing/version_dependents/historical_parallel_input.py'
RECOVERY_ID = 'finalization-8gb-v3'
QUALITY = 'pipeline/preprocessing/version_dependents/historical_production_quality.py'
COORDINATOR = 'pipeline/preprocessing/version_dependents/historical_parallel.py'
PROOF_HELPER = 'pipeline/preprocessing/version_dependents/finalization_recovery.py'


def contract_changes(old, new):
    if old['runtime'] != new['runtime']:
        raise ValueError('Recovery runtime differs from original execution')
    changed = sorted(k for k in set(old['files']) | set(new['files']) if old['files'].get(k) != new['files'].get(k))
    if set(changed) - {READER, COMPATIBILITY, QUALITY, COORDINATOR, PROOF_HELPER}:
        raise ValueError('Recovery only permits reviewed reader/input validation changes: ' + str(changed))
    return changed


def prepare_plan(experiment):
    root = experiment.root
    request = experiment.request('baseline')
    prefix = runner.run_prefix(request)
    envelope = required(experiment.local, BUCKET, prefix + '/request.json')
    old = json.loads(envelope)
    if old['request'] != request or old['work_dir'] != str((root / 'w' / request['run_id']).resolve()):
        raise ValueError('Original request identity differs')
    current = code_contract()
    changed = contract_changes(old['code_contract'], current)
    attempt = root / 'w' / request['run_id'] / 'dependents' / 'parallel-attempt'
    candidates = list(attempt.glob('prep-*/input/input_manifest.json'))
    if len(candidates) != 1:
        raise ValueError('Recovery requires exactly one prepared input manifest')
    manifest_path = candidates[0]
    prepared_manifest = parallel._read_json(manifest_path)
    proof = {'format': 'reader-limit-input-recovery-v1',
        'manifest_path': str(manifest_path.resolve()), 'manifest_sha256': file_sha256(manifest_path),
        'previous_contract': prepared_manifest['generation_contract'], 'new_contract': inputs.contract()}
    proof_path = root / (RECOVERY_ID + '-input-proof.json')
    proof_body = json_bytes(proof)
    if proof_path.exists():
        if proof_path.read_bytes() != proof_body:
            raise ValueError('Input compatibility proof changed')
    else:
        with proof_path.open('xb') as stream: stream.write(proof_body)
    os.environ['PICKAGE_INPUT_RECOVERY_PROOF'] = str(proof_path)
    os.environ['PICKAGE_INPUT_RECOVERY_PROOF_SHA256'] = sha(proof_body)
    finalization_proof = None
    run_root = attempt / 'parallel-run'
    parallel_plan_path = run_root / 'run_plan.json'
    if parallel_plan_path.exists():
        old_parallel = parallel._read_json(parallel_plan_path)
        checkpoints = {f'partitions/{int(p):03d}/complete.json':
            file_sha256(run_root / f'partitions/{int(p):03d}/complete.json') for p in old_parallel['partitions']}
        from pipeline.preprocessing.version_dependents import finalization_recovery
        final_proof = {'format': 'finalization-recovery-v1', 'run_root': str(run_root.resolve()),
            'plan_sha256': file_sha256(parallel_plan_path), 'previous_contract': old_parallel['generation_contract'],
            'new_contract': parallel.contract(), 'checkpoints': checkpoints,
            'helper_sha256': file_sha256(Path(finalization_recovery.__file__))}
        final_path = root / (RECOVERY_ID + '-finalization-proof.json')
        final_body = json_bytes(final_proof)
        if final_path.exists():
            if final_path.read_bytes() != final_body: raise ValueError('Finalization proof changed')
        else:
            with final_path.open('xb') as stream: stream.write(final_body)
        os.environ['PICKAGE_FINALIZATION_RECOVERY_PROOF'] = str(final_path)
        os.environ['PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256'] = sha(final_body)
        finalization_proof = finalization_recovery.verify(run_root, old_parallel, parallel.contract())
    checkpoints = {name: sha(required(experiment.local, BUCKET, prefix + '/stages/' + name + '.json'))
                   for name in STAGES if name != 'dependents'}
    value = {'format': 'dependents-reader-recovery-v1', 'recovery_id': RECOVERY_ID,
        'request': request, 'original_envelope_sha256': sha(envelope),
        'original_code_contract_sha256': sha(json_bytes(old['code_contract'])),
        'new_code_contract': current, 'changed_generator_files': changed,
        'controller_sha256': file_sha256(Path(__file__)), 'checkpoints': checkpoints,
        'prepared_dir': str(manifest_path.parent), 'prepared_manifest_sha256': file_sha256(manifest_path),
        'input_compatibility_proof': {'path': str(proof_path), 'sha256': sha(proof_body)},
        'finalization_proof': finalization_proof,
        'finalization_settings': {'threads': 2, 'memory_limit': '8GB', 'max_temp_size': '100GB'},
        'original_identity_sha256': file_sha256(attempt / 'identity.json'),
        'original_producer_inventory_sha256': file_sha256(root / 'source-files.json'),
        'scope': 'REUSE_VERIFIED_FIVE_STAGES_AND_PREPARED_DEPENDENTS', 'server_writes': False}
    path = root / (RECOVERY_ID + '-plan.json')
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError('Recovery plan or pinned inputs changed')
    else:
        atomic(path, value)
    return value


def source_files(attempt, identity):
    """Use the original content-addressed cache, never silently substitute input."""
    result = {}
    for table, records in identity['files'].items():
        paths = []
        for record in records:
            path = attempt.parent / ('targets.parquet' if table == 'targets' else 'cache/' + record['sha256'] + '.parquet')
            if not path.is_file() or path.stat().st_size != record['bytes'] or file_sha256(path) != record['sha256']:
                raise ValueError('Original source cache changed: ' + str(path))
            paths.append(path)
        result[table] = paths[0] if table == 'targets' else paths
    return result


def publish_dependents(s3, request, completed, attempt, result, receipt_ref, files, prepared, manifest):
    prefix = f"{DEPENDENTS_PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}"
    key = prefix + '/run_manifest.json'
    identity = {'request': request, 'population_manifest_sha256': completed['package_version']['manifest_sha256']}
    existing = read_optional(s3, BUCKET, key)
    if existing is None:
        options = request['options']
        with connection(attempt / ('recover-export-' + uuid.uuid4().hex[:8] + '.duckdb'),
                threads=options['threads'], memory_limit='8GB', max_temp_size='100GB') as con:
            _load_weekly_views(con, files)
            directory, schemas, quality = _materialize_stage_outputs(con, files=files, root=attempt,
                prepared=prepared, run_result=result, snapshot=request['snapshot'], metadata=manifest['weekly_metadata'])
        rows = upload_outputs(s3, BUCKET, prefix + '/attempts/' + RECOVERY_ID, directory, workers=2)
        for row in rows:
            row.update(next(s for s in schemas if row['key'].endswith('/' + s['path'])))
        body = json_bytes({'format_version': 1, 'dataset': 'version-dependents-single', 'status': 'PASSED',
            'identity': identity, 'run_id': request['run_id'], 'snapshot': request['snapshot'],
            'files': rows, 'quality': quality, 'db_loaded': False, 'engine': 'historical_parallel_cpu_weighted',
            'metric': 'DISTINCT_SOURCE_PACKAGE_VERSION_PER_TARGET_VERSION_AND_SNAPSHOT',
            'dependency_kind': 'dependencies', 'recovery': receipt_ref})
        put_immutable(s3, BUCKET, key, body)
    else:
        body = existing[0]
    producer = json.loads(body)
    if producer.get('identity') != identity or producer.get('recovery') != receipt_ref:
        raise ValueError('Existing dependents producer is outside this recovery')
    marker = json_bytes({'manifest_sha256': sha(body)})
    put_immutable(s3, BUCKET, prefix + '/_SUCCESS', marker)
    descriptor = {'stage': 'dependents', 'run_id': request['run_id'], 'snapshot': request['snapshot'],
        'bucket': BUCKET, 'prefix': prefix, 'manifest_key': key, 'manifest_sha256': sha(body),
        'marker_key': prefix + '/_SUCCESS', 'marker_sha256': sha(marker), 'files': producer['files'],
        'quality': producer['quality'], 'metadata': {'snapshot_count': 1, 'recovery': receipt_ref}}
    verify_descriptor(s3, descriptor, workers=2)
    return descriptor


def recover_baseline(experiment, request):
    plan = prepare_plan(experiment)
    root, s3 = experiment.root, experiment.local
    local = root / 'w' / request['run_id']
    prefix = runner.run_prefix(request)
    attempt = local / 'dependents' / 'parallel-attempt'
    prepared = Path(plan['prepared_dir'])
    digest = plan['prepared_manifest_sha256']
    receipt_key = prefix + '/recoveries/' + RECOVERY_ID + '.json'
    receipt_body = json_bytes(plan)
    receipt_ref = {'key': receipt_key, 'sha256': sha(receipt_body)}
    with host_lock(s3):
        state = json.loads((local / 'status.json').read_bytes())
        state.update(status='RUNNING', phase='dependents', error=None, recovery=receipt_ref)
        state['stages']['dependents'].update(status='RUNNING', error=None, started_at=now(),
            attempt=state['stages']['dependents'].get('attempt', 0) + 1, finished_at=None)
        save_state(s3, prefix, local, state)
        put_immutable(s3, BUCKET, receipt_key, receipt_body)
        completed = {}
        try:
            with experiment.phase('baseline:recovery:VERIFY_COMPLETED_STAGES'):
                for name, expected in plan['checkpoints'].items():
                    body = required(s3, BUCKET, prefix + '/stages/' + name + '.json')
                    if sha(body) != expected:
                        raise ValueError('Completed checkpoint changed: ' + name)
                    descriptor = json.loads(body)
                    if (descriptor['stage'],descriptor['run_id'],descriptor['snapshot']) != (name,request['run_id'],request['snapshot']):
                        raise ValueError('Completed checkpoint identity differs')
                    verify_descriptor(s3, descriptor, workers=2)
                    completed[name] = descriptor
            marker = read_optional(s3, BUCKET, prefix + '/_SUCCESS')
            if marker is not None:
                body = required(s3, BUCKET, prefix + '/run_manifest.json')
                bundle = json.loads(body)
                if bundle.get('recovery') != receipt_ref or json.loads(marker[0]) != {'manifest_sha256':sha(body)}:
                    raise ValueError('Existing complete bundle differs from recovery')
                for descriptor in bundle['stages'].values(): verify_descriptor(s3, descriptor, workers=2)
                publish_current(s3, request, body, replay=True)
            else:
                with experiment.phase('baseline:recovery:VERIFY_SOURCE_CACHE'):
                    identity_path = attempt / 'identity.json'
                    if file_sha256(identity_path) != plan['original_identity_sha256']:
                        raise ValueError('Original dependents identity changed')
                    identity = json.loads(identity_path.read_bytes())
                    files = source_files(attempt, identity)
                    manifest = inputs._manifest(prepared, digest)
                    if (manifest['source_manifest_sha256'] != sha256(identity)
                            or manifest['calendar'] != [{'snapshot_at': request['snapshot'], 'snapshot_timestamp': request['snapshot_timestamp']}]):
                        raise ValueError('Prepared source identity differs')
                options = request['options']
                settings = plan['finalization_settings']
                with experiment.phase('baseline:dependents:VERIFY_INPUT_AND_PARALLEL_COMPUTE'):
                    run_dir = attempt / 'parallel-run'
                    result = parallel.run(prepared_dir=prepared, manifest_sha256=digest, output=run_dir,
                        workers=2, **settings, allow_full_selected=True, history_layout='grouped', resume=run_dir.exists())
                    if result['run_status'] != 'COMPLETE': raise RuntimeError('Parallel recovery did not complete')
                with experiment.phase('baseline:dependents:VERIFY_OUTPUT'):
                    parallel.verify_run(run_dir=run_dir, manifest_sha256=result['run_manifest_sha256'], **settings)
                with experiment.phase('baseline:dependents:PUBLISH'):
                    completed['dependents'] = publish_dependents(s3, request, completed, attempt, result,
                        receipt_ref, files, prepared, manifest)
                    put_immutable(s3, BUCKET, prefix + '/stages/dependents.json', json_bytes(completed['dependents']))
                    if code_contract() != plan['new_code_contract'] or file_sha256(Path(__file__)) != plan['controller_sha256']:
                        raise ValueError('Recovery generator changed during execution')
                    for descriptor in completed.values(): verify_descriptor(s3, descriptor, workers=2)
                    bundle = {'format_version':1, 'dataset':'curated-bundle','status':'COMPLETE',
                        'scope':'RAW_TO_CURATED_ONLY','request':request,
                        'code_contract_sha256':sha(json_bytes(plan['new_code_contract'])), 'stages':completed,
                        'calculation_complete':True,'db_loaded':False,
                        'consumer_contract':'pipeline/preprocessing/orchestration/CONTRACT.md','recovery':receipt_ref}
                    body = json_bytes(bundle)
                    put_immutable(s3, BUCKET, prefix + '/run_manifest.json', body)
                    put_immutable(s3, BUCKET, prefix + '/_SUCCESS', json_bytes({'manifest_sha256':sha(body)}))
                    publish_current(s3, request, body)
            state['stages']['dependents'].update(status='COMPLETE', finished_at=now(), error=None, recovery=receipt_ref)
            state.update(status='COMPLETE',phase='COMPLETE',finished_at=now(),error=None)
            save_state(s3,prefix,local,state)
            atomic(local/'bundle.json',bundle)
            return bundle
        except BaseException as error:
            state['stages']['dependents'].update(status='FAILED',error={'type':type(error).__name__,'message':str(error)})
            state.update(status='FAILED',phase='dependents',error={'type':type(error).__name__,'message':str(error)},finished_at=now())
            save_state(s3,prefix,local,state)
            raise


class RecoveryExperiment(Experiment):
    def copy(self, label, rows):
        if label == 'baseline':
            print(now(), 'REUSE_EXISTING_BASELINE_INPUT; no source collection or preprocessing repeated', flush=True)
            return
        return super().copy(label, rows)

    def preprocess(self, label, request):
        if label == 'baseline': return recover_baseline(self,request)
        return super().preprocess(label,request)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args()
    root=Path(args.root)
    import msvcrt
    with (root/'experiment.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1): handle.write(b'0'); handle.flush()
        handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        experiment=RecoveryExperiment(root)
        if args.prepare:
            value=prepare_plan(experiment)
            print(json.dumps({'recovery_id':value['recovery_id'],'changed_files':value['changed_generator_files'],
                              'retained_stages':list(value['checkpoints']),'prepared_dir':value['prepared_dir']}))
        else: experiment.run()


if __name__ == '__main__': main()
