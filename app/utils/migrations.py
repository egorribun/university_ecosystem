from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from alembic.config import Config
from alembic.script import ScriptDirectory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


@lru_cache
def get_alembic_script() -> ScriptDirectory:
    """Load Alembic script directory configuration."""
    # Assumes structure: project_root/app/utils/migrations.py
    # parents[2] gets to project_root
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return ScriptDirectory.from_config(config)


_migration_cache: dict[str, Any] = {
    "expires_at": 0.0,
    "result": (),
}


async def migrations_are_current(
    conn: AsyncConnection | None = None,
    engine: Any | None = None,
) -> tuple[bool, set[str], set[str]]:
    """
    Check if the database schema is up-to-date with Alembic heads.
    Uses a 60-second cache to avoid heavy DB queries on every health probe.
    """
    now = time.monotonic()
    if _migration_cache["expires_at"] > now:
        return _migration_cache["result"]

    script = get_alembic_script()
    expected_heads = set(script.get_heads())

    async def _fetch(c):
        result = await c.execute(text("SELECT version_num FROM alembic_version"))
        return {row[0] for row in result}

    if conn:
        current_versions = await _fetch(conn)
    elif engine:
        async with engine.connect() as conn_new:
            current_versions = await _fetch(conn_new)
    else:
        raise ValueError("Either conn or engine must be provided")

    res = (
        current_versions == expected_heads,
        current_versions,
        expected_heads,
    )
    _migration_cache.update(
        {
            "expires_at": now + 60.0,
            "result": res,
        }
    )
    return res


def reset_migration_cache() -> None:
    """Clear the migration status cache."""
    _migration_cache.update({"expires_at": 0.0, "result": ()})
