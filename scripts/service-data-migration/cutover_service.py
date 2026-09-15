"""Promote the verified 341 candidate under the existing service DB name.

Keeps both databases and the current API image. No data copying or deletion.
Run only after the same API image was smoke-tested against the candidate.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from transfer import CANDIDATE_PATTERN, ROOT_TABLES, write_json, utc_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--candidate-db', required=True)
    parser.add_argument('--backup-db', required=True)
    args = parser.parse_args()
    candidate, backup = args.candidate_db, args.backup_db
    if not CANDIDATE_PATTERN.fullmatch(candidate) or not backup.startswith('pickage_before_341_') or not backup.replace('_', '').isalnum():
        raise ValueError('Unexpected database name')
    output = args.output_dir.resolve()
    if (output / 'cutover-result.json').exists():
        raise ValueError('A cutover record already exists; inspect it before retrying')
    if json.loads((output / 'probe-health.json').read_text()).get('status') != 'UP':
        raise ValueError('Candidate API probe did not pass')
    report = {'status': 'RUNNING', 'started_at': utc_now(), 'source_validation': 'DEFERRED_BY_USER',
              'candidate_before': candidate, 'service_database': 'pickage', 'backup_database': backup,
              'api_feature_smoke': 'BLOCKED_BY_EXISTING_IMAGE_MISSING_ROUTES', 'phases': []}
    started = time.monotonic()

    def save():
        report['updated_at'] = utc_now()
        report['elapsed_seconds'] = round(time.monotonic()-started, 3)
        write_json(output / 'cutover-result.json', report)

    def run(command, data=None):
        r = subprocess.run(command, input=data, capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode('utf-8', 'replace')[-3000:])
        return r.stdout.decode()

    def sql(db, statement):
        return run(['docker', 'exec', '-i', 'pickage-app-postgres-1', 'psql', '-X', '-U', 'pickage',
                    '-d', db, '-qAt', '-v', 'ON_ERROR_STOP=1'], statement.encode()).strip()

    def db_map():
        return json.loads(sql('postgres', "SELECT json_object_agg(datname,oid) FROM pg_database WHERE datname IN "
                             f"('pickage','{candidate}','{backup}');"))

    def health():
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/actuator/health', timeout=3) as r:
                    if json.load(r).get('status') == 'UP':
                        return
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError('API did not become healthy within 120 seconds')

    def phase(name, action):
        report['current_phase'] = name
        save()
        at = time.monotonic()
        result = action()
        report['phases'].append({'name': name, 'seconds': round(time.monotonic()-at, 3)})
        save()
        return result

    stopped = False
    before = None
    try:
        before = db_map()
        if set(before) != {'pickage', candidate}:
            raise ValueError('Expected original and candidate only; backup must not exist')
        report['database_oids_before'] = before
        for table in ROOT_TABLES:
            if sql('pickage', f'SELECT count(*) FROM public.{table};') != '0':
                raise ValueError('Original service now has data; reconcile it before cutover')
        if sql(candidate, "SELECT count(*) FROM flyway_schema_history WHERE success AND version IN ('1','2','3','4','5','6');") != '6':
            raise ValueError('Candidate migrations are incomplete')
        phase('stop_probe', lambda: run(['docker', 'stop', 'pickage-341-cutover-probe']))
        # Set before stopping so failure still attempts to restore availability.
        stopped = True
        phase('stop_api', lambda: run(['docker', 'stop', '--time', '30', 'pickage-app-api-1']))
        sql('postgres', f'ALTER DATABASE pickage ALLOW_CONNECTIONS false; ALTER DATABASE "{candidate}" ALLOW_CONNECTIONS false;')
        remaining = sql('postgres', f"SELECT count(*) FROM pg_stat_activity WHERE datname IN ('pickage','{candidate}');")
        if remaining != '0':
            raise ValueError('Unexpected connections remain; no databases renamed')
        phase('atomic_database_rename', lambda: sql('postgres',
              f'BEGIN; ALTER DATABASE pickage RENAME TO "{backup}"; '
              f'ALTER DATABASE "{candidate}" RENAME TO pickage; COMMIT;'))
        sql('postgres', 'ALTER DATABASE pickage ALLOW_CONNECTIONS true;')
        phase('start_api', lambda: run(['docker', 'start', 'pickage-app-api-1']))
        phase('api_health', health)
        after = db_map()
        if after != {'pickage': before[candidate], backup: before['pickage']}:
            raise ValueError('Database OIDs do not match the promotion')
        report['database_oids_after'] = after
        image = json.loads(run(['docker', 'inspect', 'pickage-app-api-1']))[0]
        original_image = json.loads((output / 'api-inspect.private.json').read_text())
        if image['Image'] != original_image['Image']:
            raise ValueError('API image unexpectedly changed')
        ip = image['NetworkSettings']['Networks']['pickage-app_default']['IPAddress']
        active = int(sql('postgres', f"SELECT count(*) FROM pg_stat_activity WHERE datid={before[candidate]} "
                         f"AND client_addr='{ip}'::inet AND application_name='PostgreSQL JDBC Driver';"))
        if active < 1:
            raise ValueError('API connections to promoted database not observed')
        report['api_connections_to_promoted_database'] = active
        with urllib.request.urlopen('https://j15a506.p.ssafy.io/actuator/health', timeout=15) as r:
            report['public_health'] = json.load(r)
        if report['public_health'].get('status') != 'UP':
            raise ValueError('Public health failed')
        report['status'] = 'SERVICE_DB_SWITCHED'
        report['current_phase'] = 'complete'
        report['completed_at'] = utc_now()
        report['backup_connections_allowed'] = False
    except BaseException as exc:
        report['error'] = str(exc)
        if stopped and before:
            try:
                run(['docker', 'stop', '--time', '30', 'pickage-app-api-1'])
                current = db_map()
                if current.get('pickage') == before[candidate]:
                    sql('postgres', 'ALTER DATABASE pickage ALLOW_CONNECTIONS false;')
                    sql('postgres', f'BEGIN; ALTER DATABASE pickage RENAME TO "{candidate}"; '
                        f'ALTER DATABASE "{backup}" RENAME TO pickage; COMMIT;')
                sql('postgres', f'ALTER DATABASE pickage ALLOW_CONNECTIONS true; ALTER DATABASE "{candidate}" ALLOW_CONNECTIONS true;')
                run(['docker', 'start', 'pickage-app-api-1'])
                health()
                report['status'] = 'ROLLED_BACK'
            except BaseException as rollback_error:
                report['status'] = 'ROLLBACK_NEEDS_ATTENTION'
                report['rollback_error'] = str(rollback_error)
        else:
            report['status'] = 'PREFLIGHT_FAILED'
        raise
    finally:
        save()
    print(json.dumps(report))


if __name__ == '__main__':
    main()
