"""Stop only the identified old restore, preserving committed candidate data."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--postgres-container', default='pickage-app-postgres-1')
    parser.add_argument('--user', default='pickage')
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.output_dir.resolve()
    original = json.loads((work / 'server-result.json').read_text())
    candidate = original['candidate']
    if not transfer.CANDIDATE_PATTERN.fullmatch(candidate):
        raise ValueError('Invalid candidate')
    if original['status'] != 'RUNNING' or original.get('current_phase') != 'restore_full_archive':
        raise ValueError('Original restore has advanced or stopped; reconcile before stopping')
    restore_file = work / (candidate + '.restore-status.json')
    restore = json.loads(restore_file.read_text())
    if not {'pre-data', 'data'}.issubset({p['name'] for p in restore['phases']}):
        raise ValueError('Data COPY is not recorded complete')
    helper = 'pickage-341-pgclient-' + candidate.rsplit('_', 1)[1]
    config = json.loads(subprocess.check_output(['docker', 'inspect', helper]))[0]
    mounts = config['Mounts']
    if not any(m['Source'] == str(work) and m['Destination'] == '/work' for m in mounts):
        raise ValueError('Old helper does not mount the expected archive')
    pids = [(original['pid'], 'server_pilot.py'), (restore['pid'], 'transfer.py')]
    for pid, script in pids:
        command = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
        if str(work) not in command or script not in command:
            raise ValueError('PID identity changed; refusing to signal')

    def sql(statement):
        result = subprocess.run(['docker', 'exec', '-i', args.postgres_container, 'psql', '-X',
                                 '-U', args.user, '-d', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'],
                                input=statement.encode(), capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        return result.stdout.decode().strip()

    def sessions():
        return json.loads(sql("SELECT coalesce(json_agg(row_to_json(a)), '[]'::json) FROM "
                              "(SELECT pid,application_name,state,query FROM pg_stat_activity "
                              f"WHERE datname='{candidate}') a;"))

    before = sessions()
    if any(s['application_name'] != 'pg_restore' for s in before):
        raise ValueError('Unexpected candidate clients; refusing to stop')
    # TABLE ATTACH is pre-data. This path deliberately resumes post-data only.
    # Query the candidate with the same guarded connection command.
    result = subprocess.run(['docker', 'exec', '-i', args.postgres_container, 'psql', '-X',
                             '-U', args.user, '-d', candidate, '-At', '-v', 'ON_ERROR_STOP=1'],
                            input=b"SELECT count(*) FROM pg_inherits h JOIN pg_class p ON p.oid=h.inhparent JOIN pg_namespace n ON n.oid=p.relnamespace WHERE n.nspname='public' AND p.relname='package_version_snapshot';",
                            capture_output=True, check=True)
    expected_leaves = sum('TABLE DATA vd193_reload_20260912_ready01 ' in line
                          for line in (work / 'archive-toc.txt').read_text().splitlines())
    if not expected_leaves or int(result.stdout.strip()) != expected_leaves:
        raise ValueError('Partition attachments are incomplete; post-data-only resume is not applicable')
    output.mkdir(parents=True, exist_ok=True)
    receipt_file = output / 'stop-receipt.json'
    if receipt_file.exists():
        raise ValueError('Stop receipt already exists; inspect it instead of stopping twice')
    transfer.write_json(output / 'original-server-result.json', original)
    transfer.write_json(output / 'original-restore-status.json', restore)
    receipt = {'status': 'STOPPING', 'candidate': candidate, 'started_at': transfer.utc_now(),
               'sessions_before': before, 'pids': pids, 'data_copy_repeated': False}
    transfer.write_json(receipt_file, receipt)
    frozen = []
    try:
        for pid, _ in pids:
            os.kill(pid, signal.SIGSTOP)
            frozen.append(pid)
        # Disconnect both pg_restore workers together; the server rolls back
        # their active statements. The database and committed objects remain.
        subprocess.run(['docker', 'rm', '-f', helper], check=True, capture_output=True)
        for _ in range(30):
            active = sessions()
            if not active:
                break
            if any(s['application_name'] != 'pg_restore' for s in active):
                raise ValueError('Unexpected connection appeared during stop')
            for row in active:
                sql(f"SELECT pg_terminate_backend({int(row['pid'])}) WHERE EXISTS "
                    f"(SELECT 1 FROM pg_stat_activity WHERE pid={int(row['pid'])} "
                    f"AND datname='{candidate}' AND application_name='pg_restore');")
            time.sleep(1)
        else:
            raise RuntimeError('Old restore connections did not quiesce')
        for pid in frozen:
            os.kill(pid, signal.SIGTERM)
            os.kill(pid, signal.SIGCONT)
        frozen.clear()
        for _ in range(30):
            running = []
            for pid, _ in pids:
                try:
                    # Zombies cannot run code or write another status file.
                    state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
                    if state != 'Z':
                        running.append(pid)
                except FileNotFoundError:
                    pass
            if not running:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Old runner PIDs have not exited')
        receipt['status'] = 'STOPPED'
        receipt['old_processes_exited'] = True
        receipt['sessions_after'] = sessions()
        receipt['completed_at'] = transfer.utc_now()
        for path, document in [(work / 'server-result.json', original), (restore_file, restore)]:
            document.update(status='STOPPED_FOR_ORDERED_RESUME', updated_at=transfer.utc_now(),
                            resume_directory=str(output), source_validation='DEFERRED_BY_USER')
            transfer.write_json(path, document)
    except BaseException as exc:
        receipt.update(status='NEEDS_REVIEW', error=str(exc))
        raise
    finally:
        for pid in frozen:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        transfer.write_json(receipt_file, receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
