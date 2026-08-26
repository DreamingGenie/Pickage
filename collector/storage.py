from __future__ import annotations

import gzip
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import PACKAGE_DIR, SourceRegistry, SourceSpec
from .contracts import CollectionItem, CollectionRun, ValidationReport
from .logging_utils import LOGGER, log_event
from .safety import contains_secret


SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_run (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target TEXT NOT NULL,
    evidence_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    safe_params_json TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    failure_code TEXT,
    failure_message TEXT
);
CREATE TABLE IF NOT EXISTS http_exchange (
    exchange_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    safe_endpoint TEXT NOT NULL,
    safe_params_json TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    headers_received_at TEXT,
    body_completed_at TEXT NOT NULL,
    http_status INTEGER,
    content_type TEXT,
    body_sha256 TEXT NOT NULL,
    body_bytes INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    transport_error TEXT,
    retry_after TEXT,
    retry_history_json TEXT NOT NULL DEFAULT '[]',
    duplicate_of TEXT,
    raw_artifact_path TEXT,
    normalized_artifact_path TEXT,
    FOREIGN KEY(run_id) REFERENCES collection_run(run_id)
);
CREATE INDEX IF NOT EXISTS idx_exchange_source_hash
ON http_exchange(source_id, body_sha256);
CREATE TABLE IF NOT EXISTS parse_batch (
    exchange_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    business_code TEXT,
    business_message TEXT,
    declared_count INTEGER,
    parsed_count INTEGER NOT NULL,
    parse_error TEXT,
    response_format TEXT,
    FOREIGN KEY(exchange_id) REFERENCES http_exchange(exchange_id)
);
CREATE TABLE IF NOT EXISTS quota_ledger (
    credential_alias TEXT NOT NULL,
    kst_date TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    reserved_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(credential_alias, kst_date)
);
CREATE TABLE IF NOT EXISTS quota_reservation (
    reservation_id TEXT PRIMARY KEY,
    credential_alias TEXT NOT NULL,
    kst_date TEXT NOT NULL,
    run_id TEXT,
    reserved_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quota_reservation_active
ON quota_reservation(credential_alias, kst_date, status, expires_at);
CREATE TABLE IF NOT EXISTS validation_report (
    report_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    target TEXT NOT NULL,
    verdict TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    manifest_sha256 TEXT,
    evaluated_at TEXT NOT NULL,
    report_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_run(run_id)
);
CREATE TABLE IF NOT EXISTS quality_result (
    report_id TEXT NOT NULL,
    check_code TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY(report_id, check_code),
    FOREIGN KEY(report_id) REFERENCES validation_report(report_id)
);
"""


class MetadataRepository:
    # A lease prevents a process killed between reserve and consume/release
    # from permanently blocking the provider's daily quota.  Recovery is
    # explicit so the existing service flow remains backward-compatible.
    DEFAULT_QUOTA_LEASE_SECONDS = 15 * 60

    def __init__(
        self,
        root: str | Path = PACKAGE_DIR / "var",
        db_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path).resolve() if db_path else self.root / "collector.sqlite3"
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        self._ensure_column(
            "quota_ledger", "reserved_count", "INTEGER NOT NULL DEFAULT 0"
        )
        self._ensure_column(
            "collection_run", "status", "TEXT NOT NULL DEFAULT 'RUNNING'"
        )
        self._ensure_column("collection_run", "failure_code", "TEXT")
        self._ensure_column("collection_run", "failure_message", "TEXT")
        self._ensure_column("http_exchange", "retry_after", "TEXT")
        self._ensure_column(
            "http_exchange", "retry_history_json", "TEXT NOT NULL DEFAULT '[]'"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def begin_run(
        self,
        run: CollectionRun,
        evidence_mode: str,
        collector_version: str,
        *,
        secrets: list[str] | None = None,
    ) -> None:
        safe_params = json.dumps(run.params, ensure_ascii=False, sort_keys=True, default=str)
        self._assert_no_secrets(
            {"target": run.target, "params": safe_params}, secrets or []
        )
        with self.connection:
            self.connection.execute(
                """INSERT INTO collection_run
                (run_id, source_id, target, evidence_mode, started_at, ended_at,
                 safe_params_json, collector_version, status, failure_code, failure_message)
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 'RUNNING', NULL, NULL)""",
                (run.run_id, run.source_id, run.target, evidence_mode, run.started_at, safe_params, collector_version),
            )

    def save_item(
        self,
        run: CollectionRun,
        item: CollectionItem,
        spec: SourceSpec,
        policy: dict[str, Any],
    ) -> None:
        exchange = item.exchange
        SourceRegistry._validate_policy(spec.source_id, policy)
        credential_alias = spec.get("auth", {}).get("env", "NO_CREDENTIAL")
        secrets = [os.environ.get(credential_alias, "")] if credential_alias != "NO_CREDENTIAL" else []
        safe_record = {
            "safe_endpoint": exchange.safe_endpoint,
            "safe_params": exchange.safe_params,
            "transport_error": exchange.transport_error,
            "retry_history": exchange.retry_history,
            "business_code": item.batch.business_code,
            "business_message": item.batch.business_message,
        }
        self._assert_no_secrets(safe_record, secrets)
        if policy.get("raw") == "ALLOW_LOCAL_ONLY":
            self._assert_no_secrets(item.exchange.body.decode("utf-8", errors="replace"), secrets)
        if policy.get("normalized") == "ALLOW_LOCAL_ONLY":
            self._assert_no_secrets(item.batch.rows, secrets)

        duplicate_row = self.connection.execute(
            "SELECT exchange_id FROM http_exchange WHERE source_id=? AND body_sha256=? ORDER BY requested_at LIMIT 1",
            (spec.source_id, exchange.body_sha256),
        ).fetchone()
        duplicate_of = duplicate_row["exchange_id"] if duplicate_row else None
        # Files are created before the metadata transaction so their paths can
        # be stored atomically.  If the database write fails, the except block
        # removes both files and avoids orphaned evidence.
        raw_path = self._write_raw(run, item, policy)
        normalized_path = self._write_normalized(run, item, policy)
        try:
            with self.connection:
                self.connection.execute(
                    """INSERT INTO http_exchange
                    (exchange_id, run_id, source_id, safe_endpoint, safe_params_json,
                     requested_at, headers_received_at, body_completed_at, http_status, content_type,
                     body_sha256, body_bytes, attempts, elapsed_ms, transport_error, duplicate_of,
                     retry_after, retry_history_json, raw_artifact_path, normalized_artifact_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        exchange.exchange_id,
                        run.run_id,
                        spec.source_id,
                        exchange.safe_endpoint,
                        json.dumps(exchange.safe_params, ensure_ascii=False, sort_keys=True, default=str),
                        exchange.requested_at,
                        exchange.headers_received_at,
                        exchange.body_completed_at,
                        exchange.http_status,
                        exchange.content_type,
                        exchange.body_sha256,
                        exchange.body_bytes,
                        exchange.attempts,
                        exchange.elapsed_ms,
                        exchange.transport_error,
                        duplicate_of,
                        exchange.retry_after,
                        json.dumps(exchange.retry_history, ensure_ascii=False, sort_keys=True),
                        str(raw_path) if raw_path else None,
                        str(normalized_path) if normalized_path else None,
                    ),
                )
                self.connection.execute(
                    """INSERT INTO parse_batch
                    (exchange_id, source_id, business_code, business_message, declared_count,
                     parsed_count, parse_error, response_format)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        exchange.exchange_id,
                        spec.source_id,
                        item.batch.business_code,
                        item.batch.business_message,
                        item.batch.declared_count,
                        len(item.batch.rows),
                        item.batch.parse_error,
                        item.batch.response_format,
                    ),
                )
        except Exception:
            for artifact_path in (raw_path, normalized_path):
                if artifact_path is not None:
                    artifact_path.unlink(missing_ok=True)
            raise
        log_event(
            LOGGER,
            logging.DEBUG,
            "storage.item_saved",
            "exchange metadata and permitted artifacts were persisted",
            run_id=run.run_id,
            source_id=spec.source_id,
            exchange_id=exchange.exchange_id,
            duplicate=duplicate_of is not None,
            raw_persisted=raw_path is not None,
            normalized_persisted=normalized_path is not None,
            raw_policy=policy.get("raw"),
            normalized_policy=policy.get("normalized"),
        )

    def finish_run(self, run: CollectionRun) -> None:
        self._assert_no_secrets(
            {"failure_code": run.failure_code, "failure_message": run.failure_message},
            [],
        )
        with self.connection:
            self.connection.execute(
                """UPDATE collection_run
                SET ended_at=?, status=?, failure_code=?, failure_message=?
                WHERE run_id=?""",
                (
                    run.ended_at,
                    "FAILED" if run.failure_code else "COMPLETE",
                    run.failure_code,
                    run.failure_message,
                    run.run_id,
                ),
            )

    def save_report(self, report: ValidationReport) -> Path:
        payload = report.to_dict()
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        report_dir = self.root / "reports" / report.scope.source_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{report.report_id}.json"
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
        try:
            with self.connection:
                self.connection.execute(
                    """INSERT INTO validation_report
                    (report_id, run_id, source_id, purpose, target, verdict, scope_key,
                     manifest_sha256, evaluated_at, report_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.report_id,
                        report.run_id,
                        report.scope.source_id,
                        report.scope.purpose.value,
                        report.scope.target,
                        report.verdict.value,
                        report.scope.key(),
                        report.manifest_sha256,
                        report.evaluated_at,
                        serialized,
                    ),
                )
                self.connection.executemany(
                    """INSERT INTO quality_result
                    (report_id, check_code, check_name, status, message, metrics_json)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            report.report_id,
                            check.code,
                            check.name,
                            check.status.value,
                            check.message,
                            json.dumps(
                                check.metrics,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            ),
                        )
                        for check in report.checks
                    ],
                )
        except Exception:
            report_path.unlink(missing_ok=True)
            raise
        log_event(
            LOGGER,
            logging.DEBUG,
            "storage.report_saved",
            "validation report metadata was persisted",
            run_id=report.run_id,
            source_id=report.scope.source_id,
            report_id=report.report_id,
            verdict=report.verdict.value,
        )
        return report_path

    def get_report(self, report_or_run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT report_json FROM validation_report
            WHERE report_id=? OR run_id=? ORDER BY evaluated_at DESC LIMIT 1""",
            (report_or_run_id, report_or_run_id),
        ).fetchone()
        return json.loads(row["report_json"]) if row else None

    def quota_usage(self, credential_alias: str, kst_date: str) -> int:
        row = self.connection.execute(
            "SELECT attempt_count FROM quota_ledger WHERE credential_alias=? AND kst_date=?",
            (credential_alias, kst_date),
        ).fetchone()
        return int(row["attempt_count"]) if row else 0

    def quota_state(
        self, quota_pool: str, kst_date: str, daily_limit: int | None
    ) -> dict[str, int | None]:
        row = self.connection.execute(
            "SELECT attempt_count, reserved_count FROM quota_ledger WHERE credential_alias=? AND kst_date=?",
            (quota_pool, kst_date),
        ).fetchone()
        used = int(row["attempt_count"]) if row else 0
        reserved = int(row["reserved_count"]) if row else 0
        remaining = (
            max(0, daily_limit - used - reserved)
            if daily_limit is not None
            else None
        )
        return {
            "used": used,
            "reserved": reserved,
            "remaining": remaining,
            "daily_limit": daily_limit,
        }

    def reserve_quota(
        self,
        quota_pool: str,
        kst_date: str,
        amount: int,
        daily_limit: int | None,
        *,
        run_id: str | None = None,
        lease_seconds: int | float | None = None,
        reservation_id: str | None = None,
    ) -> str:
        if amount < 1:
            raise ValueError("quota reservation amount must be positive")
        cursor = self.connection.cursor()
        reservation_id = reservation_id or str(uuid.uuid4())
        lease_seconds = (
            self.DEFAULT_QUOTA_LEASE_SECONDS
            if lease_seconds is None
            else float(lease_seconds)
        )
        if lease_seconds <= 0:
            raise ValueError("quota lease_seconds must be positive")
        created_at = datetime.now(timezone.utc)
        expires_at = created_at.timestamp() + lease_seconds
        expires_at_iso = datetime.fromtimestamp(expires_at, timezone.utc).isoformat()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            row = cursor.execute(
                """SELECT attempt_count, reserved_count FROM quota_ledger
                WHERE credential_alias=? AND kst_date=?""",
                (quota_pool, kst_date),
            ).fetchone()
            used = int(row["attempt_count"]) if row else 0
            reserved = int(row["reserved_count"]) if row else 0
            if daily_limit is not None and used + reserved + amount > daily_limit:
                raise ValueError(
                    f"Quota admission denied for {quota_pool}: used={used}, "
                    f"reserved={reserved}, requested={amount}, limit={daily_limit}"
                )
            cursor.execute(
                """INSERT INTO quota_ledger
                (credential_alias, kst_date, attempt_count, reserved_count)
                VALUES (?, ?, 0, ?)
                ON CONFLICT(credential_alias, kst_date)
                DO UPDATE SET reserved_count=reserved_count+excluded.reserved_count""",
                (quota_pool, kst_date, amount),
            )
            cursor.execute(
                """INSERT INTO quota_reservation
                (reservation_id, credential_alias, kst_date, run_id,
                 reserved_count, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
                (
                    reservation_id,
                    quota_pool,
                    kst_date,
                    run_id,
                    amount,
                    created_at.isoformat(),
                    expires_at_iso,
                ),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        log_event(
            LOGGER,
            logging.DEBUG,
            "quota.reservation_created",
            "quota lease reservation persisted",
            reservation_id=reservation_id,
            run_id=run_id,
            quota_pool=quota_pool,
            kst_date=kst_date,
            amount=amount,
            expires_at=expires_at_iso,
        )
        return reservation_id

    def consume_quota(
        self,
        quota_pool: str,
        kst_date: str,
        amount: int,
        reservation_id: str | None = None,
    ) -> None:
        if amount < 1:
            return
        self._settle_quota(quota_pool, kst_date, amount, "CONSUMED", reservation_id)

    def release_quota(
        self,
        quota_pool: str,
        kst_date: str,
        amount: int,
        reservation_id: str | None = None,
    ) -> None:
        if amount < 1:
            return
        self._settle_quota(quota_pool, kst_date, amount, "RELEASED", reservation_id)

    def recover_expired_quota(self, now: str | datetime | None = None) -> int:
        """Release active leases whose owner disappeared before settling them.

        This is safe to call after a restart: each reservation is transitioned
        once, and the ledger is decremented in the same SQLite transaction.
        Returns the number of recovered reservations (not quota units).
        """
        now_iso = self._quota_time(now)
        cursor = self.connection.cursor()
        try:
            # Serialize recovery so two collectors starting together cannot
            # subtract the same expired reservation from the shared ledger.
            cursor.execute("BEGIN IMMEDIATE")
            rows = cursor.execute(
                """SELECT reservation_id, credential_alias, kst_date,
                          reserved_count
                   FROM quota_reservation
                   WHERE status='ACTIVE' AND expires_at<=?""",
                (now_iso,),
            ).fetchall()
            for row in rows:
                amount = int(row["reserved_count"])
                cursor.execute(
                    """UPDATE quota_ledger SET reserved_count=MAX(0, reserved_count-?)
                       WHERE credential_alias=? AND kst_date=?""",
                    (amount, row["credential_alias"], row["kst_date"]),
                )
                cursor.execute(
                    """UPDATE quota_reservation SET status='EXPIRED', reserved_count=0
                       WHERE reservation_id=? AND status='ACTIVE'""",
                    (row["reservation_id"],),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        if rows:
            log_event(
                LOGGER,
                logging.WARNING,
                "quota.expired_recovered",
                "recovered quota leases left by an interrupted collector",
                reservation_count=len(rows),
                reservation_ids=[row["reservation_id"] for row in rows],
            )
        return len(rows)

    def _settle_quota(
        self,
        quota_pool: str,
        kst_date: str,
        amount: int,
        status: str,
        reservation_id: str | None,
    ) -> None:
        with self.connection:
            if reservation_id:
                rows = self.connection.execute(
                    """SELECT reservation_id, reserved_count FROM quota_reservation
                       WHERE reservation_id=? AND credential_alias=? AND kst_date=?
                         AND status='ACTIVE'""",
                    (reservation_id, quota_pool, kst_date),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    """SELECT reservation_id, reserved_count FROM quota_reservation
                       WHERE credential_alias=? AND kst_date=? AND status='ACTIVE'
                       ORDER BY created_at, reservation_id""",
                    (quota_pool, kst_date),
                ).fetchall()
            tracked_total = sum(int(row["reserved_count"]) for row in rows)
            ledger_row = self.connection.execute(
                """SELECT reserved_count FROM quota_ledger
                   WHERE credential_alias=? AND kst_date=?""",
                (quota_pool, kst_date),
            ).fetchone()
            ledger_reserved = int(ledger_row["reserved_count"]) if ledger_row else 0
            if reservation_id and not rows:
                raise ValueError(
                    f"Quota reservation {reservation_id} is not active for {quota_pool}"
                )
            if (rows and tracked_total < amount) or (not rows and ledger_reserved < amount):
                message = (
                    f"Quota usage for {quota_pool} exceeds its reservation"
                    if status == "CONSUMED"
                    else f"Cannot release unreserved quota for {quota_pool}"
                )
                raise ValueError(message)
            if rows:
                remaining = amount
                for row in rows:
                    if remaining <= 0:
                        break
                    portion = min(remaining, int(row["reserved_count"]))
                    new_count = int(row["reserved_count"]) - portion
                    self.connection.execute(
                        """UPDATE quota_reservation
                           SET reserved_count=?, status=?
                           WHERE reservation_id=?""",
                        (new_count, status if new_count == 0 else "ACTIVE", row["reservation_id"]),
                    )
                    remaining -= portion
            self.connection.execute(
                """UPDATE quota_ledger
                   SET attempt_count=attempt_count+?, reserved_count=reserved_count-?
                   WHERE credential_alias=? AND kst_date=?""",
                (
                    amount if status == "CONSUMED" else 0,
                    amount,
                    quota_pool,
                    kst_date,
                ),
            )

    @staticmethod
    def _quota_time(value: str | datetime | None) -> str:
        if value is None:
            value = datetime.now(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return value

    def artifact_count(self, artifact_kind: str) -> int:
        column = {"raw": "raw_artifact_path", "normalized": "normalized_artifact_path"}[artifact_kind]
        row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM http_exchange WHERE {column} IS NOT NULL"
        ).fetchone()
        return int(row["count"])

    def _write_raw(
        self, run: CollectionRun, item: CollectionItem, policy: dict[str, Any]
    ) -> Path | None:
        # Persistence is default-deny even for public data: transport success
        # and credential redaction do not establish redistribution rights.
        if policy.get("raw") != "ALLOW_LOCAL_ONLY":
            return None
        path = self.root / "raw" / run.source_id / run.run_id / f"{item.exchange.exchange_id}.body.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "xb") as stream:
            stream.write(item.exchange.body)
        return path

    def _write_normalized(
        self, run: CollectionRun, item: CollectionItem, policy: dict[str, Any]
    ) -> Path | None:
        if policy.get("normalized") != "ALLOW_LOCAL_ONLY":
            return None
        path = self.root / "normalized" / run.source_id / run.run_id / f"{item.exchange.exchange_id}.jsonl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "xt", encoding="utf-8") as stream:
            for row in item.batch.rows:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
                stream.write("\n")
        return path

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
            )

    @staticmethod
    def _assert_no_secrets(value: Any, secrets: list[str]) -> None:
        if contains_secret(value, secrets):
            raise ValueError("Refusing to persist metadata containing a provider credential")
