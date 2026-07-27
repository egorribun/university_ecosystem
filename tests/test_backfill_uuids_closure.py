"""Closure tests for UUID backfill mapping, batching, and rollback paths."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scripts import backfill_uuids


@pytest.mark.asyncio
async def test_get_user_id_map_skips_rows_without_uuid():
    session = AsyncMock()

    async def rows():
        yield SimpleNamespace(id=1, uuid_id=None)
        yield SimpleNamespace(id=2, uuid_id="uuid-2")

    session.stream.return_value = rows()

    fake_user = SimpleNamespace(id=MagicMock(), uuid_id=MagicMock())
    with (
        patch.object(backfill_uuids, "User", fake_user),
        patch.object(backfill_uuids, "select", return_value=MagicMock()),
    ):
        assert await backfill_uuids.get_user_id_map(session) == {2: "uuid-2"}


@pytest.mark.asyncio
async def test_backfill_own_uuids_normalizes_naive_timestamp_and_missing_field():
    class DummyModel:
        __tablename__ = "dummy"
        uuid_id = MagicMock()

    naive = datetime(2026, 1, 1, 12, 0)
    first = SimpleNamespace(uuid_id=None, created_at=naive)
    second = SimpleNamespace(uuid_id=None)
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    session = AsyncMock()
    result_first = MagicMock()
    result_first.scalars.return_value.all.return_value = [first]
    result_second = MagicMock()
    result_second.scalars.return_value.all.return_value = [second]
    session.execute.side_effect = [result_first, empty, result_second, empty]

    with (
        patch.object(
            backfill_uuids,
            "TABLES_OWN_ID",
            [(DummyModel, "created_at"), (DummyModel, None)],
        ),
        patch.object(backfill_uuids, "select", return_value=MagicMock()),
        patch.object(
            backfill_uuids, "generate_uuid7", side_effect=["uuid-1", "uuid-2"]
        ) as generate,
    ):
        await backfill_uuids.backfill_own_uuids(session)

    assert first.uuid_id == "uuid-1"
    assert second.uuid_id == "uuid-2"
    assert generate.call_args_list[0].args[0].tzinfo is UTC
    assert generate.call_args_list[1].args[0] is None


@pytest.mark.asyncio
async def test_backfill_foreign_uuids_counts_unknown_legacy_users_as_skipped():
    class DummyModel:
        __tablename__ = "dummy_fk"
        user_id = MagicMock()
        shadow_user_id = MagicMock()

    linked = SimpleNamespace(user_id=1, shadow_user_id=None)
    skipped = SimpleNamespace(user_id=2, shadow_user_id=None)
    result = MagicMock()
    result.scalars.return_value.all.side_effect = [[linked, skipped], []]
    session = AsyncMock()
    session.execute.return_value = result

    with (
        patch.object(
            backfill_uuids,
            "TABLES_USER_FK",
            [(DummyModel, "user_id", "shadow_user_id")],
        ),
        patch.object(backfill_uuids, "select", return_value=MagicMock()),
    ):
        await backfill_uuids.backfill_foreign_uuids(session, {1: "uuid-1"})

    assert linked.shadow_user_id == "uuid-1"
    assert skipped.shadow_user_id is None
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_main_rolls_back_after_backfill_failure():
    session = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(backfill_uuids, "async_session", return_value=session_context),
        patch.object(
            backfill_uuids,
            "backfill_own_uuids",
            new=AsyncMock(side_effect=RuntimeError("broken migration")),
        ),
        patch.object(backfill_uuids.logger, "error") as error,
    ):
        await backfill_uuids.main()

    session.rollback.assert_awaited_once_with()
    error.assert_called_once()
