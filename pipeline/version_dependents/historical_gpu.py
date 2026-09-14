"""Opt-in resolver experiment; never publishes counts or modifies production state.

NumPy and PyTorch are optional experiment dependencies. Normal production imports
do not load this module. npm semantics are normalized by a separate Node adapter.
"""
from __future__ import annotations

from pathlib import Path
import time


NORMALIZER = Path(__file__).with_name('historical_gpu_normalize.cjs')


def validate_plan(plan):
    n = plan['snapshot_count']
    versions, births, lookups = plan['rank_to_version'], plan['birth_by_rank'], plan['lookups']
    if type(n) is not int or not 1 <= n <= 4096 or type(plan['known_package']) is not bool:
        raise ValueError('Invalid calendar or known_package')
    if len(versions) != len(births) or len(versions) > 100000 or len(lookups) > 2048:
        raise ValueError('Experimental input bound exceeded')
    if len(set(versions)) != len(versions) or any(not isinstance(v, str) for v in versions):
        raise ValueError('Invalid ranked versions')
    if any(type(b) is not int or not 0 <= b < n for b in births):
        raise ValueError('Invalid birth_by_rank')
    if not plan['known_package'] and births:
        raise ValueError('Unmapped package cannot have candidates')
    if plan['earliest_accepted_birth'] != min(births, default=n):
        raise ValueError('Invalid earliest_accepted_birth')
    for item in lookups:
        if item['fixed_status'] and item['spans']:
            raise ValueError('Fixed status cannot have rank spans')
        previous_end = -1
        for lo, hi in item['spans']:
            if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(births):
                raise ValueError('Invalid rank span')
            if lo <= previous_end:
                raise ValueError('Rank spans must be sorted, disjoint and nonadjacent')
            previous_end = hi


def unique_spans(plan):
    """Equivalent range results share work on both CPU and GPU paths."""
    validate_plan(plan)
    rows, indices, seen = [], [], {}
    for item in plan['lookups']:
        key = tuple(tuple(span) for span in item['spans'])
        if key not in seen:
            seen[key] = len(rows)
            rows.append(key)
        indices.append(seen[key])
    return rows, indices


def cpu_ranks(plan):
    """Rightmost eligible rank via a min-birth segment tree, not a Q x V scan."""
    import numpy as np

    started = time.perf_counter()
    spans, mapping = unique_spans(plan)
    n, births = plan['snapshot_count'], plan['birth_by_rank']
    size = 1 << max(0, len(births) - 1).bit_length()
    tree = [n] * (2 * size)
    tree[size:size + len(births)] = births
    for i in range(size - 1, 0, -1):
        tree[i] = min(tree[2 * i], tree[2 * i + 1])

    def rightmost(node, left, right, lo, hi, day):
        if right <= lo or left >= hi or tree[node] > day:
            return -1
        if right - left == 1:
            return left
        middle = (left + right) // 2
        found = rightmost(2 * node + 1, middle, right, lo, hi, day)
        return found if found >= 0 else rightmost(2 * node, left, middle, lo, hi, day)

    values = np.full((len(spans), n), -1, dtype=np.int64)
    for row, intervals in enumerate(spans):
        prior = -1
        for day in range(n):
            winner = prior
            for lo, hi in reversed(intervals):
                if hi <= prior + 1:
                    break
                candidate = rightmost(1, 0, size, max(lo, prior + 1), hi, day)
                if candidate >= 0:
                    winner = candidate
                    break
            values[row, day] = prior = winner
    output = values[mapping] if mapping else np.empty((0, n), dtype=np.int64)
    return output, {'seconds': time.perf_counter() - started,
                    'unique_span_sets': len(spans), 'algorithm': 'min-birth-segment-tree'}


def gpu_ranks(plan, *, workspace_mib=128, device_index=0):
    """Chunked integer CUDA reductions with explicit transfer and memory metrics."""
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; no CPU fallback in the GPU experiment')
    if type(workspace_mib) is not int or not 1 <= workspace_mib <= 512:
        raise ValueError('workspace_mib must be between 1 and 512')
    if type(device_index) is not int or not 0 <= device_index < torch.cuda.device_count():
        raise ValueError('Invalid CUDA device index')
    started = time.perf_counter()
    spans, mapping = unique_spans(plan)
    n, births = plan['snapshot_count'], plan['birth_by_rank']
    v, q = len(births), len(spans)
    width = max((len(s) for s in spans), default=0)
    # Account for mask temporaries, int64 masked ranks, date values and cummax indices.
    row_bytes = max(1, 16 * v + 32 * n + 16 * width)
    chunk = max(1, min(q or 1, workspace_mib * 1024 ** 2 // row_bytes))
    if row_bytes > workspace_mib * 1024 ** 2:
        raise ValueError('One requirement exceeds the workspace budget')
    lo = np.zeros((q, width), dtype=np.int64)
    hi = np.zeros((q, width), dtype=np.int64)
    for row, intervals in enumerate(spans):
        for col, (lower, upper) in enumerate(intervals):
            lo[row, col], hi[row, col] = lower, upper
    result = np.full((q, n), -1, dtype=np.int64)
    preparation = time.perf_counter() - started
    device = torch.device('cuda', device_index)
    with torch.cuda.device(device), torch.inference_mode():
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
        baseline_allocated = torch.cuda.memory_allocated(device)
        transfer_started = time.perf_counter()
        ranks = torch.arange(v, dtype=torch.int64, device=device)
        birth_gpu = torch.tensor(births, dtype=torch.int64, device=device)
        lower_gpu = torch.from_numpy(lo).to(device)
        upper_gpu = torch.from_numpy(hi).to(device)
        torch.cuda.synchronize(device)
        h2d = time.perf_counter() - transfer_started
        compute, d2h = 0.0, 0.0
        for start in range(0, q, chunk):
            end = min(q, start + chunk)
            tick = time.perf_counter()
            mask = torch.zeros((end - start, v), dtype=torch.bool, device=device)
            for col in range(width):
                mask |= ((ranks[None, :] >= lower_gpu[start:end, col, None]) &
                         (ranks[None, :] < upper_gpu[start:end, col, None]))
            eligible = torch.where(mask, ranks[None, :], -1)
            by_birth = torch.full((end - start, n), -1, dtype=torch.int64, device=device)
            if v:
                by_birth.scatter_reduce_(1, birth_gpu[None, :].expand(end - start, -1),
                                         eligible, reduce='amax', include_self=True)
            cumulative = torch.cummax(by_birth, dim=1).values
            torch.cuda.synchronize(device)
            compute += time.perf_counter() - tick
            tick = time.perf_counter()
            result[start:end] = cumulative.cpu().numpy()
            torch.cuda.synchronize(device)
            d2h += time.perf_counter() - tick
            del mask, eligible, by_birth, cumulative
        peak = torch.cuda.max_memory_allocated(device)
        reserved = torch.cuda.max_memory_reserved(device)
        output = result[mapping] if mapping else np.empty((0, n), dtype=np.int64)
    return output, {'seconds': time.perf_counter() - started, 'host_preparation_seconds': preparation,
                    'h2d_seconds': h2d, 'compute_seconds': compute, 'd2h_seconds': d2h,
                    'peak_allocated_bytes': peak, 'baseline_allocated_bytes': baseline_allocated,
                    'peak_reserved_bytes': reserved, 'chunk_rows': chunk, 'workspace_mib': workspace_mib,
                    'unique_span_sets': q, 'algorithm': 'cuda-scatter-amax-cummax',
                    'device': torch.cuda.get_device_name(device), 'torch': torch.__version__,
                    'cuda_build': torch.version.cuda}


def intervals_from_ranks(plan, ranks):
    """Restore the existing interval/status contract, including unresolved dates."""
    import numpy as np

    validate_plan(plan)
    n, lookups, versions = plan['snapshot_count'], plan['lookups'], plan['rank_to_version']
    if ranks.shape != (len(lookups), n) or ranks.dtype.kind not in 'iu':
        raise ValueError('Invalid rank result shape or dtype')
    if np.any(ranks < -1) or np.any(ranks >= len(versions)):
        raise ValueError('Invalid result rank')
    output = []
    for item, row in zip(lookups, ranks):
        intervals = []
        for day, rank in enumerate(row):
            if item['fixed_status']:
                status, version, normalized = item['fixed_status'], None, None
            else:
                normalized = item['normalized_range']
                version = versions[int(rank)] if rank >= 0 else None
                status = ('RESOLVED' if version is not None else
                          'UNMAPPED_TARGET_PACKAGE' if not plan['known_package'] else
                          'NO_ELIGIBLE_TARGET' if day < plan['earliest_accepted_birth'] else
                          'NO_SATISFYING_VERSION')
            key = (status, version, normalized)
            prior = intervals[-1] if intervals else None
            if prior and (prior['status'], prior['target_version'], prior['normalized_range']) == key:
                prior['end_index'] = day + 1
            else:
                intervals.append({'start_index': day, 'end_index': day + 1, 'status': status,
                                  'normalized_range': normalized, 'target_version': version})
        output.append({'requirement': item['requirement'], 'intervals': intervals})
    return output
