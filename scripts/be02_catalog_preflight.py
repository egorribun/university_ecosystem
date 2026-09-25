"""Read-only BE-02 phase-four catalog preflight for a deployed PostgreSQL.

Alembic revision ``202609250001`` validates every target column under
ACCESS EXCLUSIVE locks and aborts before its first ALTER TABLE. This command
runs the *same* validation ahead of a deployment, inside a READ ONLY
transaction and without taking table locks, so operators learn about catalog
drift (types, enum labels, NULL rows, conflicting defaults) before a release
window. It never writes. The database URL is read from ``DATABASE_URL`` (or
``--database-url-env``), never from command arguments.
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
MIGRATION_PATH = ROOT / "alembic/versions/202609250001_phase_semantic_defaults.py"


@dataclass(frozen=True)
class ColumnResult:
    column: str
    status: str
    detail: str


def load_migration(path: Path = MIGRATION_PATH) -> ModuleType:
    """Import the reviewed migration so the preflight cannot drift from it."""

    spec = importlib.util.spec_from_file_location("be02_phase_four", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load BE-02 migration from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sync_url(url: str) -> str:
    """Use the synchronous psycopg driver for an async application URL."""

    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def inspect_catalog(connection: Any, migration: ModuleType) -> list[ColumnResult]:
    """Validate every BE-02 target column; ``pending`` means the ALTER will run."""

    schema = migration._target_schema(connection)
    results: list[ColumnResult] = []
    for spec in migration.DEFAULT_SPECS:
        column = f"{schema}.{spec.table}.{spec.column}"
        try:
            state = migration._catalog_state(connection, spec, schema)
            migration._validate_state(spec, state)
        except RuntimeError as error:
            results.append(ColumnResult(column, "blocked", str(error)))
            continue
        if state.default_sql is None:
            results.append(ColumnResult(column, "pending", spec.expression))
        else:
            results.append(ColumnResult(column, "converged", state.default_sql))
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
        "--database-url-env",
        default="DATABASE_URL",
        help="environment variable holding the target database URL",
    )
    args = parser.parse_args(argv)
    url = os.environ.get(args.database_url_env, "").strip()
    if not url:
        print(f"{args.database_url_env} is not set", file=sys.stderr)
        return 2
    results = run(url, load_migration())
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 1 if any(result.status == "blocked" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
