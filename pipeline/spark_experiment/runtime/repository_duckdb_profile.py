"""Low-overhead profiling for the DuckDB repository transform.

The profiler is deliberately a connection proxy: the transformation receives
the same API and SQL as before, while every statement is recorded as one
durable JSONL operation.  A SELECT's execute and fetch are combined into one
event so deferred fetch work is not counted twice.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import time
from typing import Any, Iterator

from ..telemetry import read_snapshot, snapshot_delta


_CATEGORIES = (
    "input_read", "validation", "approved_join", "raw_join", "normalize",
    "candidates_selection", "observations", "metric_join", "output_prepare",
    "output_write", "output_recount", "final_validation_report",
)


def _category(sql: str, executemany: bool = False) -> str:
    text = re.sub(r"\s+", " ", sql.upper()).strip()
    # COPY must be checked before table-name heuristics: its SELECT source can
    # mention any intermediate table, but the operation itself is publication.
    if text.startswith("COPY"):
        return "output_write"
    if "READ_PARQUET" in text and "COUNT" in text:
        return "output_recount"
    if "READ_PARQUET" in text:
        return "input_read"
    match = re.match(r"CREATE(?: OR REPLACE)? TEMP TABLE ([A-Z0-9_]+)", text)
    if match:
        target = match.group(1)
        if target.startswith("INPUT_") and "NORMALIZED" not in target:
            return "input_read"
        if "NORMALIZED" in target:
            return "normalize"
        if target == "APPROVED":
            return "approved_join"
        if target == "MATCHED":
            return "raw_join"
        if target in {"URL_MAP", "CANDIDATES", "SELECTED"}:
            return "candidates_selection"
        if target in {"OBSERVATIONS_BASE", "OBSERVATIONS_BASE2", "PAIRS", "CANONICAL", "CANONICAL_VALUES", "UNMAPPED"}:
            return "observations"
        if target in {"JOINED", "METRIC_DATA", "SELECTION", "CANDIDATES_OUT"}:
            return "metric_join"
        if target in {"PROJECT_OBSERVATIONS", "PROJECT_CONFLICTS", "UNMAPPED_PROJECTS"}:
            return "output_prepare"
    if text.startswith("DESCRIBE") or "SELECT 1 FROM" in text or "GROUP BY" in text and "HAVING" in text:
        return "validation"
    if "APPROVED" in text:
        return "approved_join"
    if "MATCHED" in text or "BRONZE" in text or "SOURCE_REPO" in text and "RAW" in text:
        return "raw_join"
    if "NORMALIZED" in text or "CAST(" in text and "SNAPSHOTAT" in text:
        return "normalize"
    if "URL_MAP" in text or "CANDIDATE" in text or "SELECTED" in text:
        return "candidates_selection"
    if "OBSERVATIONS" in text or "CANONICAL" in text or "PAIRS" in text or "UNMAPPED" in text:
        return "observations"
    if "JOINED" in text or "METRIC_DATA" in text or "SELECTION AS" in text:
        return "metric_join"
    if text.startswith("SET "):
        return "output_prepare"
    return "validation" if not executemany else "candidates_selection"


def _short_sql(sql: Any) -> str:
    return re.sub(r"\s+", " ", str(sql)).strip()[:240]


class _CursorProxy:
    def __init__(self, owner: "DuckDBProfiler", cursor: Any, event: dict[str, Any]):
        self._owner, self._cursor, self._event = owner, cursor, event
        self._done = False

    def _finish(self, method: str, fn):
        if self._done:
            return fn()
        started = time.perf_counter()
        failed = False
        try:
            return fn()
        except BaseException:
            failed = True
            raise
        finally:
            self._event["fetch_method"] = method
            self._event["fetch_seconds"] = round(time.perf_counter() - started, 6)
            self._owner._finish(self._event, completed=not failed)
            self._done = True

    def fetchone(self):
        return self._finish("fetchone", self._cursor.fetchone)

    def fetchall(self):
        return self._finish("fetchall", self._cursor.fetchall)

    def fetchmany(self, size=None):
        return self._finish("fetchmany", lambda: self._cursor.fetchmany() if size is None else self._cursor.fetchmany(size))

    def __iter__(self):
        if self._done:
            return iter(self._cursor)
        started = time.perf_counter()
        def rows():
            failed = False
            try:
                yield from self._cursor
            except BaseException:
                failed = True
                raise
            finally:
                self._event["fetch_method"] = "iter"
                self._event["fetch_seconds"] = round(time.perf_counter() - started, 6)
                self._owner._finish(self._event, completed=not failed)
                self._done = True
        return rows()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionProxy:
    def __init__(self, owner: "DuckDBProfiler", connection: Any):
        self._owner, self._connection = owner, connection

    def execute(self, sql, parameters=None, *args, **kwargs):
        return self._owner._execute(self._connection.execute, sql, parameters, args, kwargs)

    def executemany(self, sql, parameters, *args, **kwargs):
        return self._owner._execute(self._connection.executemany, sql, parameters, args, kwargs, executemany=True)

    def __getattr__(self, name):
        return getattr(self._connection, name)


class DuckDBProfiler:
    """Record DuckDB operations and aggregate timing by transparent category."""

    def __init__(self, path: str | Path, *, snapshot_fn=read_snapshot):
        self.path = Path(path)
        self.summary_path = self.path.with_name(self.path.stem + "-summary.json")
        self.snapshot_fn = snapshot_fn
        self._stream = None
        self.events: list[dict[str, Any]] = []
        self._pending: list[dict[str, Any]] = []
        self.started_at = None
        self.failed: dict[str, str] | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("w", encoding="utf-8")
        self.started_at = time.time()
        return self

    def connection(self, con: Any) -> _ConnectionProxy:
        return _ConnectionProxy(self, con)

    def _execute(self, fn, sql, parameters, args, kwargs, *, executemany=False):
        self._flush_pending()
        before = self.snapshot_fn()
        started = time.perf_counter()
        wall_started = time.time()
        try:
            if parameters is None:
                cursor = fn(sql, *args, **kwargs)
            else:
                cursor = fn(sql, parameters, *args, **kwargs)
        except BaseException:
            self._finish({"kind": "execute", "sql": _short_sql(sql), "category": _category(sql, executemany),
                          "execute_seconds": round(time.perf_counter() - started, 6), "fetch_seconds": 0.0,
                          "started_at": wall_started, "before": before, "error": True})
            raise
        event = {"kind": "executemany" if executemany else "execute", "sql": _short_sql(sql),
                 "category": _category(sql, executemany), "execute_seconds": round(time.perf_counter() - started, 6),
                 "fetch_seconds": 0.0, "started_at": wall_started, "before": before}
        # DuckDB statements without a fetch are complete at execute return;
        # SELECTs are finalized when the caller fetches from the returned proxy.
        if re.match(r"\s*(SELECT|DESCRIBE|SHOW|EXPLAIN)", str(sql), re.I):
            self._pending.append(event)
            return _CursorProxy(self, cursor, event)
        self._finish(event)
        return cursor

    def _flush_pending(self):
        for event in self._pending[:]:
            self._finish(event, completed=False, uncompleted=True)
        self._pending.clear()

    def _finish(self, event, *, completed=True, uncompleted=False):
        if event in self._pending:
            self._pending.remove(event)
        after = self.snapshot_fn()
        event["finished_at"] = time.time()
        event["wall_seconds"] = round(event["execute_seconds"] + event.get("fetch_seconds", 0.0), 6)
        event["delta"] = _safe_delta(event.pop("before", None), after)
        event["completed"] = completed and not event.get("error", False)
        if uncompleted:
            event["uncompleted"] = True
        self.events.append(event)
        if self._stream is not None:
            self._stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._stream.flush()

    def summary(self) -> dict[str, Any]:
        totals = {name: round(sum(e.get("wall_seconds", 0.0) for e in self.events if e.get("category") == name), 6)
                  for name in _CATEGORIES}
        return {"format": "duckdb_repository_profile_v1", "status": "FAILED" if self.failed else "COMPLETED",
                "started_at": self.started_at, "finished_at": time.time(), "operation_count": len(self.events),
                "completed_operation_count": sum(1 for e in self.events if e.get("completed")),
                "failed": self.failed, "category_seconds": totals,
                "unclassified_seconds": round(sum(e.get("wall_seconds", 0.0) for e in self.events
                                                   if e.get("category") not in _CATEGORIES), 6),
                "limitations": ["operation wall time includes DuckDB execute and fetch; categories are SQL attribution",
                                "cgroup counters are process/container aggregate and may be unavailable"]}

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.failed = {"type": type(exc).__name__, "message": str(exc)}
        self._flush_pending()
        if self._stream is not None:
            self._stream.close()
        self.summary_path.write_text(json.dumps(self.summary(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return False


def _safe_delta(before, after):
    if not before or not after:
        return None
    try:
        return snapshot_delta(before, after)
    except (KeyError, TypeError):
        return None


@contextmanager
def profile_connection(con: Any, path: str | Path) -> Iterator[_ConnectionProxy]:
    """Yield a profiled connection and always persist completion/failure summary."""
    with DuckDBProfiler(path) as profiler:
        yield profiler.connection(con)


__all__ = ["DuckDBProfiler", "profile_connection"]
