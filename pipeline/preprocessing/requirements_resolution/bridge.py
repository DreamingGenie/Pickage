"""Bounded host bridge between Parquet and one persistent npm resolver."""
from __future__ import annotations

from itertools import groupby, islice
import json
from pathlib import Path
import queue
import shutil
import subprocess
import threading

import duckdb

from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes


def discover_runtime(node=None, semver_module=None, package_arg_module=None):
    executable = shutil.which(node or "node")
    if not executable:
        raise ValueError("Node executable is unavailable; pass --node")
    npm_modules = Path(executable).resolve().parent / "node_modules" / "npm" / "node_modules"
    if not npm_modules.is_dir():
        # Unix npm installs live under prefix/lib, Windows beside node.exe.
        npm_modules = Path(executable).resolve().parent.parent / "lib" / "node_modules" / "npm" / "node_modules"
    semver = Path(semver_module).resolve() if semver_module else npm_modules / "semver"
    package_arg = Path(package_arg_module).resolve() if package_arg_module else npm_modules / "npm-package-arg"
    if any(not (root / "package.json").is_file() for root in (semver, package_arg)):
        raise ValueError("Pass installed --semver-module and --package-arg-module paths")
    return {"node": str(Path(executable).resolve()), "semver_module": str(semver),
            "package_arg_module": str(package_arg)}


class NodeSession:
    def __init__(self, runtime, log_path, *, timeout=60, worker=None):
        self.timeout = timeout
        self.responses = queue.Queue()
        self.log = Path(log_path).open("xb")
        self.closed = False
        command = [runtime["node"], "--max-old-space-size=768",
                   str(worker or Path(__file__).with_name("semver_worker.cjs")),
                   runtime["semver_module"], runtime["package_arg_module"]]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.log, text=True, encoding="utf-8", bufsize=1)
        except BaseException:
            self.log.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8 * 1024 * 1024 + 1)
                if not line:
                    self.responses.put(None)
                    return
                if len(line) > 8 * 1024 * 1024 or not line.endswith("\n"):
                    self.responses.put(ValueError("Node response exceeds framing limit"))
                    return
                self.responses.put(line)
        except BaseException as error:
            self.responses.put(error)

    def request(self, message):
        if self.closed:
            raise ValueError("Node session is closed")
        try:
            self.process.stdin.write(canonical_bytes(message).decode("utf-8"))
            self.process.stdin.flush()
            response = self.responses.get(timeout=self.timeout)
        except (BrokenPipeError, OSError, queue.Empty) as error:
            self.close(check=False)
            raise RuntimeError("Node bridge failed or exceeded request timeout") from error
        if response is None or isinstance(response, BaseException):
            self.close(check=False)
            raise RuntimeError("Node bridge ended before a valid response") from (
                response if isinstance(response, BaseException) else None)
        try:
            value = json.loads(response)
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("Node bridge returned invalid JSON") from error
        if not isinstance(value, dict) or value.get("ok") is not True or "result" not in value:
            detail = value.get("error", "Invalid response contract") if isinstance(value, dict) else "Invalid response contract"
            detail = "".join(char for char in str(detail) if char.isprintable())[:240]
            raise RuntimeError("Node bridge rejected the request: " + detail)
        return value["result"]

    def close(self, *, check=True):
        if self.closed:
            return
        self.closed = True
        try:
            self.process.stdin.close()
            try:
                code = self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                code = self.process.wait(timeout=10)
            self.reader.join(timeout=2)
            self.process.stdout.close()
            if check and code != 0:
                raise RuntimeError("Node bridge exited with a nonzero status")
        finally:
            self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.close(check=kind is None)


def _rows(cursor):
    while batch := cursor.fetchmany(4096):
        yield from batch


def _batches(iterator, size=512):
    while batch := list(islice(iterator, size)):
        yield batch


def _files(path):
    paths = sorted(Path(path).rglob("*.parquet"))
    if not paths or any(p.is_symlink() for p in paths):
        raise ValueError("Missing or symlinked stage Parquet")
    return [str(path.resolve()) for path in paths]


def resolve_prepared(prepared_dir, output, runtime, *, memory_limit="2GB", threads=2):
    prepared_dir, output = Path(prepared_dir).resolve(), Path(output).resolve()
    if output.is_relative_to(prepared_dir) or prepared_dir.is_relative_to(output):
        raise ValueError("Bridge input/output paths must be separate")
    output.mkdir(parents=True, exist_ok=False)
    mapping_json, quality_json = output / "mappings.jsonl", output / "target-quality.jsonl"
    counts = {"lookups": 0, "consulted_target_packages": 0, "rejected_consulted_candidates": 0}
    with duckdb.connect(str(output / "bridge.duckdb"), config={"threads": threads,
                        "memory_limit": memory_limit}) as con:
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET temp_directory=?", [str(output / "scratch")])
        con.execute("CREATE TABLE requests AS SELECT DISTINCT lookup_id,declared_name,requirement "
                    "FROM read_parquet(?,hive_partitioning=false)", [_files(prepared_dir / "declarations")])
        if con.execute("SELECT count(*) FROM (SELECT lookup_id FROM requests GROUP BY lookup_id HAVING count(*)<>1)").fetchone()[0]:
            raise ValueError("Lookup ID maps to inconsistent declaration fields")
        requests = con.cursor().execute("SELECT declared_name,lookup_id,requirement FROM requests ORDER BY declared_name NULLS FIRST,lookup_id")
        candidates = con.cursor().execute("SELECT name,version FROM read_parquet(?,hive_partitioning=false) ORDER BY name,version",
                                          [_files(prepared_dir / "candidates")])
        candidate_groups = iter(groupby(_rows(candidates), key=lambda row: row[0]))
        current = next(candidate_groups, None)
        with NodeSession(runtime, output / "node-stderr.log") as node, mapping_json.open("xb") as mapped, quality_json.open("xb") as quality:
            metadata = node.request({"op": "metadata"})
            for name, group in groupby(_rows(requests), key=lambda row: row[0]):
                if not isinstance(name, str) or not name or "\x00" in name:
                    for _, lookup_id, requirement in group:
                        mapped.write(canonical_bytes({"lookup_id": lookup_id, "declared_name": name,
                            "requirement": requirement, "normalized_range": None, "target_version": None,
                            "status": "INVALID_PACKAGE_NAME"}))
                        counts["lookups"] += 1
                    continue
                while current is not None and current[0] < name:
                    current = next(candidate_groups, None)
                node.request({"op": "start", "name": name})
                counts["consulted_target_packages"] += 1
                if current is not None and current[0] == name:
                    for batch in _batches(current[1], size=4096):
                        reply = node.request({"op": "candidates", "versions": [row[1] for row in batch]})
                        for rejected in reply["rejected"]:
                            quality.write(canonical_bytes({"name": name, **rejected}))
                            counts["rejected_consulted_candidates"] += 1
                    current = next(candidate_groups, None)
                for batch in _batches(group):
                    replies = node.request({"op": "resolve", "requirements": [row[2] for row in batch]})
                    if not isinstance(replies, list) or len(replies) != len(batch):
                        raise ValueError("Node result batch does not match its request")
                    for (_, lookup_id, requirement), reply in zip(batch, replies):
                        if reply.get("requirement") != requirement:
                            raise ValueError("Node changed the original requirement")
                        mapped.write(canonical_bytes({"lookup_id": lookup_id, "declared_name": name, **reply}))
                        counts["lookups"] += 1
        schemas = {"mappings": "lookup_id VARCHAR,declared_name VARCHAR,requirement VARCHAR,normalized_range VARCHAR,target_version VARCHAR,status VARCHAR",
                   "target_quality": "name VARCHAR,version VARCHAR,reason VARCHAR"}
        for table, path in (("mappings", mapping_json), ("target_quality", quality_json)):
            con.execute(f"CREATE TABLE {table}({schemas[table]})")
            if path.stat().st_size:
                columns = {part.split()[0]: part.split()[1] for part in schemas[table].split(",")}
                con.execute(f"INSERT INTO {table} SELECT * FROM read_json(?,format='newline_delimited',columns=?)", [str(path), columns])
            folder = output / table
            folder.mkdir()
            con.execute(f"COPY {table} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(folder / "part-0.parquet")])
        if con.execute("SELECT count(*) FROM mappings").fetchone()[0] != counts["lookups"]:
            raise ValueError("Bridge output row count mismatch")
        requests.close()
        candidates.close()
    return {**counts, "runtime": metadata, "target_quality_scope": "consulted_target_packages_only"}
