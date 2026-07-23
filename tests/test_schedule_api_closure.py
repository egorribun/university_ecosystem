from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from starlette.responses import Response


def _install_import_stubs() -> None:
    import dishka.integrations.fastapi as dishka_fastapi

    dishka_fastapi.inject = lambda function: function

    deps = ModuleType("app.api.deps")
    deps.get_current_user = lambda: None
    deps.get_current_user_optional = lambda: None
    sys.modules.setdefault("app.api.deps", deps)

    bus = ModuleType("app.cqrs.bus")
    bus.CommandBus = object
    bus.QueryBus = object
    sys.modules.setdefault("app.cqrs.bus", bus)

    commands = ModuleType("app.cqrs.commands.schedule")

    @dataclass
    class CreateScheduleCommand:
        data: object
        locale: str
        actor_id: object

    @dataclass
    class UpdateScheduleCommand:
        schedule_id: object
        data: object
        actor_id: object
        actor_role: object

    @dataclass
    class DeleteScheduleCommand:
        schedule_id: object

    commands.CreateScheduleCommand = CreateScheduleCommand
    commands.UpdateScheduleCommand = UpdateScheduleCommand
    commands.DeleteScheduleCommand = DeleteScheduleCommand
    sys.modules.setdefault("app.cqrs.commands.schedule", commands)

    queries = ModuleType("app.cqrs.queries")

    @dataclass
    class GetScheduleQuery:
        group_id: object
        locale: str
        if_none_match: str | None

    queries.GetScheduleQuery = GetScheduleQuery
    sys.modules.setdefault("app.cqrs.queries", queries)


_install_import_stubs()

from app.api import schedule, validation
from app.core.exceptions.domain import BusinessRuleViolation
from app.models.enums import UserRole
from app.schemas import schemas


class _Request:
    query_params: ClassVar[dict[str, str]] = {}
    headers: ClassVar[dict[str, str]] = {}

    class _Client:
        host = "127.0.0.1"

    client = _Client()


def _user(role=UserRole.ADMIN):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _schedule_out():
    group_id = uuid.uuid4()
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        group_id=group_id,
        subject="Math",
        teacher="Teacher",
        room="101",
        weekday="monday",
        start_time=now,
        end_time=now,
        parity="both",
        lesson_type=None,
        lesson_type_display=None,
    )


def test_vary_helper_and_cache_headers(monkeypatch):
    main = ModuleType("app.main")
    main._ensure_vary_header = lambda response, value: response.headers.__setitem__(
        "Vary", value
    )
    monkeypatch.setitem(sys.modules, "app.main", main)
    schedule._get_vary_helper.cache_clear()
    helper = schedule._get_vary_helper()
    response = Response()
    helper(response, "Accept-Language")
    assert response.headers["Vary"] == "Accept-Language"

    schedule._set_schedule_cache_headers(response)
    assert response.headers["Cache-Control"] == "private, max-age=300"
    assert "Expires" in response.headers
    assert schedule._schedule_cache_key(uuid.UUID(int=1)).startswith("schedule:group:")


@pytest.mark.asyncio
async def test_add_schedule_success_and_domain_conflict(monkeypatch):
    monkeypatch.setattr(schedule, "resolve_locale", lambda **kwargs: "en")
    monkeypatch.setattr(schedule, "require_teacher_or_admin", lambda *args: None)
    data = schemas.ScheduleCreate(
        group_id=uuid.uuid4(),
        subject="Math",
        weekday="monday",
        start_time="2026-07-23T10:00:00Z",
        end_time="2026-07-23T11:00:00Z",
    )
    bus = SimpleNamespace(execute=AsyncMock(return_value=_schedule_out()))
    result = await schedule.add_schedule(data, _Request(), bus, _user())
    assert result.subject == "Math"

    conflict_bus = SimpleNamespace(
        execute=AsyncMock(side_effect=BusinessRuleViolation("conflict"))
    )
    monkeypatch.setattr(
        validation,
        "raise_conflict",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(status_code=409)),
    )
    with pytest.raises(HTTPException) as exc_info:
        await schedule.add_schedule(data, _Request(), conflict_bus, _user())
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_schedule_full_and_not_modified_responses(monkeypatch):
    monkeypatch.setattr(schedule, "resolve_locale", lambda **kwargs: "en")
    monkeypatch.setattr(
        schedule,
        "_get_vary_helper",
        lambda: lambda response, value: response.headers.__setitem__("Vary", value),
    )
    group_id = uuid.uuid4()
    response = Response()
    bus = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                not_modified=False, etag='"etag"', payload=[_schedule_out()]
            )
        )
    )
    result = await schedule.get_schedule(
        group_id, _Request(), response, bus, None, None
    )
    assert result and result[0].subject == "Math"
    assert response.headers["ETag"] == '"etag"'
    assert response.headers["Content-Language"] == "en"

    no_etag_response = Response()
    no_etag_bus = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                not_modified=False,
                etag=None,
                payload=[],
            )
        )
    )
    assert (
        await schedule.get_schedule(
            group_id,
            _Request(),
            no_etag_response,
            no_etag_bus,
            None,
            None,
        )
        == []
    )
    assert "ETag" not in no_etag_response.headers

    cached_bus = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(not_modified=True, etag='"cached"', payload=[])
        )
    )
    cached = await schedule.get_schedule(
        group_id, _Request(), Response(), cached_bus, None, '"cached"'
    )
    assert isinstance(cached, Response)
    assert cached.status_code == status.HTTP_304_NOT_MODIFIED
    assert cached.headers["ETag"] == '"cached"'


@pytest.mark.asyncio
async def test_update_schedule_success_permission_and_missing(monkeypatch):
    monkeypatch.setattr(schedule, "resolve_locale", lambda **kwargs: "en")
    monkeypatch.setattr(schedule, "require_teacher_or_admin", lambda *args: None)
    monkeypatch.setattr(
        schedule,
        "raise_forbidden",
        lambda *args: (_ for _ in ()).throw(HTTPException(status_code=403)),
    )
    monkeypatch.setattr(
        schedule,
        "ensure_exists",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(status_code=404)),
    )
    data = schemas.ScheduleUpdate(subject="Updated")
    updated = _schedule_out()
    bus = SimpleNamespace(execute=AsyncMock(return_value=updated))
    result = await schedule.update_schedule(
        uuid.uuid4(), data, _Request(), bus, _user()
    )
    assert result.subject == "Math"

    permission_bus = SimpleNamespace(execute=AsyncMock(side_effect=PermissionError()))
    with pytest.raises(HTTPException) as exc_info:
        await schedule.update_schedule(
            uuid.uuid4(), data, _Request(), permission_bus, _user()
        )
    assert exc_info.value.status_code == 403

    missing_bus = SimpleNamespace(execute=AsyncMock(side_effect=ValueError()))
    with pytest.raises(HTTPException) as exc_info:
        await schedule.update_schedule(
            uuid.uuid4(), data, _Request(), missing_bus, _user()
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule_success_and_not_found(monkeypatch):
    monkeypatch.setattr(schedule, "resolve_locale", lambda **kwargs: "en")
    monkeypatch.setattr(schedule, "require_teacher_or_admin", lambda *args: None)
    monkeypatch.setattr(
        schedule,
        "ensure_exists",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(status_code=404)),
    )
    bus = SimpleNamespace(execute=AsyncMock(return_value=True))
    assert await schedule.delete_schedule(uuid.uuid4(), _Request(), bus, _user()) == {
        "ok": True
    }

    missing = SimpleNamespace(execute=AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as exc_info:
        await schedule.delete_schedule(uuid.uuid4(), _Request(), missing, _user())
    assert exc_info.value.status_code == 404
