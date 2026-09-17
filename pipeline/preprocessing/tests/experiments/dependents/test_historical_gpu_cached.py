import unittest
import numpy as np
import torch
from pipeline.preprocessing.experiments.dependents.historical_gpu_cached import CacheEngine
from pipeline.preprocessing.version_dependents.historical_gpu import cpu_ranks, gpu_ranks

@unittest.skipUnless(torch.cuda.is_available(), 'CUDA unavailable')
class CachedGpuTests(unittest.TestCase):
    def test_cached_batches_match_cpu_and_gpu_reference(self):
        births=np.array([0,1,0,2],dtype=np.int64)
        spans=[((0,4),),((1,3),),((2,4),)]
        plan={'snapshot_count':4,'known_package':True,'rank_to_version':['a','b','c','d'],'birth_by_rank':births.tolist(),'earliest_accepted_birth':0,'lookups':[{'requirement':'*','normalized_range':'*','fixed_status':None,'spans':[list(x) for x in spans[0]]},{'requirement':'>=','normalized_range':'>=','fixed_status':None,'spans':[list(x) for x in spans[1]]},{'requirement':'x','normalized_range':'x','fixed_status':None,'spans':[list(x) for x in spans[2]]}]}
        with CacheEngine() as engine:
            engine.begin('a',births,4)
            actual,_=engine.calculate('a',spans,[0,1,2])
            expected,_=gpu_ranks(plan)
            cpu,_=cpu_ranks(plan)
            np.testing.assert_array_equal(actual,expected); np.testing.assert_array_equal(actual,cpu)
            self.assertTrue(engine.calculate('a',spans,[2])[0].shape==(1,4))
            engine.end('a')
    def test_validation_and_cache_lifecycle(self):
        with CacheEngine(cache_bytes=16) as engine:
            with self.assertRaises(ValueError): engine.begin('x',np.array([0,1],dtype=np.int64),2)
            engine.begin('x',np.array([],dtype=np.int64),2)
            self.assertEqual(engine.calculate('x',[],[])[0].shape,(0,2)); engine.end('x')
            with self.assertRaises(ValueError): engine.end('x')

    def test_small_workspace_chunks_many_requirements_and_global_cache_limit(self):
        births=np.arange(10000,dtype=np.int64)%8
        spans=[((i%100, min(10000, i%100+500)),) for i in range(40)]
        with CacheEngine(workspace_mib=1, cache_bytes=10000*16*2) as engine:
            engine.begin('a', births, 8); engine.begin('b', births, 8)
            values, metrics=engine.calculate('a', spans, list(range(40)))
            self.assertEqual(values.shape,(40,8)); self.assertLess(metrics['chunk_rows'],40)
            with self.assertRaises(ValueError): engine.begin('c', births, 8)

if __name__ == '__main__': unittest.main()
