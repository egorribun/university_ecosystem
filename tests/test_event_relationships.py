"""Event creator/attendee SpiceDB relation writes: writer, outbox handler, backfill."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import grpc.aio
import pytest
from authzed.api.v1 import RelationshipUpdate

from app.auth import relationships
from app.auth.relationships import (
    ATTENDEE_RELATION,
    CREATOR_RELATION,
    EventRelationshipWriter,
    RelationshipWriteError,
    build_event_relationship_update,
    sync_event_attendee,
    sync_event_creator,
)
from scripts import backfill_event_relationships as backfill


def _stub_with(write_mock: AsyncMock) -> MagicMock:
    stub = MagicMock()
    stub.WriteRelationships = write_mock
    return stub


def _written_updates(write_mock: AsyncMock) -> list[RelationshipUpdate]:
    """Every update across all WriteRelationships calls, in send order."""
    return [
        update for call in write_mock.await_args_list for update in call.args[0].updates
    ]


# ---------------------------------------------------------------------------
# Writer: builds the expected RelationshipUpdate objects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_touch_creator_writes_event_creator_relationship():
    event_id, user_id = uuid4(), uuid4()
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        await EventRelationshipWriter(MagicMock()).touch_creator(event_id, user_id)

    (update,) = _written_updates(write)
    assert update.operation == RelationshipUpdate.OPERATION_TOUCH
    relationship = update.relationship
    assert relationship.resource.object_type == "event"
    assert relationship.resource.object_id == str(event_id)
    assert relationship.relation == CREATOR_RELATION
    assert relationship.subject.object.object_type == "user"
    assert relationship.subject.object.object_id == str(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "operation", "relation"),
    [
        ("touch_creator", RelationshipUpdate.OPERATION_TOUCH, CREATOR_RELATION),
        ("delete_creator", RelationshipUpdate.OPERATION_DELETE, CREATOR_RELATION),
        ("touch_attendee", RelationshipUpdate.OPERATION_TOUCH, ATTENDEE_RELATION),
        ("delete_attendee", RelationshipUpdate.OPERATION_DELETE, ATTENDEE_RELATION),
    ],
)
async def test_each_writer_operation_maps_to_its_relation(method, operation, relation):
    event_id, user_id = uuid4(), uuid4()
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        await getattr(EventRelationshipWriter(MagicMock()), method)(event_id, user_id)

    (update,) = _written_updates(write)
    assert update.operation == operation
    assert update.relationship.relation == relation
    assert update.relationship.resource.object_id == str(event_id)
    assert update.relationship.subject.object.object_id == str(user_id)


def test_build_update_accepts_legacy_integer_ids():
    update = build_event_relationship_update(
        operation="touch", relation=ATTENDEE_RELATION, event_id=7, user_id=9
    )
    assert update.relationship.resource.object_id == "7"
    assert update.relationship.subject.object.object_id == "9"


def test_build_update_rejects_unknown_operation_and_relation():
    with pytest.raises(ValueError, match="operation"):
        build_event_relationship_update(
            operation="upsert", relation=CREATOR_RELATION, event_id=1, user_id=1
        )
    with pytest.raises(ValueError, match="relation"):
        build_event_relationship_update(
            operation="touch", relation="viewer", event_id=1, user_id=1
        )


@pytest.mark.asyncio
async def test_write_failure_raises_typed_error():
    write = AsyncMock(
        side_effect=grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="down",
        )
    )
    with (
        patch.object(
            relationships, "PermissionsServiceStub", return_value=_stub_with(write)
        ),
        pytest.raises(RelationshipWriteError),
    ):
        await EventRelationshipWriter(MagicMock()).touch_creator(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_empty_write_sends_nothing():
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        await EventRelationshipWriter(MagicMock()).write([])
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_event_attendee_is_best_effort_and_logs_warning():
    write = AsyncMock(side_effect=RelationshipWriteError("down"))
    channel = MagicMock()
    with (
        patch.object(
            relationships,
            "acquire_shared_spicedb_channel",
            AsyncMock(return_value=channel),
        ),
        patch.object(
            relationships, "PermissionsServiceStub", return_value=_stub_with(write)
        ),
        patch.object(relationships.logger, "warning") as warning,
    ):
        # Must not raise: the attendance commit has already succeeded.
        await sync_event_attendee(uuid4(), uuid4(), attending=True)

    warning.assert_called_once()
    assert warning.call_args.args[0] == "event_attendee_relationship_sync_failed"


# ---------------------------------------------------------------------------
# Best-effort creator sync (called after the event commit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_event_creator_touches_creator(mock_spicedb_relationship_writes):
    event_id, user_id = uuid4(), uuid4()
    await sync_event_creator(event_id, user_id)

    (update,) = _written_updates(mock_spicedb_relationship_writes.WriteRelationships)
    assert update.operation == RelationshipUpdate.OPERATION_TOUCH
    assert update.relationship.relation == CREATOR_RELATION
    assert update.relationship.resource.object_id == str(event_id)
    assert update.relationship.subject.object.object_id == str(user_id)


@pytest.mark.asyncio
async def test_sync_event_creator_is_noop_without_creator(
    mock_spicedb_relationship_writes,
):
    await sync_event_creator(uuid4(), None)
    mock_spicedb_relationship_writes.WriteRelationships.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_event_creator_is_best_effort_and_logs_warning(
    mock_spicedb_relationship_writes,
):
    mock_spicedb_relationship_writes.WriteRelationships.side_effect = (
        RelationshipWriteError("down")
    )
    event_id = uuid4()
    with patch.object(relationships.logger, "warning") as warning:
        # Must not raise: the event commit has already succeeded.
        await sync_event_creator(event_id, uuid4())

    warning.assert_called_once()
    assert warning.call_args.args[0] == "event_creator_relationship_sync_failed"
    assert warning.call_args.kwargs["event_id"] == str(event_id)


# ---------------------------------------------------------------------------
# Backfill: batching and idempotence
# ---------------------------------------------------------------------------


def _pages_from(rows: list[tuple[UUID, list[RelationshipUpdate]]]):
    """Fake keyset fetcher over ``rows`` sorted by key, honouring ``after``/limit."""
    calls: list[tuple[object, int]] = []

    async def fetch(after, limit):
        calls.append((after, limit))
        remaining = [row for row in rows if after is None or row[0] > after]
        return remaining[:limit]

    return fetch, calls


def _creator_rows(count: int) -> list[tuple[UUID, list[RelationshipUpdate]]]:
    rows = []
    for _ in range(count):
        event_id = uuid4()
        rows.append(
            (
                event_id,
                [
                    build_event_relationship_update(
                        operation="touch",
                        relation=CREATOR_RELATION,
                        event_id=event_id,
                        user_id=uuid4(),
                    )
                ],
            )
        )
    return sorted(rows, key=lambda row: row[0])


@pytest.mark.asyncio
async def test_backfill_walks_all_pages_in_batches():
    rows = _creator_rows(5)
    fetch, calls = _pages_from(rows)
    write = AsyncMock(return_value=None)
    writer = EventRelationshipWriter(MagicMock())
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        processed = await backfill.apply_pages(fetch, writer, batch_size=2)

    assert processed == 5
    # Pages of 2, 2, 1; the short final page ends the walk without an extra fetch.
    assert [limit for _, limit in calls] == [2, 2, 2]
    assert calls[0][0] is None
    assert calls[1][0] == rows[1][0]
    assert calls[2][0] == rows[3][0]
    assert write.await_count == 3
    written = [u.relationship.resource.object_id for u in _written_updates(write)]
    assert written == [str(row[0]) for row in rows]


@pytest.mark.asyncio
async def test_backfill_chunks_writes_below_spicedb_update_cap():
    rows = _creator_rows(250)
    fetch, _ = _pages_from(rows)
    write = AsyncMock(return_value=None)
    writer = EventRelationshipWriter(MagicMock())
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        processed = await backfill.apply_pages(fetch, writer, batch_size=250)

    assert processed == 250
    sizes = [len(call.args[0].updates) for call in write.await_args_list]
    assert sizes == [backfill.WRITE_CHUNK_SIZE, backfill.WRITE_CHUNK_SIZE, 50]


@pytest.mark.asyncio
async def test_backfill_is_idempotent_across_reruns():
    rows = _creator_rows(4)
    write = AsyncMock(return_value=None)
    writer = EventRelationshipWriter(MagicMock())

    def fresh_fetch():
        fetch, _ = _pages_from(rows)
        return fetch

    def summary() -> list[tuple[int, str, str]]:
        return [
            (u.operation, u.relationship.resource.object_id, u.relationship.relation)
            for u in _written_updates(write)
        ]

    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        await backfill.apply_pages(fresh_fetch(), writer, batch_size=3)
        first = summary()
        write.reset_mock()
        await backfill.apply_pages(fresh_fetch(), writer, batch_size=3)
        second = summary()

    # Every write is a TOUCH on the same relations, so a rerun converges to the same state.
    assert len(first) == 4
    assert first == second
    assert all(op == RelationshipUpdate.OPERATION_TOUCH for op, _, _ in first)


@pytest.mark.asyncio
async def test_backfill_with_no_rows_writes_nothing():
    fetch, _ = _pages_from([])
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        processed = await backfill.apply_pages(
            fetch, EventRelationshipWriter(MagicMock()), batch_size=10
        )
    assert processed == 0
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_rejects_non_positive_batch_size():
    fetch, _ = _pages_from([])
    with pytest.raises(ValueError, match="batch_size"):
        await backfill.apply_pages(
            fetch, EventRelationshipWriter(MagicMock()), batch_size=0
        )


@pytest.mark.asyncio
async def test_run_backfill_requires_configured_mvp_tenant(monkeypatch):
    monkeypatch.setattr(backfill, "settings", SimpleNamespace(mvp_tenant_id=None))
    with pytest.raises(RuntimeError, match="MVP_TENANT_ID"):
        await backfill.run_backfill(batch_size=10)


@pytest.mark.asyncio
async def test_run_backfill_restores_tenant_context(monkeypatch):
    from app.core.tenant import get_current_tenant

    tenant = uuid4()
    monkeypatch.setattr(backfill, "settings", SimpleNamespace(mvp_tenant_id=tenant))
    monkeypatch.setattr(backfill, "init_database", lambda: None)
    seen_tenants: list[str] = []

    class _Session:
        async def __aenter__(self):
            seen_tenants.append(get_current_tenant())
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(backfill, "async_session", lambda: _Session())
    monkeypatch.setattr(backfill, "require_mvp_tenant", AsyncMock(return_value=tenant))
    monkeypatch.setattr(
        backfill,
        "acquire_shared_spicedb_channel",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        backfill,
        "apply_pages",
        AsyncMock(return_value=0),
    )
    close = AsyncMock(return_value=None)
    monkeypatch.setattr(backfill, "close_global_spicedb_channel", close)

    assert await backfill.run_backfill(batch_size=10) == (0, 0)
    assert seen_tenants == [str(tenant)]
    assert get_current_tenant() == ""
    close.assert_awaited_once()


def test_backfill_main_prints_counts(monkeypatch, capsys):
    monkeypatch.setattr(
        backfill,
        "run_backfill",
        AsyncMock(return_value=(3, 2)),
    )
    monkeypatch.setattr("sys.argv", ["backfill", "--batch-size", "7"])
    backfill.main()
    out = capsys.readouterr().out
    assert "creator relations: 3" in out
    assert "attendee relations: 2" in out


@pytest.mark.asyncio
async def test_shared_channel_fails_closed_when_creation_yields_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import spicedb as spicedb_module

    monkeypatch.setattr(spicedb_module, "_global_channel", None)
    monkeypatch.setattr(
        spicedb_module, "create_async_spicedb_channel", lambda *a, **k: None
    )

    with pytest.raises(RuntimeError, match="SpiceDB async channel is unavailable"):
        await spicedb_module.acquire_shared_spicedb_channel()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_cursor", [False, True])
async def test_creator_backfill_page_preserves_keyset_and_relationships(
    monkeypatch, has_cursor
):
    event_id, user_id = uuid4(), uuid4()
    cursor = uuid4() if has_cursor else None
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(event_id, user_id), (uuid4(), None)]
    )
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(backfill, "async_session", lambda: context)

    page = await backfill._fetch_creator_page(cursor, 7)

    assert len(page) == 1
    row_id, (update,) = page[0]
    assert row_id == event_id
    assert update == build_event_relationship_update(
        operation="touch", relation=CREATOR_RELATION, event_id=event_id, user_id=user_id
    )
    (statement,) = session.execute.await_args.args
    sql = str(statement)
    assert "events.created_by IS NOT NULL" in sql
    assert "ORDER BY events.id" in sql
    assert ("events.id >" in sql) is has_cursor
    assert 7 in statement.compile().params.values()
    if has_cursor:
        assert cursor in statement.compile().params.values()
    context.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("has_cursor", [False, True])
async def test_attendee_backfill_page_uses_attendance_key_and_relationship(
    monkeypatch, has_cursor
):
    attendance_id, event_id, user_id = uuid4(), uuid4(), uuid4()
    cursor = uuid4() if has_cursor else None
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(attendance_id, event_id, user_id)]
    )
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(backfill, "async_session", lambda: context)

    page = await backfill._fetch_attendee_page(cursor, 9)

    assert len(page) == 1
    row_id, (update,) = page[0]
    assert row_id == attendance_id
    assert update == build_event_relationship_update(
        operation="touch",
        relation=ATTENDEE_RELATION,
        event_id=event_id,
        user_id=user_id,
    )
    (statement,) = session.execute.await_args.args
    sql = str(statement)
    assert "ORDER BY event_attendance.id" in sql
    assert ("event_attendance.id >" in sql) is has_cursor
    assert 9 in statement.compile().params.values()
    if has_cursor:
        assert cursor in statement.compile().params.values()
    context.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("after", "limit", "expected_ids"),
    [(None, 10, [4, 6]), (None, 1, [4]), (4, 1, [6]), (6, 1, [])],
)
async def test_attendee_backfill_requires_tenant_visible_event_and_user(
    monkeypatch, after, limit, expected_ids
):
    """Execute the actual query against each parent's tenant-visible row set.

    Attendance has no tenant column or RLS policy. Its event and user parents
    must both be joined before LIMIT. SQLite supplies the relational negative
    controls here, not evidence that PostgreSQL's RLS policies are enforced.
    """
    from contextlib import asynccontextmanager

    from sqlalchemy import Column, MetaData, Table, Uuid, create_engine

    metadata = MetaData()
    attendance = Table(
        "event_attendance",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("event_id", Uuid, nullable=False),
        Column("user_id", Uuid, nullable=False),
    )
    events = Table("events", metadata, Column("id", Uuid, primary_key=True))
    users = Table("users", metadata, Column("id", Uuid, primary_key=True))
    (
        visible_event,
        second_visible_event,
        hidden_event,
        second_hidden_event,
        visible_user,
        hidden_user,
    ) = (uuid4() for _ in range(6))
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            # These parent tables represent only rows visible in this tenant.
            # The unscoped child still contains all four event/user combinations.
            connection.execute(
                events.insert(),
                [{"id": visible_event}, {"id": second_visible_event}],
            )
            connection.execute(users.insert(), [{"id": visible_user}])
            connection.execute(
                attendance.insert(),
                [
                    {"id": UUID(int=key), "event_id": event, "user_id": user}
                    for key, event, user in [
                        (1, hidden_event, hidden_user),
                        (2, visible_event, hidden_user),
                        (3, hidden_event, visible_user),
                        (4, visible_event, visible_user),
                        (5, second_hidden_event, hidden_user),
                        (6, second_visible_event, visible_user),
                    ]
                ],
            )

            async def execute(statement):
                return connection.execute(statement)

            @asynccontextmanager
            async def session():
                yield SimpleNamespace(execute=execute)

            monkeypatch.setattr(backfill, "async_session", session)
            page = await backfill._fetch_attendee_page(
                UUID(int=after) if after is not None else None, limit
            )

        assert [key.int for key, _ in page] == expected_ids
        expected_events = {4: visible_event, 6: second_visible_event}
        for key, updates in page:
            (update,) = updates
            assert update.operation == RelationshipUpdate.OPERATION_TOUCH
            assert update.relationship.resource.object_type == "event"
            assert update.relationship.resource.object_id == str(
                expected_events[key.int]
            )
            assert update.relationship.relation == "attendee"
            assert update.relationship.subject.object.object_type == "user"
            assert update.relationship.subject.object.object_id == str(visible_user)
    finally:
        engine.dispose()
