"""Retired BE-02 phase preflight entrypoint and read-only inspection helpers.

ADR-051 replaced phases 1/3/4 with a fresh-only irreversible MVP baseline.
The CLI refuses retired operations; it does not inspect or migrate a database.
The explicit-module inspection helpers remain available to existing callers.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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
_RETIRED_PHASE = (
    "BE-02 phases 1, 3, and 4 were retired by ADR-051: the fresh-only MVP "
    "baseline 202611020000 has no pre-squash upgrade path. "
    "See docs/adr/ADR-051-mvp-migration-baseline-squash.md and run "
    "scripts/quality/audit_model_defaults.py for the current source inventory. "
    "That inventory is not deployed-catalog proof; BE-02 remains open pending "
    "current-baseline PostgreSQL catalog verification."
)
_UNSUPPORTED_PHASE = (
    "Historical BE-02 DDL phases were 1, 3, and 4 (now retired); "
    "phase 2 is Python-only and has no catalog DDL"
)


@dataclass(frozen=True)
class ColumnResult:
    column: str
    status: str
    detail: str
    phase: int = 4


def load_migration(phase: int = 4) -> ModuleType:
    """Reject retired migration loading without importing historical source."""

    if isinstance(phase, bool) or phase not in MIGRATION_PATHS:
        raise ValueError(_UNSUPPORTED_PHASE)
    raise RuntimeError(_RETIRED_PHASE)


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
            "retired historical phase option retained for compatibility only; "
            "no phase is executed; phase 2 is Python-only and has no catalog "
            "DDL (default: 4)"
        ),
    )
    parser.add_argument(
        "--database-url-env",
        default="DATABASE_URL",
        help=(
            "historical compatibility option only; the named environment "
            "variable is not read and no database URL is used"
        ),
    )
    parser.parse_args(argv)
    print(_RETIRED_PHASE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
