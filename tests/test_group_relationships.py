"""Group participant SpiceDB writes: writer, sync, user call sites and backfill."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc.aio
import pytest
from authzed.api.v1 import RelationshipUpdate

from app.auth import relationships
from app.auth.relationships import (
    GROUP_PARTICIPANT_RELATION,
    EventRelationshipWriter,
    RelationshipWriteError,
    build_group_participant_update,
    sync_group_participant,
)
from app.services.user.profile_service import UserProfileService
from scripts import backfill_group_participants as group_backfill


def _stub_with(write_mock: AsyncMock) -> MagicMock:
    stub = MagicMock()
    stub.WriteRelationships = write_mock
    return stub


def _written_updates(write_mock: AsyncMock) -> list[RelationshipUpdate]:
    return [
        update for call in write_mock.await_args_list for update in call.args[0].updates
    ]


def _assert_group_update(
    update: RelationshipUpdate, *, operation, group_id, user_id
) -> None:
    assert update.operation == operation
    relationship = update.relationship
    assert relationship.resource.object_type == "group"
    assert relationship.resource.object_id == str(group_id)
    assert relationship.relation == GROUP_PARTICIPANT_RELATION
    assert relationship.subject.object.object_type == "user"
    assert relationship.subject.object.object_id == str(user_id)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("touch_group_participant", RelationshipUpdate.OPERATION_TOUCH),
        ("delete_group_participant", RelationshipUpdate.OPERATION_DELETE),
    ],
)
async def test_group_participant_writer_maps_operation(method, operation):
    group_id, user_id = uuid4(), uuid4()
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        await getattr(EventRelationshipWriter(MagicMock()), method)(group_id, user_id)

    (update,) = _written_updates(write)
    _assert_group_update(
        update, operation=operation, group_id=group_id, user_id=user_id
    )


@pytest.mark.asyncio
async def test_group_participant_write_failure_raises_typed_error():
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
        await EventRelationshipWriter(MagicMock()).touch_group_participant(
            uuid4(), uuid4()
        )


def test_build_group_participant_update_rejects_unknown_operation():
    with pytest.raises(ValueError, match="operation"):
        build_group_participant_update(operation="upsert", group_id=1, user_id=2)


def test_build_group_participant_update_accepts_legacy_integer_ids():
    update = build_group_participant_update(operation="touch", group_id=7, user_id=9)
    _assert_group_update(
        update, operation=RelationshipUpdate.OPERATION_TOUCH, group_id=7, user_id=9
    )


# ---------------------------------------------------------------------------
# sync_group_participant semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_group_participant_noop_when_unchanged(
    mock_spicedb_relationship_writes,
):
    group_id = uuid4()
    await sync_group_participant(uuid4(), group_id, group_id)
    await sync_group_participant(uuid4(), None, None)
    mock_spicedb_relationship_writes.WriteRelationships.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_group_participant_touches_new_group_when_joining(
    mock_spicedb_relationship_writes,
):
    user_id, new_group = uuid4(), uuid4()
    await sync_group_participant(user_id, None, new_group)

    (update,) = _written_updates(mock_spicedb_relationship_writes.WriteRelationships)
    _assert_group_update(
        update,
        operation=RelationshipUpdate.OPERATION_TOUCH,
        group_id=new_group,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_sync_group_participant_deletes_old_group_when_leaving(
    mock_spicedb_relationship_writes,
):
    user_id, old_group = uuid4(), uuid4()
    await sync_group_participant(user_id, old_group, None)

    (update,) = _written_updates(mock_spicedb_relationship_writes.WriteRelationships)
    _assert_group_update(
        update,
        operation=RelationshipUpdate.OPERATION_DELETE,
        group_id=old_group,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_sync_group_participant_moves_membership_in_one_request(
    mock_spicedb_relationship_writes,
):
    user_id, old_group, new_group = uuid4(), uuid4(), uuid4()
    await sync_group_participant(user_id, old_group, new_group)

    write = mock_spicedb_relationship_writes.WriteRelationships
    write.assert_awaited_once()
    delete, touch = _written_updates(write)
    _assert_group_update(
        delete,
        operation=RelationshipUpdate.OPERATION_DELETE,
        group_id=old_group,
        user_id=user_id,
    )
    _assert_group_update(
        touch,
        operation=RelationshipUpdate.OPERATION_TOUCH,
        group_id=new_group,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_sync_group_participant_is_best_effort_and_logs_warning(
    mock_spicedb_relationship_writes,
):
    mock_spicedb_relationship_writes.WriteRelationships.side_effect = (
        RelationshipWriteError("down")
    )
    user_id, new_group = uuid4(), uuid4()
    with patch.object(relationships.logger, "warning") as warning:
        # Must not raise: the user commit has already succeeded.
        await sync_group_participant(user_id, None, new_group)

    warning.assert_called_once()
    assert warning.call_args.args[0] == "group_participant_relationship_sync_failed"
    assert warning.call_args.kwargs["user_id"] == str(user_id)
    assert warning.call_args.kwargs["new_group_id"] == str(new_group)


# ---------------------------------------------------------------------------
# Call sites: user services sync after commit and swallow write failures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_service() -> UserProfileService:
    repo = MagicMock()
    repo.db = AsyncMock()
    repo.get_orm_for_update_with_relations = AsyncMock()

    uow = MagicMock()
    uow.users = repo
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    return UserProfileService(uow, MagicMock(), AsyncMock())


def _admin_update_fixture(profile_service, *, old_group, new_group):
    target_id = uuid4()
    db_user = MagicMock()
    db_user.group_id = old_group
    profile_service.repo.get_orm_for_update_with_relations.return_value = db_user
    profile_service.repo._to_dto.return_value = SimpleNamespace(id=target_id)
    data = MagicMock()
    data.model_dump.return_value = {"group_id": new_group}

    def apply(user, payload):
        user.group_id = payload["group_id"]

    return target_id, data, apply


@pytest.mark.asyncio
async def test_admin_update_user_syncs_group_after_commit(
    profile_service, mock_spicedb_relationship_writes, monkeypatch
):
    old_group, new_group = uuid4(), uuid4()
    target_id, data, apply = _admin_update_fixture(
        profile_service, old_group=old_group, new_group=new_group
    )
    order: list[str] = []
    profile_service.uow.commit.side_effect = lambda: order.append("commit")
    mock_spicedb_relationship_writes.WriteRelationships.side_effect = (
        lambda *_a, **_k: order.append("write")
    )
    monkeypatch.setattr(
        "app.services.user.profile_service.update_user_attributes", apply
    )

    await profile_service.admin_update_user(
        target_id, data, MagicMock(), SimpleNamespace(role="admin")
    )

    assert order == ["commit", "write"]
    delete, touch = _written_updates(
        mock_spicedb_relationship_writes.WriteRelationships
    )
    _assert_group_update(
        delete,
        operation=RelationshipUpdate.OPERATION_DELETE,
        group_id=old_group,
        user_id=target_id,
    )
    _assert_group_update(
        touch,
        operation=RelationshipUpdate.OPERATION_TOUCH,
        group_id=new_group,
        user_id=target_id,
    )


@pytest.mark.asyncio
async def test_admin_update_user_swallows_group_sync_failure(
    profile_service, mock_spicedb_relationship_writes, monkeypatch
):
    target_id, data, apply = _admin_update_fixture(
        profile_service, old_group=None, new_group=uuid4()
    )
    mock_spicedb_relationship_writes.WriteRelationships.side_effect = (
        RelationshipWriteError("down")
    )
    monkeypatch.setattr(
        "app.services.user.profile_service.update_user_attributes", apply
    )

    with patch.object(relationships.logger, "warning") as warning:
        result = await profile_service.admin_update_user(
            target_id, data, MagicMock(), SimpleNamespace(role="admin")
        )

    assert result.id == target_id
    warning.assert_called_once()
    assert warning.call_args.args[0] == "group_participant_relationship_sync_failed"


@pytest.mark.asyncio
async def test_admin_update_user_without_group_change_writes_nothing(
    profile_service, mock_spicedb_relationship_writes, monkeypatch
):
    group_id = uuid4()
    target_id, data, _apply = _admin_update_fixture(
        profile_service, old_group=group_id, new_group=group_id
    )
    monkeypatch.setattr(
        "app.services.user.profile_service.update_user_attributes", MagicMock()
    )

    await profile_service.admin_update_user(
        target_id, data, MagicMock(), SimpleNamespace(role="admin")
    )

    mock_spicedb_relationship_writes.WriteRelationships.assert_not_awaited()


# ---------------------------------------------------------------------------
# Backfill: group participants for the MVP tenant
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.statements: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_group_backfill_fetch_builds_touch_per_member(monkeypatch):
    user_a, user_b, group = uuid4(), uuid4(), uuid4()
    session = _FakeSession([(user_a, group), (user_b, group), (uuid4(), None)])
    monkeypatch.setattr(group_backfill, "async_session", lambda: session)

    page = await group_backfill._fetch_group_participant_page(None, 10)

    assert [row[0] for row in page] == [user_a, user_b]
    for user_id, updates in page:
        (update,) = updates
        _assert_group_update(
            update,
            operation=RelationshipUpdate.OPERATION_TOUCH,
            group_id=group,
            user_id=user_id,
        )
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_group_backfill_fetch_applies_keyset_cursor(monkeypatch):
    session = _FakeSession([])
    monkeypatch.setattr(group_backfill, "async_session", lambda: session)

    assert await group_backfill._fetch_group_participant_page(uuid4(), 5) == []
    assert "users.id >" in str(session.statements[0]).replace("\n", " ")


@pytest.mark.asyncio
async def test_group_backfill_writes_members_through_shared_pager(monkeypatch):
    members = [(uuid4(), uuid4()) for _ in range(3)]
    session = _FakeSession([(user, group) for user, group in members])
    monkeypatch.setattr(group_backfill, "async_session", lambda: session)
    write = AsyncMock(return_value=None)
    with patch.object(
        relationships, "PermissionsServiceStub", return_value=_stub_with(write)
    ):
        processed = await group_backfill.apply_pages(
            group_backfill._fetch_group_participant_page,
            EventRelationshipWriter(MagicMock()),
            batch_size=10,
        )

    assert processed == 3
    written = _written_updates(write)
    assert [u.relationship.subject.object.object_id for u in written] == [
        str(user) for user, _ in members
    ]


@pytest.mark.asyncio
async def test_run_group_backfill_requires_configured_mvp_tenant(monkeypatch):
    monkeypatch.setattr(group_backfill, "settings", SimpleNamespace(mvp_tenant_id=None))
    with pytest.raises(RuntimeError, match="MVP_TENANT_ID"):
        await group_backfill.run_group_backfill(batch_size=10)


@pytest.mark.asyncio
async def test_run_group_backfill_restores_tenant_context(monkeypatch):
    from app.core.tenant import get_current_tenant

    tenant = uuid4()
    monkeypatch.setattr(
        group_backfill, "settings", SimpleNamespace(mvp_tenant_id=tenant)
    )
    monkeypatch.setattr(group_backfill, "init_database", lambda: None)
    seen_tenants: list[str] = []

    class _Session:
        async def __aenter__(self):
            seen_tenants.append(get_current_tenant())
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(group_backfill, "async_session", lambda: _Session())
    monkeypatch.setattr(
        group_backfill, "require_mvp_tenant", AsyncMock(return_value=tenant)
    )
    monkeypatch.setattr(
        group_backfill,
        "acquire_shared_spicedb_channel",
        AsyncMock(return_value=MagicMock()),
    )
    apply = AsyncMock(return_value=4)
    monkeypatch.setattr(group_backfill, "apply_pages", apply)
    close = AsyncMock(return_value=None)
    monkeypatch.setattr(group_backfill, "close_global_spicedb_channel", close)

    assert await group_backfill.run_group_backfill(batch_size=10) == 4
    assert seen_tenants == [str(tenant)]
    assert get_current_tenant() == ""
    assert apply.await_args.kwargs == {"batch_size": 10}
    close.assert_awaited_once()


def test_group_backfill_main_prints_count(monkeypatch, capsys):
    monkeypatch.setattr(group_backfill, "run_group_backfill", AsyncMock(return_value=6))
    monkeypatch.setattr("sys.argv", ["backfill_group_participants"])
    group_backfill.main()
    assert "group participant relations: 6" in capsys.readouterr().out
