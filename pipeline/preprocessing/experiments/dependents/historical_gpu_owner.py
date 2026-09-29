"""Authenticated local RPC to one contained CUDA owner, with one request per client."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import pickle
import queue
import re
import threading
import time
import uuid
from multiprocessing.connection import Client as PipeClient, Listener, wait
import numpy as np
from pipeline.preprocessing.version_dependents.historical_parallel_pool import Pool
from pipeline.preprocessing.version_dependents.historical_gpu import unique_spans, validate_plan

MAX_FRAME = 16 * 1024**2
PROTOCOL = 'local-cuda-owner-v1'


class OwnerError(RuntimeError):
    pass


def _pack(value, limit=MAX_FRAME):
    raw = pickle.dumps(value, protocol=5)
    if len(raw) > limit:
        raise ValueError('GPU IPC frame exceeds byte limit')
    return raw


def _unpack(raw):
    # Only authenticated same-user local processes can supply these frames.
    return pickle.loads(raw)


def _birth_digest(births, n):
    return hashlib.sha256(str(n).encode('ascii') + b':' + births.tobytes()).hexdigest()


def _identity(value):
    if (not isinstance(value, dict) or set(value) != {'run_plan_sha256', 'epoch', 'attempt', 'partition_id'}
            or not isinstance(value['run_plan_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['run_plan_sha256'])
            or not isinstance(value['epoch'], str) or not re.fullmatch('[0-9a-f]{32}', value['epoch'])
            or type(value['partition_id']) is not int or not 0 <= value['partition_id'] < 256
            or not isinstance(value['attempt'], str)
            or not re.fullmatch(r'partitions/' + f"{value['partition_id']:03d}" + r'/attempts/[0-9a-f]{32}', value['attempt'])):
        raise ValueError('Invalid GPU attempt identity')
    return value


def _trace(path, phase, **values):
    if path is not None:
        with Path(path).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(phase=phase, at_ns=time.monotonic_ns(), pid=os.getpid(), **values)) + '\n')


class Service:
    def __init__(self, address, authkey, workers, workspace_mib, trace_path):
        from pipeline.preprocessing.experiments.dependents.historical_gpu_cached import CacheEngine
        self.engine = CacheEngine(workspace_mib=workspace_mib)
        self.identity = self.engine.identity()
        self.listener = Listener(address, family='AF_PIPE', authkey=authkey)
        self.workers, self.trace_path = workers, trace_path
        self.connections = {}
        self.accepted = queue.Queue(maxsize=workers)
        self.capacity = threading.BoundedSemaphore(workers)
        self.stopped = threading.Event()
        self.accept_error = None
        self.accept_lock = threading.Lock()

    def close(self):
        with self.accept_lock:
            self.stopped.set()
            while not self.accepted.empty():
                self.accepted.get_nowait().close()
        for conn in list(self.connections):
            conn.close()
        self.listener.close()
        self.engine.close()

    def _accept(self):
        try:
            while not self.stopped.is_set():
                if not self.capacity.acquire(timeout=0.2):
                    continue
                conn = self.listener.accept()
                with self.accept_lock:
                    if self.stopped.is_set():
                        conn.close()
                        self.capacity.release()
                        return
                    self.accepted.put_nowait(conn)
        except Exception as error:
            if not self.stopped.is_set():
                self.accept_error = error

    def _drop(self, conn):
        state = self.connections.pop(conn)
        if state['cache_key'] is not None:
            self.engine.end(state['cache_key'])
        conn.close()
        self.capacity.release()

    def _handle(self, req, state):
        if (not isinstance(req, dict) or set(req) != {'protocol', 'sequence', 'identity', 'package_key', 'candidate_digest', 'payload', 'sent_ns'}
                or req['protocol'] != PROTOCOL or type(req['sequence']) is not int
                or req['sequence'] != state['sequence'] + 1 or type(req['sent_ns']) is not int):
            raise ValueError('GPU request sequence or protocol mismatch')
        state['sequence'] = req['sequence']
        body = req['payload']
        if not isinstance(body, dict):
            raise ValueError('Invalid GPU payload')
        op = body.get('op')
        if op == 'hello':
            if state['sequence'] != 1 or set(body) != {'op'} or any(req[k] is not None for k in ('identity','package_key','candidate_digest')):
                raise ValueError('Invalid GPU hello')
            return dict(runtime=self.identity, owner_pid=os.getpid())
        identity = _identity(req['identity'])
        key, digest = req['package_key'], req['candidate_digest']
        if (not isinstance(key, str) or not 0 < len(key.encode('utf-8')) <= 4096
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('Invalid GPU package identity')
        if op == 'begin':
            if state['cache_key'] is not None or set(body) != {'op','births','snapshot_count'}:
                raise ValueError('Package already active or invalid begin')
            births, n = body['births'], body['snapshot_count']
            if not isinstance(births, np.ndarray) or births.dtype != np.int64 or births.ndim != 1:
                raise ValueError('Invalid candidate array')
            if _birth_digest(births, n) != digest:
                raise ValueError('Candidate digest differs')
            cache_key = (state['connection_id'], key, digest)
            metrics = self.engine.begin(cache_key, births, n)
            state.update(cache_key=cache_key, identity=identity, package_key=key, candidate_digest=digest, snapshot_count=n)
            return dict(metrics=metrics or {}, owner_pid=os.getpid())
        if (state['cache_key'] is None or any(req[k] != state[k] for k in ('identity','package_key','candidate_digest'))):
            raise ValueError('GPU response belongs to another attempt or package')
        if op == 'end':
            if set(body) != {'op'}:
                raise ValueError('Invalid end')
            self.engine.end(state['cache_key'])
            state['cache_key'] = None
            return dict(metrics={})
        if op != 'batch' or set(body) != {'op','spans','mapping'}:
            raise ValueError('Invalid GPU operation')
        if not isinstance(body['mapping'], list) or len(body['mapping']) * state['snapshot_count'] * 8 > MAX_FRAME - 65536:
            raise ValueError('GPU response would exceed framing bound')
        _trace(self.trace_path, 'GPU_CALCULATE_BEGIN', identity=identity, package_key=key)
        try:
            ranks, metrics = self.engine.calculate(state['cache_key'], body['spans'], body['mapping'])
        finally:
            _trace(self.trace_path, 'GPU_CALCULATE_END', identity=identity, package_key=key)
        return dict(ranks=ranks, metrics=metrics)

    def serve(self):
        threading.Thread(target=self._accept, daemon=True).start()
        try:
            while True:
                if self.accept_error:
                    raise OwnerError('GPU listener failed') from self.accept_error
                while not self.accepted.empty():
                    conn = self.accepted.get_nowait()
                    self.connections[conn] = dict(connection_id=uuid.uuid4().hex, sequence=0, cache_key=None)
                readable = wait(list(self.connections), timeout=0.05) if self.connections else []
                if not self.connections:
                    self.stopped.wait(0.01)
                for conn in readable:
                    try:
                        req = _unpack(conn.recv_bytes(MAX_FRAME))
                    except (EOFError, OSError):
                        self._drop(conn)
                        continue
                    queue_seconds = max(0, time.monotonic_ns() - req.get('sent_ns', time.monotonic_ns())) / 1e9
                    try:
                        result = self._handle(req, self.connections[conn])
                        result.setdefault('metrics', {})['queue_wait_seconds'] = queue_seconds
                        answer = {k:req[k] for k in ('protocol','sequence','identity','package_key','candidate_digest')}
                        answer.update(ok=True, result=result)
                        conn.send_bytes(_pack(answer))
                    except Exception as error:
                        # All protocol/CUDA failures are owner-fatal, never CPU fallback.
                        try:
                            conn.send_bytes(_pack(dict(ok=False,error=str(error))))
                        except (OSError, EOFError):
                            pass
                        raise OwnerError('GPU service failed: ' + str(error)) from error
        finally:
            self.close()


def _service_init(*args):
    return Service(*args)


def _service_task(task, service):
    if task == 'describe':
        return dict(runtime=service.identity, owner_pid=os.getpid(), protocol=PROTOCOL)
    if task != 'serve':
        raise ValueError('Unknown GPU owner task')
    return service.serve()


class Owner:
    def __init__(self, workers, workspace_mib=128, trace_path=None, startup_timeout=120):
        if type(workers) is not int or workers not in (1,2,4):
            raise ValueError('Use 1, 2 or 4 CPU clients')
        self.address = r'\\.\pipe\pickage-gpu-' + uuid.uuid4().hex
        self.authkey = os.urandom(32)
        self.startup_timeout = startup_timeout
        self.pool = Pool(1, _service_task, initializer=_service_init,
                         initargs=(self.address,self.authkey,workers,workspace_mib,trace_path))
        self.runtime = None
        self.failed, self.closed = None, False

    def __enter__(self):
        try:
            self.pool.__enter__()
            deadline = time.monotonic() + self.startup_timeout
            sent = False
            while time.monotonic() < deadline:
                for event in self.pool.events():
                    if event['kind'] == 'READY':
                        self.pool.submit(0,'describe'); sent = True
                    elif event['kind'] == 'RESULT' and sent:
                        if event['value']['protocol'] != PROTOCOL:
                            raise OwnerError('GPU owner protocol differs')
                        self.runtime = event['value']['runtime']
                        self.pid = event['value']['owner_pid']
                        self.pool.submit(0,'serve')
                        return self
                    else:
                        raise OwnerError('GPU owner initialization failed: ' + str(event))
            raise OwnerError('GPU owner startup timed out')
        except BaseException:
            self.pool.close()
            raise

    def check(self):
        if self.failed or self.closed:
            raise OwnerError(self.failed or 'GPU owner is closed')
        for event in self.pool.events(timeout=0):
            self.failed = 'GPU owner stopped: ' + str(event)
            raise OwnerError(self.failed)
        if not self.pool.slots[0]['process'].is_alive():
            self.failed = 'GPU owner died'
            raise OwnerError(self.failed)

    def close(self):
        self.closed = True
        self.pool.close()

    def __exit__(self,*args):
        self.close()


class Client:
    def __init__(self, address, authkey, expected_runtime, timeout=120):
        self.timeout, self.sequence = timeout, 0
        self.conn = PipeClient(address, family='AF_PIPE', authkey=authkey)
        self.identity = self.key = self.digest = self.base = None
        self.jobs, self.replies = queue.Queue(maxsize=1), queue.Queue(maxsize=1)
        self.closed = False
        self.lock = threading.Lock()
        threading.Thread(target=self._io, daemon=True).start()
        hello = self._request({'op':'hello'})
        if hello['runtime'] != expected_runtime:
            self.close()
            raise OwnerError('GPU runtime differs from run plan')
        self.owner_pid = hello['owner_pid']

    def _io(self):
        while True:
            raw = self.jobs.get()
            if raw is None:
                return
            try:
                self.conn.send_bytes(raw)
                result = _unpack(self.conn.recv_bytes(MAX_FRAME))
                self.replies.put((True,result))
            except Exception as error:
                self.replies.put((False,error))
                return

    def _request(self, payload):
        if self.closed or not self.lock.acquire(blocking=False):
            raise OwnerError('GPU client is closed or already has an in-flight request')
        started = time.perf_counter()
        try:
            self.sequence += 1
            envelope = dict(protocol=PROTOCOL, sequence=self.sequence, identity=self.identity,
                            package_key=self.key, candidate_digest=self.digest, payload=payload, sent_ns=time.monotonic_ns())
            encoded = _pack(envelope)
            encode_seconds = time.perf_counter()-started
            self.jobs.put_nowait(encoded)
            try:
                success, answer = self.replies.get(timeout=self.timeout)
            except queue.Empty as error:
                self.close()
                raise OwnerError('GPU request timed out; resume unfinished partitions in a new run') from error
            if not success:
                raise OwnerError('GPU connection failed') from answer
            if answer.get('ok') is not True:
                raise OwnerError('GPU owner rejected request: '+str(answer.get('error')))
            if any(answer.get(k) != envelope[k] for k in ('protocol','sequence','identity','package_key','candidate_digest')):
                raise OwnerError('GPU response identity or sequence mismatch')
            result = answer['result']
            result.setdefault('metrics',{}).update(rpc_seconds=time.perf_counter()-started,
                ipc_encode_seconds=encode_seconds,request_bytes=len(encoded),response_bytes=len(_pack(answer)))
            return result
        except BaseException:
            self.close()
            raise
        finally:
            self.lock.release()

    def bind(self, identity):
        if self.key is not None:
            raise OwnerError('Cannot rebind an active package')
        self.identity = dict(_identity(identity))

    def begin(self, package_key, base_plan):
        if self.key is not None or self.identity is None:
            raise OwnerError('Cannot begin without an idle bound attempt')
        validate_plan(base_plan)
        births = np.asarray(base_plan['birth_by_rank'],dtype=np.int64)
        self.key, self.digest = package_key, _birth_digest(births,base_plan['snapshot_count'])
        self.base = {k:base_plan[k] for k in ('rank_to_version','birth_by_rank','snapshot_count','known_package')}
        return self._request(dict(op='begin',births=births,snapshot_count=base_plan['snapshot_count']))['metrics']

    def ranks(self, package_key, plan):
        if package_key != self.key or any(plan[k] != v for k,v in self.base.items()):
            raise OwnerError('Batch candidate mapping changed')
        spans,mapping = unique_spans(plan)
        result = self._request(dict(op='batch',spans=spans,mapping=mapping))
        ranks = result['ranks']
        if not isinstance(ranks,np.ndarray) or ranks.dtype != np.int64 or ranks.shape != (len(plan['lookups']),plan['snapshot_count']):
            raise OwnerError('GPU rank result shape or dtype mismatch')
        return ranks,result['metrics']

    def end(self, package_key):
        if package_key != self.key:
            raise OwnerError('Ending another package')
        result = self._request(dict(op='end'))
        self.key = self.digest = self.base = None
        return result['metrics']

    def close(self):
        if not self.closed:
            self.closed = True
            self.conn.close()
            try:
                self.jobs.put_nowait(None)
            except queue.Full:
                pass
