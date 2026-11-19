"""Closure tests for UUID backfill mapping, batching, and rollback paths."""

from __future__ import annotations

import asyncio
import runpy
from datetime import UTC, datetime
from pathlib import Path
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
        id = MagicMock()
        user_id = MagicMock()
        shadow_user_id = MagicMock()

    DummyModel.id.__gt__.return_value = MagicMock(name="after_page")

    linked = SimpleNamespace(id=10, user_id=1, shadow_user_id=None)
    skipped = SimpleNamespace(id=11, user_id=2, shadow_user_id=None)
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
async def test_backfill_foreign_uuids_pages_past_unmapped_rows():
    class DummyModel:
        __tablename__ = "dummy_fk"
        id = MagicMock()
        user_id = MagicMock()
        shadow_user_id = MagicMock()

    DummyModel.id.__gt__.return_value = MagicMock(name="after_page")

    unmapped = SimpleNamespace(id=7, user_id=99, shadow_user_id=None)
    result = MagicMock()
    # A real database returns the unmapped row again unless the next page
    # starts after it; the keyset filter is what ends the scan.
    result.scalars.return_value.all.side_effect = [[unmapped], []]
    session = AsyncMock()
    session.execute.return_value = result
    select = MagicMock()

    with (
        patch.object(
            backfill_uuids,
            "TABLES_USER_FK",
            [(DummyModel, "user_id", "shadow_user_id")],
        ),
        patch.object(backfill_uuids, "select", select),
    ):
        await backfill_uuids.backfill_foreign_uuids(session, {})

    first, second = select.return_value.where.call_args_list
    assert len(first.args) == 2
    assert len(second.args) == 3
    DummyModel.id.__gt__.assert_called_once_with(7)
    assert second.args[2] is DummyModel.id.__gt__.return_value
    assert unmapped.shadow_user_id is None
    assert session.execute.await_count == 2


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
        assert await backfill_uuids.main() == 1

    session.rollback.assert_awaited_once_with()
    error.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_phase", ["own", "map", "foreign", None])
async def test_main_status_preserves_phase_order_and_rollback(failed_phase):
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    user_map = {1: "synthetic-uuid"}
    phases = {
        "own": AsyncMock(),
        "map": AsyncMock(return_value=user_map),
        "foreign": AsyncMock(),
    }
    if failed_phase is not None:
        phases[failed_phase].side_effect = RuntimeError("synthetic backfill failure")

    with (
        patch.object(backfill_uuids, "async_session", return_value=context),
        patch.object(backfill_uuids, "configure_logging"),
        patch.object(backfill_uuids, "backfill_own_uuids", phases["own"]),
        patch.object(backfill_uuids, "get_user_id_map", phases["map"]),
        patch.object(backfill_uuids, "backfill_foreign_uuids", phases["foreign"]),
        patch.object(backfill_uuids.logger, "info") as info,
        patch.object(backfill_uuids.logger, "error") as error,
    ):
        result = await backfill_uuids.main()

    assert result == (0 if failed_phase is None else 1)
    phases["own"].assert_awaited_once_with(session)
    if failed_phase == "own":
        phases["map"].assert_not_awaited()
    else:
        phases["map"].assert_awaited_once_with(session)
    if failed_phase in ("own", "map"):
        phases["foreign"].assert_not_awaited()
    else:
        phases["foreign"].assert_awaited_once_with(session, user_map)
    if failed_phase is None:
        session.rollback.assert_not_awaited()
        error.assert_not_called()
        info.assert_called_once_with("Backfill complete!")
    else:
        session.rollback.assert_awaited_once_with()
        error.assert_called_once()
        info.assert_not_called()
    context.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("status", [0, 1])
def test_direct_entrypoint_propagates_main_status_without_extra_output(status, capsys):
    def run(coroutine):
        assert coroutine.cr_code.co_name == "main"
        coroutine.close()
        return status

    with patch.object(asyncio, "run", side_effect=run) as execute:
        with pytest.raises(SystemExit) as raised:
            runpy.run_path(str(Path(backfill_uuids.__file__)), run_name="__main__")

    assert raised.value.code == status
    execute.assert_called_once()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""
