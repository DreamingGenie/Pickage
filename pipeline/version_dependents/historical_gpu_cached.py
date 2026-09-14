"""CUDA rank reduction with package candidates retained across bounded batches."""
from __future__ import annotations
import time
import numpy as np


class CacheEngine:
    def __init__(self, workspace_mib=128, device_index=0, cache_bytes=64*1024**2, allocation_guard=6*1024**3):
        if type(workspace_mib) is not int or not 1 <= workspace_mib <= 512:
            raise ValueError('Invalid workspace_mib')
        if any(type(x) is not int or x <= 0 for x in (cache_bytes,allocation_guard)):
            raise ValueError('Cache and allocation limits must be positive integers')
        if type(device_index) is not int or device_index != 0:
            raise ValueError('This local GPU owner supports device 0 only')
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable; no CPU fallback')
        self.device = torch.device('cuda',device_index)
        self.workspace_mib, self.cache_bytes, self.allocation_guard = workspace_mib,cache_bytes,allocation_guard
        self._entries, self._closed = {},False

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def identity(self):
        from .historical_production_resolver import runtime_identity
        return runtime_identity('gpu')

    @property
    def used_bytes(self):
        return sum(len(entry[0])*16 for entry in self._entries.values())

    def begin(self,key,birth_by_rank,snapshot_count):
        if self._closed or key in self._entries:
            raise ValueError('Duplicate or closed cache key')
        births = np.asarray(birth_by_rank)
        if (births.ndim != 1 or births.dtype != np.int64 or len(births)>100000
                or type(snapshot_count) is not int or not 1 <= snapshot_count <= 4096
                or np.any(births<0) or np.any(births>=snapshot_count)):
            raise ValueError('Invalid candidate array or calendar')
        needed = len(births)*16
        if self.used_bytes+needed > self.cache_bytes:
            raise ValueError('Candidate cache exceeds byte limit')
        import torch
        started = time.perf_counter()
        with torch.cuda.device(self.device),torch.inference_mode():
            if torch.cuda.memory_allocated(self.device)+needed >= self.allocation_guard:
                raise RuntimeError('GPU allocation guard exceeded')
            ranks = torch.arange(len(births),dtype=torch.int64,device=self.device)
            gpu_birth = torch.from_numpy(births.copy()).to(self.device)
            torch.cuda.synchronize(self.device)
        self._entries[key] = (births.copy(),snapshot_count,ranks,gpu_birth)
        return dict(h2d_seconds=time.perf_counter()-started,candidate_cache_bytes=self.used_bytes)

    def calculate(self,key,spans,mapping):
        if self._closed or key not in self._entries:
            raise ValueError('Unknown or closed cache key')
        births,n,ranks,gpu_birth = self._entries[key]
        if not isinstance(spans,list) or not isinstance(mapping,list) or len(spans)>2048 or len(mapping)>2048:
            raise ValueError('Invalid span or mapping array')
        for intervals in spans:
            if not isinstance(intervals,tuple):
                raise ValueError('Invalid span set')
            previous = -1
            for interval in intervals:
                if (not isinstance(interval,(tuple,list)) or len(interval)!=2
                        or any(type(i) is not int for i in interval)):
                    raise ValueError('Invalid rank span')
                lo,hi=interval
                if not 0 <= lo < hi <= len(births) or lo <= previous:
                    raise ValueError('Spans must be sorted, disjoint and nonadjacent')
                previous=hi
        if any(type(i) is not int or not 0 <= i < len(spans) for i in mapping):
            raise ValueError('Invalid rank mapping')
        started = time.perf_counter()
        q,v = len(spans),len(births)
        width = max((len(s) for s in spans),default=0)
        row_bytes = max(1,16*v+32*n+16*width)
        budget = self.workspace_mib*1024**2
        if row_bytes > budget:
            raise ValueError('One requirement exceeds workspace budget')
        chunk = max(1,min(q or 1,budget//row_bytes))
        lower=np.zeros((q,width),dtype=np.int64); upper=np.zeros((q,width),dtype=np.int64)
        for i,intervals in enumerate(spans):
            for j,(lo,hi) in enumerate(intervals):
                lower[i,j],upper[i,j]=lo,hi
        values=np.full((q,n),-1,dtype=np.int64)
        preparation=time.perf_counter()-started
        import torch
        h2d=compute=d2h=0.0
        with torch.cuda.device(self.device),torch.inference_mode():
            torch.cuda.synchronize(self.device)
            torch.cuda.reset_peak_memory_stats(self.device)
            for start in range(0,q,chunk):
                end=min(q,start+chunk)
                if torch.cuda.memory_allocated(self.device)+(end-start)*row_bytes >= self.allocation_guard:
                    raise RuntimeError('GPU allocation guard exceeded')
                tick=time.perf_counter()
                lo_gpu=torch.from_numpy(lower[start:end]).to(self.device)
                hi_gpu=torch.from_numpy(upper[start:end]).to(self.device)
                torch.cuda.synchronize(self.device); h2d+=time.perf_counter()-tick
                tick=time.perf_counter()
                mask=torch.zeros((end-start,v),dtype=torch.bool,device=self.device)
                for col in range(width):
                    mask |= (ranks[None,:]>=lo_gpu[:,col,None]) & (ranks[None,:]<hi_gpu[:,col,None])
                eligible=torch.where(mask,ranks[None,:],-1)
                by_birth=torch.full((end-start,n),-1,dtype=torch.int64,device=self.device)
                if v:
                    by_birth.scatter_reduce_(1,gpu_birth[None,:].expand(end-start,-1),eligible,reduce='amax',include_self=True)
                cumulative=torch.cummax(by_birth,dim=1).values
                torch.cuda.synchronize(self.device); compute+=time.perf_counter()-tick
                tick=time.perf_counter(); values[start:end]=cumulative.cpu().numpy()
                torch.cuda.synchronize(self.device); d2h+=time.perf_counter()-tick
                del mask,eligible,by_birth,cumulative,lo_gpu,hi_gpu
            peak=torch.cuda.max_memory_allocated(self.device)
            reserved=torch.cuda.max_memory_reserved(self.device)
            if peak >= self.allocation_guard:
                raise RuntimeError('GPU allocation guard exceeded')
        result=values[mapping] if mapping else np.empty((0,n),dtype=np.int64)
        return result,dict(seconds=time.perf_counter()-started,host_preparation_seconds=preparation,h2d_seconds=h2d,
            compute_seconds=compute,d2h_seconds=d2h,peak_allocated_bytes=peak,peak_reserved_bytes=reserved,
            candidate_cache_bytes=self.used_bytes,unique_span_sets=q,chunk_rows=chunk)

    def end(self,key):
        if self._closed or key not in self._entries:
            raise ValueError('Unknown or closed cache key')
        del self._entries[key]

    def close(self):
        self._entries.clear()
        self._closed=True
