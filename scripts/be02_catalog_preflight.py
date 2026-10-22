"""Read-only BE-02 catalog preflight for a deployed PostgreSQL DDL phase.

The selected Alembic phase validates its target columns before DDL. This
command runs the same migration-owned catalog checks inside a READ ONLY
transaction and without taking table locks, so operators can inspect catalog
drift before a release window. It never writes. The database URL is read from
``DATABASE_URL`` (or ``--database-url-env``), never from command arguments.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATHS = {
    1: ROOT / "alembic/versions/202609150001_phase_auth_boolean_defaults.py",
    3: ROOT / "alembic/versions/202609220001_phase_literal_scalar_defaults.py",
    4: ROOT / "alembic/versions/202609250001_phase_semantic_defaults.py",
}
MIGRATION_PATH = MIGRATION_PATHS[4]
_UNSUPPORTED_PHASE = (
    "BE-02 preflight supports DDL phases 1, 3, and 4; "
    "phase 2 is Python-only and has no catalog DDL"
)


@dataclass(frozen=True)
class ColumnResult:
    column: str
    status: str
    detail: str
    phase: int = 4


def load_migration(phase: int = 4) -> ModuleType:
    """Import the reviewed migration so the preflight cannot drift from it."""

    if isinstance(phase, bool) or phase not in MIGRATION_PATHS:
        raise ValueError(_UNSUPPORTED_PHASE)
    path = MIGRATION_PATHS[phase]
    spec = importlib.util.spec_from_file_location(f"be02_phase_{phase}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load BE-02 migration from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__dict__["BE02_PHASE"] = phase
    return module


def sync_url(url: str) -> str:
    """Use the synchronous psycopg driver for an async application URL."""

    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def _target_relation_kind(connection: Any, schema: str, table: str) -> str | None:
    """Return the target relation kind for phases whose migration omits it."""

    result = connection.execute(
        sa.text(
            """
            SELECT relation.relkind::text
              FROM pg_catalog.pg_class AS relation
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname = :schema_name
               AND relation.relname = :table_name
            """
        ),
        {"schema_name": schema, "table_name": table},
    ).scalar_one_or_none()
    return None if result is None else str(result)


def inspect_catalog(connection: Any, migration: ModuleType) -> list[ColumnResult]:
    """Validate every BE-02 target column; ``pending`` means the ALTER will run."""

    phase = getattr(migration, "BE02_PHASE", 4)
    if isinstance(phase, bool) or phase not in MIGRATION_PATHS:
        raise ValueError(_UNSUPPORTED_PHASE)
    if hasattr(migration, "_target_schema"):
        schema = migration._target_schema(connection)
    else:
        schema = connection.execute(
            sa.text("SELECT current_schema()")
        ).scalar_one_or_none()
        if not schema or not isinstance(schema, str):
            raise RuntimeError("BE-02 requires a current PostgreSQL schema")

    results: list[ColumnResult] = []
    relation_kinds: dict[str, str | None] = {}
    for spec in migration.DEFAULT_SPECS:
        column = f"{schema}.{spec.table}.{spec.column}"
        try:
            if phase in {1, 3}:
                if spec.table not in relation_kinds:
                    relation_kinds[spec.table] = _target_relation_kind(
                        connection, schema, spec.table
                    )
                relation_kind = relation_kinds[spec.table]
                if relation_kind not in {"r", "p"}:
                    if relation_kind is None:
                        kind_name = "missing relation"
                    else:
                        kind_name = {
                            "f": "foreign table",
                            "i": "index",
                            "I": "partitioned index",
                            "m": "materialized view",
                            "S": "sequence",
                            "t": "TOAST relation",
                            "v": "view",
                        }.get(relation_kind, f"relation kind {relation_kind!r}")
                    raise RuntimeError(
                        f"BE-02 phase {phase} requires an ordinary or partitioned "
                        f"table for {schema}.{spec.table}; found {kind_name}"
                    )
            if phase == 4:
                state = migration._catalog_state(connection, spec, schema)
                migration._validate_state(spec, state)
                status = "pending" if state.default_sql is None else "converged"
                detail = spec.expression if status == "pending" else state.default_sql
            else:
                state = migration._catalog_state(connection, spec)
                migration._validate_existing_default(spec, state)
                null_count = migration._null_count(connection, spec)
                check_name, check_validated, _ = migration._matching_check(
                    connection, spec
                )
                pending = []
                if state.default_sql is None:
                    pending.append(f"server default {spec.server_default}")
                if null_count:
                    pending.append(f"backfill {null_count} NULL row(s)")
                if not state.not_null:
                    pending.append("NOT NULL contract")
                if check_name is not None and not check_validated:
                    pending.append(f"validate check {check_name}")
                status = "pending" if pending else "converged"
                detail = "; ".join(pending) if pending else state.default_sql
        except RuntimeError as error:
            results.append(ColumnResult(column, "blocked", str(error), phase))
            continue
        results.append(ColumnResult(column, status, detail, phase))
    return results


def run(url: str, migration: ModuleType) -> list[ColumnResult]:
    engine = sa.create_engine(sync_url(url))
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            return inspect_catalog(connection, migration)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        type=int,
        choices=tuple(MIGRATION_PATHS),
        default=4,
        help=(
            "BE-02 DDL phase to inspect; phase 2 is Python-only and has no "
            "catalog DDL (default: 4)"
        ),
    )
    parser.add_argument(
        "--database-url-env",
        default="DATABASE_URL",
        help="environment variable holding the target database URL",
    )
    args = parser.parse_args(argv)
    url = os.environ.get(args.database_url_env, "").strip()
    if not url:
        print(f"{args.database_url_env} is not set", file=sys.stderr)
        return 2
    results = run(url, load_migration(args.phase))
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 1 if any(result.status == "blocked" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
