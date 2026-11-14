"""Event-file reads must not trust an obsolete SpiceDB attendee projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from authzed.api import v1
from fastapi import HTTPException
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, delete
from sqlalchemy.exc import OperationalError

from app import models
from app.api import events as api
from app.auth import rbac, relationships
from app.repositories.event_repository import EventRepository
from tests.conftest import call_injected


@pytest.fixture
async def file_authorization_case(db_session, user_factory, monkeypatch):
    user = await user_factory()
    owner = await user_factory()
    starts = datetime.now(UTC) + timedelta(days=1)
    event = models.Event(
        title="Private event files",
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
        created_by=owner.id,
    )
    db_session.add(event)
    await db_session.flush()
    attendance = models.EventAttendance(
        event_id=event.id, user_id=user.id, qr_secret="test", qr_hmac="test"
    )
    attachment = models.EventFile(
        event_id=event.id,
        file_url=f"/static/event_files/event_{event.id}/agenda.pdf",
    )
    db_session.add_all([attendance, attachment])
    await db_session.commit()
    state = {
        "attendee": True,
        "other": False,
        "outage": False,
        "missing_alias": False,
        "failed_delete": False,
    }
    permissions = []

    async def check(request):
        permissions.append(request.permission)
        if state["outage"]:
            raise OSError("synthetic SpiceDB outage")
        if state["missing_alias"] and request.permission == "view_without_attendee":
            raise RuntimeError("synthetic unknown permission")
        allowed = state["other"] or (request.permission == "view" and state["attendee"])
        return v1.CheckPermissionResponse(
            permissionship=(
                v1.CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
                if allowed
                else v1.CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
            )
        )

    async def write(request):
        for update in request.updates:
            if update.operation == v1.RelationshipUpdate.OPERATION_DELETE:
                if state["failed_delete"]:
                    raise OSError("synthetic unconfirmed deletion")
                state["attendee"] = False
            else:
                state["attendee"] = True

    monkeypatch.setattr(
        v1, "PermissionsServiceStub", lambda _: SimpleNamespace(CheckPermission=check)
    )
    monkeypatch.setattr(
        relationships,
        "PermissionsServiceStub",
        lambda _: SimpleNamespace(WriteRelationships=write),
    )
    monkeypatch.setattr(
        relationships,
        "acquire_shared_spicedb_channel",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(rbac, "_permission_cache", rbac._make_fresh_cache())
    monkeypatch.setattr(
        rbac, "_spicedb_breaker", rbac.CircuitBreaker("event-file-authorization-test")
    )
    checker = rbac.PermissionChecker(object())
    reader = AsyncMock(wraps=EventRepository(db_session).get_event_files)
    monkeypatch.setattr(EventRepository, "get_event_files", reader)
    storage = SimpleNamespace(read_file=AsyncMock(return_value=b"private event bytes"))
    monkeypatch.setattr(api, "_get_storage_backend", lambda: storage)
    monkeypatch.setattr(api, "resolve_locale", lambda **_: "en")

    async def invoke(route, *, event_id=None, filename="agenda.pdf"):
        endpoint = api.get_event_files if route == "list" else api.download_event_file
        positional = [event.id if event_id is None else event_id]
        if route == "download":
            positional.append(filename)
        return await call_injected(
            endpoint,
            *positional,
            request=SimpleNamespace(),
            user=user,
            checker=checker,
            provides={"AsyncDatabaseSession": db_session},
        )

    async def revoke_sql():
        # Keep the loaded attendance object stale on purpose. Authorization must
        # execute SQL instead of trusting identity-map or relationship state.
        await db_session.execute(
            delete(models.EventAttendance)
            .where(models.EventAttendance.id == attendance.id)
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()

    return SimpleNamespace(
        db=db_session,
        user=user,
        event=event,
        attachment=attachment,
        state=state,
        permissions=permissions,
        reader=reader,
        storage=storage,
        invoke=invoke,
        revoke_sql=revoke_sql,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
@pytest.mark.parametrize(
    ("failure", "status_code"),
    [
        ("failed_delete", 403),
        ("stale_touch", 403),
        ("outage", 503),
        ("missing_alias", 503),
    ],
)
async def test_revoked_attendee_cannot_reuse_graph_or_old_view_cache(
    file_authorization_case, route, failure, status_code
):
    case = file_authorization_case
    await case.invoke(route)  # Warm the real PermissionChecker's ordinary view ALLOW.
    assert case.permissions == ["view"]
    await case.revoke_sql()
    if failure == "failed_delete":
        case.state["failed_delete"] = True
        await relationships.sync_event_attendee(
            case.event.id, case.user.id, attending=False
        )
    elif failure == "stale_touch":
        await relationships.sync_event_attendee(
            case.event.id, case.user.id, attending=False
        )
        await relationships.sync_event_attendee(
            case.event.id, case.user.id, attending=True
        )
    else:
        case.state[failure] = True
    assert case.state["attendee"] is True
    case.reader.reset_mock()
    case.storage.read_file.reset_mock()
    case.permissions.clear()

    with pytest.raises(HTTPException) as denied:
        await case.invoke(route)

    assert denied.value.status_code == status_code
    assert case.permissions == ["view_without_attendee"]
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
async def test_current_attendance_never_overrides_graph_denial(
    file_authorization_case, route
):
    case = file_authorization_case
    case.state["attendee"] = False
    with pytest.raises(HTTPException) as denied:
        await case.invoke(route)
    assert denied.value.status_code == 403
    assert case.permissions == ["view"]
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
async def test_nonmember_retains_independent_graph_grant(
    file_authorization_case, route
):
    case = file_authorization_case
    await case.revoke_sql()
    case.state.update(attendee=False, other=True)
    result = await case.invoke(route)
    if route == "list":
        assert [item.id for item in result] == [case.attachment.id]
    else:
        assert result.body == b"private event bytes"
    assert case.permissions == ["view_without_attendee"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
async def test_membership_database_failure_is_unavailable_before_file_access(
    file_authorization_case, monkeypatch, route
):
    case = file_authorization_case
    monkeypatch.setattr(
        case.db,
        "scalar",
        AsyncMock(
            side_effect=OperationalError("SELECT attendance", {}, OSError("down"))
        ),
    )
    with pytest.raises(HTTPException) as denied:
        await case.invoke(route)
    assert denied.value.status_code == 503
    assert denied.value.detail["error"] == "authz_unavailable"
    assert case.permissions == []
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
async def test_missing_parent_never_checks_membership_or_graph(
    file_authorization_case, monkeypatch, route
):
    case = file_authorization_case
    scalar = AsyncMock(
        side_effect=AssertionError("Membership read before parent existence")
    )
    monkeypatch.setattr(case.db, "scalar", scalar)
    with pytest.raises(HTTPException) as denied:
        await case.invoke(route, event_id=uuid4())
    assert denied.value.status_code == 404
    scalar.assert_not_awaited()
    assert case.permissions == []
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_download_path_precedes_membership_read(
    file_authorization_case, monkeypatch
):
    case = file_authorization_case
    scalar = AsyncMock(
        side_effect=AssertionError("Membership read before path validation")
    )
    monkeypatch.setattr(case.db, "scalar", scalar)
    with pytest.raises(HTTPException) as denied:
        await case.invoke("download", filename="../secret.pdf")
    assert denied.value.status_code == 404
    scalar.assert_not_awaited()
    assert case.permissions == []
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("visible_event", [False, True])
@pytest.mark.parametrize("visible_user", [False, True])
async def test_membership_scalar_requires_both_tenant_visible_parents(
    visible_event, visible_user
):
    """Execute real SQL against visible row sets, not a PostgreSQL RLS proof."""
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
    event_id, user_id = uuid4(), uuid4()
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            if visible_event:
                connection.execute(events.insert(), [{"id": event_id}])
            if visible_user:
                connection.execute(users.insert(), [{"id": user_id}])
            connection.execute(
                attendance.insert(),
                [
                    {
                        "id": uuid4(),
                        "event_id": event_id,
                        "user_id": user_id,
                    }
                ],
            )

            async def scalar(statement):
                return connection.scalar(statement)

            repository = EventRepository(SimpleNamespace(scalar=scalar))
            assert await repository.has_current_attendance(event_id, user_id) is (
                visible_event and visible_user
            )
            assert await repository.has_current_attendance(uuid4(), user_id) is False
            assert await repository.has_current_attendance(event_id, uuid4()) is False
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["list", "download"])
@pytest.mark.parametrize("failure", ["outage", "missing_alias"])
async def test_independent_grant_cache_retains_only_existing_bounded_grace(
    file_authorization_case, monkeypatch, route, failure
):
    case = file_authorization_case
    now = [100.0]
    monkeypatch.setattr(rbac, "time", SimpleNamespace(monotonic=lambda: now[0]))
    await case.revoke_sql()
    case.state.update(attendee=False, other=True)
    await case.invoke(route)
    assert case.permissions == ["view_without_attendee"]

    # This existing grace is for a genuine independent grant, not attendance.
    # Schema rollback must not be documented as immediate denial of that cache.
    case.state.update(other=False)
    case.state[failure] = True
    await case.invoke(route)
    now[0] += rbac._PERMISSION_POSITIVE_TTL_SECONDS + 1
    case.reader.reset_mock()
    case.storage.read_file.reset_mock()

    with pytest.raises(HTTPException) as denied:
        await case.invoke(route)

    assert denied.value.status_code == 503
    assert case.permissions == ["view_without_attendee"] * 3
    case.reader.assert_not_awaited()
    case.storage.read_file.assert_not_awaited()
