import json
from pathlib import Path
import tempfile
import unittest
from .historical_gpu_parallel_benchmark import overlap


class OverlapTests(unittest.TestCase):
    def test_overlap_merges_concurrent_cpu_work_without_double_counting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def trace(path, spans):
                path.parent.mkdir(parents=True, exist_ok=True)
                rows = [dict(phase=phase+'_'+edge, at_ns=int(t*1e9))
                        for phase,start,end in spans for edge,t in (('BEGIN',start),('END',end))]
                path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            trace(root/'gpu-overlap.jsonl', [('GPU_CALCULATE',2,6),('GPU_CALCULATE',8,10)])
            trace(root/'partitions/001/attempts/a/overlap.jsonl',[('NORMALIZE',1,4),('AGGREGATE',8,9)])
            trace(root/'partitions/002/attempts/b/overlap.jsonl',[('AGGREGATE',3,5)])
            result = overlap(root)
            self.assertEqual(result['gpu_request_wall_seconds'],6)
            self.assertEqual(result['cpu_normalize_or_aggregate_overlap_seconds'],4)
            self.assertEqual(result['gpu_request_intervals'],2)


if __name__ == '__main__': unittest.main()
