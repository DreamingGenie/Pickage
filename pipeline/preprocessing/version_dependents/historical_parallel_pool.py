"""Persistent spawned workers with platform process-tree containment.

No task may initialize its Node child until the parent has assigned its job.
Closing the last job handle (including coordinator death) kills the whole tree.
Windows uses Job Objects. POSIX uses a worker-owned process group and a
parent-death signal, so a Node descendant cannot outlive its worker tree.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import signal
import time
import traceback


def _posix_parent_death_signal(parent_pid):
    """Arrange for a worker to terminate its own process group if orphaned."""
    if os.name == 'nt':
        return
    import ctypes.util
    libc_name = ctypes.util.find_library('c')
    if not libc_name:
        raise RuntimeError('POSIX process containment requires libc prctl support')
    libc = ctypes.CDLL(libc_name, use_errno=True)
    prctl = getattr(libc, 'prctl', None)
    if prctl is None:
        raise RuntimeError('POSIX process containment requires prctl')
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    # PR_SET_PDEATHSIG. The parent pid check closes the setup race.
    if prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != parent_pid:
        os._exit(1)


def _kill_process_group(signum=signal.SIGTERM, pgid=None):
    if os.name != 'nt':
        try:
            os.killpg(os.getpgrp() if pgid is None else pgid, signum)
        except (ProcessLookupError, PermissionError):
            pass


class Job:
    def __init__(self):
        self.handle = None
        self.pgid = None
        if os.name != 'nt':
            return
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t),
                        ('max_working', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        if os.name != 'nt':
            # The worker creates its own session before START; wait until the
            # group is observable by the coordinator.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if os.getpgid(pid) == pid:
                        self.pgid = pid
                        return
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            raise RuntimeError(f'Unable to isolate worker process group {pid}')
        handle = self.api.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(handle)

    def close(self):
        if os.name != 'nt':
            if self.pgid is not None:
                _kill_process_group(signal.SIGKILL, self.pgid)
                self.pgid = None
            return
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _child(pipe, initializer, handler, args):
    context = None
    try:
        if os.name != 'nt':
            os.setsid()
        parent_pid = os.getppid()
        _posix_parent_death_signal(parent_pid)
        if pipe.recv() != 'START':
            return
        if os.name != 'nt':
            # The parent has assigned the worker's private group before START.
            signal.signal(signal.SIGTERM, lambda signum, frame: _kill_process_group(signal.SIGKILL))
            signal.signal(signal.SIGINT, lambda signum, frame: _kill_process_group(signal.SIGKILL))
        context = initializer(*args) if initializer else None
        pipe.send({'kind': 'READY', 'pid': os.getpid()})
        while True:
            task = pipe.recv()
            if task is None:
                return
            try:
                value = handler(task, context)
                pipe.send({'kind': 'RESULT', 'value': value})
            except Exception as error:
                pipe.send({'kind': 'ERROR', 'error_type': type(error).__name__,
                           'error': str(error), 'traceback': traceback.format_exc()})
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        try:
            pipe.send({'kind': 'INIT_ERROR', 'error_type': type(error).__name__,
                       'error': str(error), 'traceback': traceback.format_exc()})
        except (EOFError, BrokenPipeError):
            pass
    finally:
        if context is not None and hasattr(context, 'close'):
            context.close()
        pipe.close()


class Pool:
    """The coordinator owns assignment, retries and receipts; this owns processes."""
    def __init__(self, size, handler, *, initializer=None, initargs=()):
        if type(size) is not int or not 1 <= size <= 4:
            raise ValueError('Use 1..4 parallel workers')
        self.ctx = mp.get_context('spawn')
        self.size, self.handler, self.initializer, self.initargs = size, handler, initializer, initargs
        self.slots = {}

    def __enter__(self):
        try:
            for slot in range(self.size):
                self.replace(slot)
        except BaseException:
            self.close()
            raise
        return self

    def replace(self, slot):
        if slot in self.slots:
            self._dispose(slot)
        parent, child = self.ctx.Pipe()
        job = Job()
        proc = self.ctx.Process(target=_child, args=(child, self.initializer, self.handler, self.initargs))
        try:
            proc.start()
            child.close()
            job.assign(proc.pid)
            self.slots[slot] = {'process': proc, 'pipe': parent, 'job': job,
                                'ready': False, 'task': None, 'dead': False}
            parent.send('START')
        except BaseException:
            job.close()
            if proc.pid:
                if proc.is_alive():
                    proc.terminate()
                proc.join(5)
            parent.close()
            child.close()
            raise

    @property
    def idle(self):
        return [i for i, s in self.slots.items() if s['ready'] and not s['dead'] and s['task'] is None]

    @property
    def active(self):
        return {i: s['task'] for i, s in self.slots.items() if s['task'] is not None and not s['dead']}

    def submit(self, slot, task):
        if slot not in self.idle:
            raise ValueError('Worker is not idle')
        self.slots[slot]['task'] = task
        self.slots[slot]['pipe'].send(task)

    def events(self, timeout=0.25):
        connections = [s['pipe'] for s in self.slots.values() if not s['dead']]
        readable = wait(connections, timeout) if connections else []
        result = []
        for slot, s in self.slots.items():
            if s['dead']:
                continue
            if s['pipe'] in readable:
                try:
                    value = s['pipe'].recv()
                    value.update(slot=slot, task=s['task'])
                    if value['kind'] == 'READY':
                        s['ready'] = True
                    else:
                        s['task'] = None
                    result.append(value)
                except (EOFError, OSError):
                    pass
            if not s['process'].is_alive():
                result.append({'kind': 'DEAD', 'slot': slot, 'task': s['task'],
                               'exit_code': s['process'].exitcode})
                s['dead'] = True
                s['job'].close()  # Also kill orphaned Node descendants of this worker.
        return result

    def _dispose(self, slot):
        s = self.slots.pop(slot)
        s['job'].close()
        s['process'].join(5)
        if s['process'].is_alive():
            raise RuntimeError('Contained worker did not exit')
        s['pipe'].close()
        s['process'].close()

    def close(self):
        for slot in list(self.slots):
            self._dispose(slot)

    def __exit__(self, *args):
        self.close()
