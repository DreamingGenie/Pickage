"""PostgreSQL COPY publisher using one psql session and no Python DB driver."""
from __future__ import annotations

from collections import deque
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid

PSQL_OPTIONS = ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-w", "-P", "pager=off"]
LOCK_KEY = "hashtextextended('curated:package-version', 0)"
COLUMNS = {
    "package": ["package_id", "name", "repo_url"],
    "version": ["version", "package_id", "published_at", "ordinal", "description", "licenses", "deprecated", "dependency"],
}


class PgLoader:
    def __init__(self, command: list[str], work_dir: Path):
        if not command:
            raise ValueError("psql command must not be empty")
        self.command = list(command)
        self.work_dir = Path(work_dir)
        self._process = None
        self._stderr_thread = None
        self._stderr = deque(maxlen=30)
        self._registered = False
        self._already_published = False
        self._counts = {}
        self.phase = "CONNECT"

    def __enter__(self):
        # Binary pipes keep Windows newline translation out of COPY data.
        self._process = subprocess.Popen(self.command + PSQL_OPTIONS, cwd=self.work_dir,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process = self._process

        def drain():
            with (self.work_dir / "psql.stderr.log").open("a", encoding="utf-8") as log:
                for line in process.stderr:
                    decoded = line.decode("utf-8", errors="replace")
                    self._stderr.append(decoded.rstrip())
                    log.write(decoded)

        self._stderr_thread = threading.Thread(target=drain, daemon=True)
        self._stderr_thread.start()
        try:
            self._send("SET search_path=pg_catalog,public; SET standard_conforming_strings=on; "
                       "SET timezone='UTC'; SET client_encoding='UTF8'; "
                       "SET lock_timeout='10s'; SET statement_timeout=0; SET client_min_messages=warning;")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.stdin.write(b"ROLLBACK;\n\\q\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if self._stderr_thread:
            self._stderr_thread.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except (BrokenPipeError, OSError):
                pass
        self._process = None

    @staticmethod
    def _literal(value):
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if "\x00" in str(value):
            raise ValueError("NUL is not allowed in a SQL literal")
        return "'" + str(value).replace("'", "''") + "'"

    def _error(self):
        if self._stderr_thread:
            self._stderr_thread.join(timeout=1)
        return RuntimeError("psql failed during " + self.phase + ": " + " | ".join(self._stderr)[-2500:])

    def _send(self, sql):
        process = self._process
        if process is None or process.poll() is not None:
            raise self._error()
        marker = "__PICKAGE_" + uuid.uuid4().hex + "__"
        try:
            process.stdin.write((sql.rstrip() + f"\nSELECT '{marker}';\n").encode("utf-8"))
            process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise self._error() from error
        rows = []
        for line in process.stdout:
            value = line.decode("utf-8").rstrip("\r\n")
            if value == marker:
                return rows
            rows.append(value)
        raise self._error()

    def _one_shot(self, sql):
        result = subprocess.run(self.command + PSQL_OPTIONS, input=(
            "SET standard_conforming_strings=on; SET timezone='UTC';\n" + sql).encode("utf-8"),
            cwd=self.work_dir, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2500:])
        return result.stdout.decode("utf-8").strip()

    def _phase(self, phase):
        self.phase = phase
        if self._registered:
            self._send(f"UPDATE public.etl_load_attempt SET phase={self._literal(phase)}, "
                       f"actual_counts={self._literal(self._counts)} WHERE attempt_id={self._literal(self._attempt_id)}; "
                       f"UPDATE public.etl_load_execution SET updated_at=clock_timestamp() "
                       f"WHERE execution_id={self._literal(self._execution_id)} AND active_attempt_id={self._literal(self._attempt_id)};")

    def start(self, metadata, execution_id, contract_sha256, attempt_id):
        for value in (execution_id, attempt_id):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
                raise ValueError("invalid execution or attempt ID")
        for value in (metadata.get("manifest_sha256"), contract_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("invalid manifest or contract hash")
        if metadata.get("dataset") != "package-version":
            raise ValueError("unsupported dataset")
        self._metadata = metadata
        self._execution_id, self._attempt_id = execution_id, attempt_id
        if self._send(f"SELECT pg_try_advisory_lock({LOCK_KEY});") != ["t"]:
            raise RuntimeError("another package-version load is active")
        self.phase = "REGISTER"
        literal = self._literal
        existing = self._send("SELECT row_to_json(e) FROM public.etl_load_execution e "
                              f"WHERE execution_id={literal(execution_id)};")
        allow_published_contract_change = False
        if existing:
            prior = json.loads(existing[0])
            identity = {"dataset": metadata["dataset"], "snapshot_at": metadata["snapshot"],
                        "curated_run_id": metadata["curated_run_id"], "run_prefix": metadata["run_prefix"],
                        "manifest_sha256": metadata["manifest_sha256"],
                        "input_metadata": metadata["manifest"], "expected_counts": metadata["counts"]}
            # PostgreSQL JSON omits trailing fractional zeros; compare the time value.
            same_input = (
                all(prior[key] == value for key, value in identity.items())
                and datetime.fromisoformat(prior["snapshot_timestamp"])
                == datetime.fromisoformat(metadata["snapshot_timestamp"])
            )
            allow_published_contract_change = prior["status"] == "PUBLISHED" and same_input
            if not same_input or (prior["contract_sha256"] != contract_sha256 and not allow_published_contract_change):
                raise ValueError("execution_id already exists with different input or contract")
        published = self._send(
            "SELECT contract_sha256 FROM public.etl_load_execution WHERE dataset='package-version' "
            f"AND manifest_sha256={literal(metadata['manifest_sha256'])} AND status='PUBLISHED' LIMIT 1;")
        if published and published[0] != contract_sha256 and not allow_published_contract_change:
            raise ValueError("published input has a different load contract; use a new approved input run")
        self._already_published = bool(published)
        values = [execution_id, "package-version", "PREPARING", metadata["snapshot"],
                  metadata["snapshot_timestamp"], metadata["curated_run_id"], metadata["run_prefix"],
                  metadata["manifest_sha256"], contract_sha256, metadata["manifest"], metadata["counts"], attempt_id]
        self._send("BEGIN; "
                   "UPDATE public.etl_load_attempt a SET status='FAILED',phase='ABANDONED', "
                   "error_message='Previous session ended before completion',completed_at=clock_timestamp() "
                   "FROM public.etl_load_execution e WHERE a.execution_id=e.execution_id "
                   "AND e.dataset='package-version' AND a.status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='FAILED',updated_at=clock_timestamp(), "
                   "error_message='Previous session ended before completion' WHERE dataset='package-version' AND status='PREPARING'; "
                   "INSERT INTO public.etl_load_execution "
                   "(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,"
                   "contract_sha256,input_metadata,expected_counts,active_attempt_id) VALUES (" +
                   ",".join(literal(value) for value in values) + ") "
                   "ON CONFLICT (execution_id) DO UPDATE SET "
                   "status=CASE WHEN etl_load_execution.status='PUBLISHED' THEN 'PUBLISHED' ELSE 'PREPARING' END, "
                   "active_attempt_id=EXCLUDED.active_attempt_id,error_message=NULL,updated_at=clock_timestamp(); "
                   "INSERT INTO public.etl_load_attempt "
                   "(attempt_id,execution_id,status,phase,validation_contract_sha256) VALUES (" +
                   f"{literal(attempt_id)},{literal(execution_id)},'PREPARING','VALIDATE_INPUT',{literal(contract_sha256)}); COMMIT;")
        self._registered = True
        self.phase = "VALIDATE_INPUT"
        return self._already_published

    def record_quality(self, quality):
        if not self._registered:
            raise RuntimeError("start() must be called before recording quality")
        self._send("UPDATE public.etl_load_attempt SET quality_report="
                   f"{self._literal(quality)} WHERE attempt_id={self._literal(self._attempt_id)};")

    def _copy(self, table, files):
        if table not in COLUMNS or not files or any(not Path(path).name.endswith(".copy.tsv") for path in files):
            raise ValueError("expected generated .copy.tsv files for a known table")
        for path in files:
            with Path(path).open("rb") as stream:
                stream.seek(0, 2)
                if stream.tell():
                    stream.seek(-1, 2)
                    if stream.read(1) != b"\n":
                        raise ValueError("COPY transport file must end with LF")
        columns = ",".join('"' + name + '"' for name in COLUMNS[table])
        command = f"COPY pg_temp.pg_stage_{table} ({columns}) FROM STDIN WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8');\n"
        try:
            self._process.stdin.write(command.encode())
            for path in files:
                with Path(path).open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        self._process.stdin.write(block)
            self._process.stdin.write(b"\\.\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise self._error() from error
        self._send("SELECT 1;")

    def publish(self, csv_files, counts, failpoint=None):
        if not self._registered:
            raise RuntimeError("start() must be called before publish()")
        if self._already_published:
            return self.reverified()
        if counts != self._metadata["counts"] or any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("input counts differ from registered contract")
        if failpoint not in (None, "after_package_insert"):
            raise ValueError("unknown failpoint")
        self._phase("COPY_PACKAGE")
        self._send("CREATE TEMP TABLE pg_stage_package (package_id integer NOT NULL CHECK(package_id>0), "
                   "name varchar(300) NOT NULL CHECK(length(trim(name))>0),repo_url varchar(200)); "
                   "CREATE TEMP TABLE pg_stage_version (version varchar(100) NOT NULL CHECK(length(trim(version))>0), "
                   "package_id integer NOT NULL,published_at timestamp,ordinal bigint NOT NULL CHECK(ordinal>=0), "
                   "description text,licenses json,deprecated text,dependency json NOT NULL);")
        for table in ("package", "version"):
            self._phase("COPY_" + table.upper())
            self._copy(table, csv_files[table])
            self._counts[table] = int(self._send(f"SELECT count(*) FROM pg_temp.pg_stage_{table};")[0])
            if self._counts[table] != counts[table]:
                raise ValueError(table + " count mismatch")
        self._phase("VALIDATE_STAGING")
        self._send("CREATE UNIQUE INDEX ON pg_temp.pg_stage_package(package_id); "
                   "CREATE UNIQUE INDEX ON pg_temp.pg_stage_package(name); "
                   "CREATE UNIQUE INDEX ON pg_temp.pg_stage_version(package_id,version); "
                   "ANALYZE pg_temp.pg_stage_package; ANALYZE pg_temp.pg_stage_version; "
                   "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_temp.pg_stage_version v "
                   "LEFT JOIN pg_temp.pg_stage_package p USING(package_id) WHERE p.package_id IS NULL) "
                   "THEN RAISE EXCEPTION 'version package FK mismatch'; END IF; END $$;")
        self._phase("PUBLISH")
        self._send("BEGIN; LOCK TABLE public.package,public.version,public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;")
        current = self._send("SELECT snapshot_at,manifest_sha256 FROM public.etl_dataset_current WHERE dataset='package-version';")
        if current:
            snapshot, digest = current[0].split("|")
            parent = self._metadata["manifest"].get("request", {}).get("parent") or {}
            if self._metadata["snapshot"] < snapshot:
                raise ValueError("incoming snapshot is older than published current")
            if (self._metadata["snapshot"] == snapshot and digest != self._metadata["manifest_sha256"]
                    and parent.get("manifest_sha256") != digest):
                raise ValueError("same snapshot has ambiguous input lineage")
        self._send("DO $$ BEGIN "
                   "IF EXISTS (SELECT 1 FROM pg_temp.pg_stage_package s JOIN public.package p USING(package_id) "
                   "WHERE p.name <> s.name) THEN RAISE EXCEPTION 'package_id/name collision'; END IF; "
                   "IF EXISTS (SELECT 1 FROM pg_temp.pg_stage_package s JOIN public.package p USING(name) "
                   "WHERE p.package_id <> s.package_id) THEN RAISE EXCEPTION 'package name/id collision'; END IF; END $$;")
        before = self._service_counts()
        self._send("INSERT INTO public.package (package_id,name,repo_url) "
                   "SELECT package_id,name,repo_url FROM pg_temp.pg_stage_package "
                   "ON CONFLICT (package_id) DO UPDATE SET repo_url=EXCLUDED.repo_url "
                   "WHERE package.repo_url IS DISTINCT FROM EXCLUDED.repo_url;")
        if failpoint == "after_package_insert":
            raise RuntimeError("failpoint: after_package_insert")
        self._send("INSERT INTO public.version (version,package_id,published_at,ordinal,description,licenses,deprecated,dependency) "
                   "SELECT version,package_id,published_at,ordinal,description,licenses,deprecated,dependency FROM pg_temp.pg_stage_version "
                   "ON CONFLICT (package_id,version) DO UPDATE SET published_at=EXCLUDED.published_at,ordinal=EXCLUDED.ordinal,"
                   "description=EXCLUDED.description,licenses=EXCLUDED.licenses,deprecated=EXCLUDED.deprecated,dependency=EXCLUDED.dependency "
                   "WHERE ROW(version.published_at,version.ordinal,version.description,version.licenses::text,version.deprecated,version.dependency::text) "
                   "IS DISTINCT FROM ROW(EXCLUDED.published_at,EXCLUDED.ordinal,EXCLUDED.description,EXCLUDED.licenses::text,EXCLUDED.deprecated,EXCLUDED.dependency::text);")
        after = self._service_counts()
        if before == {"package": 0, "version": 0} and after != counts:
            raise ValueError("empty database result differs from staged input counts")
        literal = self._literal
        meta = self._metadata
        self._send("INSERT INTO public.etl_dataset_current (dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES ("
                   f"'package-version',{literal(self._execution_id)},{literal(meta['snapshot'])},{literal(meta['manifest_sha256'])},{literal(meta['manifest'])}) "
                   "ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,snapshot_at=EXCLUDED.snapshot_at,"
                   "manifest_sha256=EXCLUDED.manifest_sha256,manifest=EXCLUDED.manifest,published_at=clock_timestamp(); "
                   f"UPDATE public.etl_load_execution SET status='PUBLISHED',actual_counts={literal(counts)},"
                   f"updated_at=clock_timestamp(),error_message=NULL WHERE execution_id={literal(self._execution_id)} "
                   f"AND active_attempt_id={literal(self._attempt_id)}; "
                   f"UPDATE public.etl_load_attempt SET status='PUBLISHED',phase='COMMIT',actual_counts={literal(counts)},"
                   f"completed_at=clock_timestamp() WHERE attempt_id={literal(self._attempt_id)}; COMMIT;")
        self.phase = "COMPLETE"
        return {"status": "PUBLISHED", "action": "LOADED", "counts": counts,
                "service_before_counts": before, "service_after_counts": after,
                "execution_id": self._execution_id, "attempt_id": self._attempt_id}

    def _service_counts(self):
        row = self._send("SELECT (SELECT count(*) FROM public.package),(SELECT count(*) FROM public.version);")[0]
        package, version = map(int, row.split("|"))
        return {"package": package, "version": version}

    def reverified(self):
        if not self._registered or not self._already_published:
            raise RuntimeError("only a previously published input can be reverified")
        literal = self._literal
        counts = self._metadata["counts"]
        current = self._send("SELECT manifest_sha256 FROM public.etl_dataset_current WHERE dataset='package-version';")
        is_current = current == [self._metadata["manifest_sha256"]]
        self._send("BEGIN; UPDATE public.etl_load_attempt SET status='REVERIFIED',phase='COMPLETE',"
                   f"actual_counts={literal(counts)},completed_at=clock_timestamp() WHERE attempt_id={literal(self._attempt_id)}; "
                   "UPDATE public.etl_load_execution SET status='PUBLISHED',error_message=NULL,"
                   f"actual_counts={literal(counts)},updated_at=clock_timestamp() WHERE execution_id={literal(self._execution_id)} "
                   f"AND active_attempt_id={literal(self._attempt_id)}; COMMIT;")
        self.phase = "COMPLETE"
        return {"status": "PUBLISHED", "action": "REVERIFIED", "counts": counts,
                "verification_scope": "INPUT_ONLY", "is_current_input": is_current,
                "execution_id": self._execution_id, "attempt_id": self._attempt_id}

    def fail(self, error):
        if self._process and self._process.poll() is None:
            try:
                self._send("ROLLBACK;")
            except (RuntimeError, OSError):
                pass
        if not self._registered:
            return
        literal = self._literal
        message = str(error).replace("\x00", "[NUL]")[-4000:]
        self._one_shot("BEGIN; UPDATE public.etl_load_attempt SET status='FAILED',"
                       f"phase={literal(self.phase)},actual_counts={literal(self._counts)},error_message={literal(message)},"
                       f"completed_at=clock_timestamp() WHERE attempt_id={literal(self._attempt_id)} AND status='PREPARING'; "
                       "UPDATE public.etl_load_execution SET status='FAILED',"
                       f"error_message={literal(message)},updated_at=clock_timestamp() WHERE execution_id={literal(self._execution_id)} "
                       f"AND active_attempt_id={literal(self._attempt_id)} AND status='PREPARING'; COMMIT;")
