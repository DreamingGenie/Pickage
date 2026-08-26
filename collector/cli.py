from __future__ import annotations

import argparse
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any

from .config import PACKAGE_DIR, SourceRegistry, load_env_file
from .contracts import AggregateVerdict, Purpose
from .http_client import ConfigurationError, HttpClient
from .logging_utils import LOGGER, configure_logging, log_event
from .safety import redact_text
from .service import CollectionService
from .storage import MetadataRepository


EXIT_BY_VERDICT = {
    AggregateVerdict.USABLE: 0,
    AggregateVerdict.CONDITIONAL: 2,
    AggregateVerdict.UNUSABLE: 3,
}


def _params(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Parameter must be key=value: {value}")
        key, item = value.split("=", 1)
        if not key:
            raise ValueError("Parameter name cannot be empty")
        result[key] = item
    return result


def _purpose(value: str) -> Purpose:
    try:
        return Purpose(value.upper())
    except ValueError as exc:
        choices = ", ".join(item.value for item in Purpose)
        raise argparse.ArgumentTypeError(f"Unknown purpose. Choose one of: {choices}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m collector",
        description="Collect API observations and validate purpose-scoped usability.",
    )
    # Keep all component-owned defaults under collector/ regardless of the
    # caller's current working directory in the monorepo.
    parser.add_argument("--env-file", default=str(PACKAGE_DIR / ".env.local"))
    parser.add_argument("--var-dir", default=str(PACKAGE_DIR / "var"))
    parser.add_argument("--db")
    parser.add_argument(
        "--local-policy",
        default=str(PACKAGE_DIR / "config" / "provider_policies.local.json"),
    )
    parser.add_argument(
        "--quota-config",
        default=str(PACKAGE_DIR / "config" / "quota_limits.local.json"),
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Diagnostic verbosity written to stderr",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        default="text",
        help="Human-readable text or JSON Lines on stderr",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sources", help="List configured API sources and policy state")

    collect = sub.add_parser("collect", help="Call a live API, persist allowed artifacts, and validate")
    collect.add_argument("--source", required=True)
    collect.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    collect.add_argument("--purpose", type=_purpose, default=Purpose.CONTRACT_SMOKE)
    collect.add_argument("--target")
    collect.add_argument("--count", type=int, default=1)
    collect.add_argument("--interval", type=float, default=0.0)
    collect.add_argument("--timeout", type=float, default=15.0)
    collect.add_argument("--retries", type=int, default=2)
    collect.add_argument("--allow-insecure-http", action="store_true")

    fixture = sub.add_parser("validate-file", help="Replay a JSON/XML fixture without network or credentials")
    fixture.add_argument("--source", required=True)
    fixture.add_argument("--input", action="append", required=True)
    fixture.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    fixture.add_argument("--purpose", type=_purpose, default=Purpose.CONTRACT_SMOKE)
    fixture.add_argument("--target")

    local_file = sub.add_parser(
        "collect-file",
        help="Ingest a downloaded CSV/XLSX/JSON/XML provider file and validate it",
    )
    local_file.add_argument("--source", required=True)
    local_file.add_argument("--input", action="append", required=True)
    local_file.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    local_file.add_argument("--purpose", type=_purpose, default=Purpose.CONTRACT_SMOKE)
    local_file.add_argument("--target")

    report = sub.add_parser("report", help="Read the newest report by report ID or run ID")
    report.add_argument("id")
    return parser


def _build_runtime(args: argparse.Namespace) -> tuple[SourceRegistry, MetadataRepository]:
    load_env_file(args.env_file)
    local_policy = Path(args.local_policy)
    quota_config = Path(args.quota_config)
    registry = SourceRegistry(
        local_policy_path=local_policy if local_policy.exists() else None,
        quota_override_path=quota_config if quota_config.exists() else None,
    )
    repository = MetadataRepository(root=args.var_dir, db_path=args.db)
    return registry, repository


def _credential_values(registry: SourceRegistry | None = None) -> list[str]:
    names = {
        "DATA_GO_BUS_API_KEY",
        "SEOUL_OPEN_API_KEY",
        "SEOUL_SUBWAY_REALTIME_KEY",
        "T_DATA_API_KEY",
        "DATA_GO_KMA_API_KEY",
    }
    if registry is not None:
        names.update(
            str(spec.get("auth", {}).get("env"))
            for spec in registry.list()
            if spec.get("auth", {}).get("env")
        )
    return [str(os.environ.get(name, "")) for name in names if os.environ.get(name)]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository: MetadataRepository | None = None
    secrets: list[str] = []
    try:
        load_env_file(args.env_file)
        secrets = _credential_values()
        configure_logging(
            level=args.log_level,
            output_format=args.log_format,
            secrets=secrets,
        )
        registry, repository = _build_runtime(args)
        secrets = _credential_values(registry)
        configure_logging(
            level=args.log_level,
            output_format=args.log_format,
            secrets=secrets,
        )
        log_event(
            LOGGER,
            logging.DEBUG,
            "cli.command_started",
            "collector command started",
            secrets=secrets,
            command=args.command,
        )
        if args.command == "sources":
            output = []
            for spec in registry.list():
                policy = registry.policy(spec.source_id)
                supports_live = registry.supports_live(spec.source_id)
                if supports_live:
                    try:
                        quota = registry.quota(spec.source_id)
                        quota_runnable = True
                    except ValueError:
                        quota = {
                            "status": "UNCONFIRMED",
                            "pool": spec.get("quota_pool"),
                            "daily_limit": spec.get("daily_quota"),
                        }
                        quota_runnable = False
                else:
                    quota = {
                        "status": "NOT_APPLICABLE",
                        "pool": None,
                        "daily_limit": None,
                    }
                    quota_runnable = False
                output.append(
                    {
                        "source_id": spec.source_id,
                        "name": spec.display_name,
                        "source_kind": spec.get("source_kind", "API"),
                        "collection_mode": spec.get("collection_mode", "API_POLLING"),
                        "file_formats": spec.get("file_formats", []),
                        "credential_env": spec.get("auth", {}).get("env"),
                        "transport_security": spec.get("transport_security"),
                        "purposes": spec.get("purposes", []),
                        "profiled": spec.get("profiled", False),
                        "raw_policy": policy.get("raw"),
                        "normalized_policy": policy.get("normalized"),
                        "quota_status": quota.get("status"),
                        "quota_pool": quota.get("pool"),
                        "daily_quota": quota.get("daily_limit"),
                        "live_collection_enabled": quota_runnable,
                        "file_collection_enabled": registry.supports_file(spec.source_id),
                    }
                )
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        if args.command == "report":
            report = repository.get_report(args.id)
            if report is None:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "report.not_found",
                    "no report matched the requested identifier",
                    report_or_run_id=args.id,
                )
                return 4
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        client = HttpClient(
            timeout_seconds=getattr(args, "timeout", 15.0),
            max_retries=getattr(args, "retries", 2),
        )
        service = CollectionService(registry=registry, repository=repository, http_client=client)
        params = _params(args.param)
        if args.command == "collect":
            run = service.collect_live(
                args.source,
                params,
                purpose=args.purpose,
                target=args.target,
                count=args.count,
                interval_seconds=args.interval,
                allow_insecure_http=args.allow_insecure_http,
            )
        elif args.command == "collect-file":
            run = service.collect_files(
                args.source,
                args.input,
                params=params,
                purpose=args.purpose,
                target=args.target,
            )
        else:
            run = service.collect_fixtures(
                args.source,
                args.input,
                params=params,
                purpose=args.purpose,
                target=args.target,
            )
        summary = run.to_summary()
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        verdict = run.report.verdict if run.report else AggregateVerdict.UNUSABLE
        return EXIT_BY_VERDICT[verdict]
    except (ConfigurationError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        message = redact_text(str(exc), secrets).strip() or "collector command failed"
        log_event(
            LOGGER,
            logging.ERROR,
            "cli.command_failed",
            message,
            secrets=secrets,
            command=getattr(args, "command", None),
            error_type=type(exc).__name__,
        )
        return 4
    except Exception as exc:  # pragma: no cover - defensive process boundary
        log_event(
            LOGGER,
            logging.ERROR,
            "cli.internal_failure",
            "unexpected collector failure; rerun with --log-level DEBUG",
            secrets=secrets,
            command=getattr(args, "command", None),
            error_type=type(exc).__name__,
        )
        log_event(
            LOGGER,
            logging.DEBUG,
            "cli.internal_traceback",
            "redacted traceback for debugging",
            secrets=secrets,
            command=getattr(args, "command", None),
            traceback=redact_text(traceback.format_exc(), secrets),
        )
        return 5
    finally:
        # stdout is reserved for one machine-readable JSON result; diagnostics
        # and cleanup failures always stay on stderr through structured logs.
        if repository is not None:
            try:
                repository.close()
            except Exception as exc:  # pragma: no cover - defensive shutdown path
                log_event(
                    LOGGER,
                    logging.ERROR,
                    "repository.close_failed",
                    "collector metadata database could not be closed cleanly",
                    secrets=secrets,
                    error_type=type(exc).__name__,
                )


if __name__ == "__main__":
    raise SystemExit(main())
