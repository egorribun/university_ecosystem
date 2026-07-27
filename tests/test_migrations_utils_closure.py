"""Closure tests for the Alembic migration status cache."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils import migrations


def _connection(rows: list[tuple[str, ...]]) -> AsyncMock:
    connection = AsyncMock()
    connection.execute = AsyncMock(return_value=rows)
    return connection


@pytest.mark.asyncio
async def test_migrations_are_current_uses_connection_and_caches_result():
    migrations.reset_migration_cache()
    connection = _connection([("head",)])
    script = MagicMock()
    script.get_heads.return_value = ["head"]

    with patch.object(migrations, "get_alembic_script", return_value=script):
        result = await migrations.migrations_are_current(conn=connection)
        cached = await migrations.migrations_are_current(conn=connection)

    assert result == (True, {"head"}, {"head"})
    assert cached == result
    connection.execute.assert_awaited_once()
    script.get_heads.assert_called_once()


@pytest.mark.asyncio
async def test_migrations_are_current_uses_engine_when_connection_is_missing():
    migrations.reset_migration_cache()
    connection = _connection([("old",)])
    engine = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=None)
    engine.connect.return_value = context
    script = MagicMock()
    script.get_heads.return_value = ["head"]

    with patch.object(migrations, "get_alembic_script", return_value=script):
        result = await migrations.migrations_are_current(engine=engine)

    assert result == (False, {"old"}, {"head"})
    engine.connect.assert_called_once_with()
    connection.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_migrations_are_current_requires_connection_or_engine():
    migrations.reset_migration_cache()

    with pytest.raises(ValueError, match="Either conn or engine"):
        await migrations.migrations_are_current()


def test_get_alembic_script_is_cached_and_reset_clears_status():
    migrations.get_alembic_script.cache_clear()

    first = migrations.get_alembic_script()
    second = migrations.get_alembic_script()
    assert first is second

    migrations._migration_cache["expires_at"] = 1.0
    migrations._migration_cache["result"] = (True, {"head"}, {"head"})
    migrations.reset_migration_cache()
    assert migrations._migration_cache == {"expires_at": 0.0, "result": ()}
