"""Read-only weekly-batch observations; violations stop only the experiment."""
import json
from pathlib import Path
import re
import subprocess
import time

from .monitor_container import resolve_host_cgroup

WEEKLY = 'pickage-weekly-run'
CHECKPOINT = Path('/srv/pickage/ingest-work/downloads-weekly/2026-09-14/raw/run=2026-09-15/checkpoint.sqlite')


def pressure(resource):
    line = Path('/proc/pressure/' + resource).read_text().splitlines()[0]
    return float(dict(item.split('=') for item in line.split()[1:])['avg10'])


def observe():
    info = json.loads(subprocess.check_output(['docker', 'inspect', WEEKLY], text=True, timeout=10))[0]
    state = info['State']
    if not state['Running']:
        raise RuntimeError('WEEKLY_NOT_RUNNING')
    logs = subprocess.check_output(['docker', 'logs', '--tail', '15', WEEKLY],
                                   text=True, stderr=subprocess.STDOUT, timeout=10)
    phases = re.findall(r'\[weekly\] (\w+): (시작|끝|실패)', logs)
    cgroup = resolve_host_cgroup(state['Pid'])
    cpu = dict(line.split() for line in (cgroup / 'cpu.stat').read_text().splitlines())
    memory = {
        line.split(':')[0]: int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    anon = dict(line.split() for line in (cgroup / 'memory.stat').read_text().splitlines())
    return {'time': time.time(), 'monotonic': time.monotonic(), 'container_id': info['Id'],
            'restarts': info['RestartCount'], 'phase': list(phases[-1]) if phases else None,
            'checkpoint_age_seconds': time.time() - CHECKPOINT.stat().st_mtime,
            'weekly_cpu_usage_usec': int(cpu['usage_usec']), 'weekly_anon_bytes': int(anon['anon']),
            'available_memory_bytes': memory['MemAvailable'],
            'io_pressure_avg10': pressure('io'), 'memory_pressure_avg10': pressure('memory')}


def violation(current, previous=None):
    if current['phase'] != ['downloads_weekly', '시작']:
        return 'WEEKLY_PHASE_CHANGED'
    if current['checkpoint_age_seconds'] > 120:
        return 'WEEKLY_CHECKPOINT_STALE'
    if current['available_memory_bytes'] < 5 * 1024**3:
        return 'AVAILABLE_MEMORY_BELOW_5G'
    if current['weekly_anon_bytes'] > 1024**3:
        return 'WEEKLY_MEMORY_INCREASED'
    if current['io_pressure_avg10'] > 10 or current['memory_pressure_avg10'] > 1:
        return 'HOST_RESOURCE_PRESSURE'
    if previous:
        if current['container_id'] != previous['container_id'] or current['restarts'] != previous['restarts']:
            return 'WEEKLY_CONTAINER_CHANGED'
        elapsed = current['monotonic'] - previous['monotonic']
        if elapsed > 0:
            cores = (current['weekly_cpu_usage_usec'] - previous['weekly_cpu_usage_usec']) / 1_000_000 / elapsed
            if cores > 0.5:
                return 'WEEKLY_CPU_INCREASED'
    return None
