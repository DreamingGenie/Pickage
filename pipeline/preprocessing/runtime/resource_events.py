"""Resource events shared by pinned and weekly bounded executions."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import threading
import time


@contextmanager
def resource_events(root, work_dir, run_id, limit):
    stop = threading.Event()
    started = time.monotonic()
    peak = 0

    def measure():
        nonlocal peak
        usage = shutil.disk_usage(root)
        used = usage.total - usage.free
        peak = max(peak, used)
        cgroup = Path('/sys/fs/cgroup/memory.current')
        memory = int(cgroup.read_text()) if cgroup.exists() else None
        state_path = Path(work_dir) / run_id / 'status.json'
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        print(json.dumps({'event': 'PIPELINE_RESOURCES', 'run_id': run_id,
            'status': state.get('status', 'STARTING'), 'phase': state.get('phase', 'INPUT'),
            'stages': state.get('stages', {}),
            'elapsed_seconds': round(time.monotonic() - started, 2),
            'scratch_used_bytes': used, 'scratch_peak_bytes': peak,
            'scratch_limit_bytes': limit, 'container_memory_bytes': memory}), flush=True)

    def monitor():
        while not stop.wait(60):
            measure()

    measure()
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)
        measure()
