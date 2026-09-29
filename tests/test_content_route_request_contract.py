"""Required HTTP requests and optional application caches are distinct contracts."""

from __future__ import annotations

import ast
import inspect
import uuid
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI, Request

from app.api import events, news
from app.core.cache_versioning import CacheVersionManager
from app.deps.cache import NullCache
from app.models.enums import UserRole
from app.schemas import schemas
from tests.conftest import call_injected

_HANDLERS = (
    news.create_news,
    news.update_news,
    news.delete_news,
    events.update_event,
    events.delete_event,
)


@pytest.mark.parametrize("handler", _HANDLERS, ids=lambda handler: handler.__name__)
def test_mutations_treat_the_container_bearing_request_as_required(handler) -> None:
    """Do not restore pre-Dishka optional-request control flow in HTTP routes."""
    original = inspect.unwrap(handler)
    parameter = inspect.signature(original).parameters["request"]
    assert parameter.default is inspect.Parameter.empty
    assert get_type_hints(original)["request"] is Request
    module = news if handler.__module__ == news.__name__ else events
    function = next(
        node
        for node in ast.parse(inspect.getsource(module)).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == handler.__name__
    )
    request_guards = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "request"
    ]
    assert not request_guards, (
        "Request is required by FastAPI and carries the Dishka container; "
        "only the cache may be absent"
    )


@pytest.mark.parametrize("handler", _HANDLERS, ids=lambda handler: handler.__name__)
@pytest.mark.parametrize("cache_state", ["present", "none", "missing"])
async def test_mutations_keep_localization_and_optional_cache_contract(
    handler, cache_state: str
) -> None:
    app = FastAPI()
    cache = object()
    if cache_state != "missing":
        app.state.cache = cache if cache_state == "present" else None
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "POST",
            "path": "/",
            "headers": [(b"accept-language", b"ru")],
            "query_string": b"",
        }
    )
    record = SimpleNamespace(id=uuid.UUID(int=17), image_url=None)
    user = SimpleNamespace(id=uuid.UUID(int=19), role=UserRole.ADMIN)
    service = MagicMock()
    notifications = AsyncMock()
    background = BackgroundTasks()
    kwargs = {"request": request, "user": user}
    module = news if handler.__module__ == news.__name__ else events
    if module is news:
        service.serialize_news.return_value = {"id": record.id}
        kwargs["provides"] = {"NewsService": service}
        if handler is news.create_news:
            data = schemas.NewsCreate(title="Title", content="Content")
            service.create_news = AsyncMock(return_value=record)
            kwargs.update(data=data, background=background)
            kwargs["provides"]["NotificationService"] = notifications
        else:
            kwargs["id"] = record.id
            if handler is news.update_news:
                data = schemas.NewsUpdate(title="Updated")
                kwargs["data"] = data
                service.update_news = AsyncMock(return_value=record)
            else:
                service.delete_news = AsyncMock(return_value=True)
    else:
        checker = SimpleNamespace(check_permission=AsyncMock(return_value=True))
        kwargs.update(event_id=record.id, checker=checker)
        kwargs["provides"] = {"EventService": service}
        if handler is events.update_event:
            data = schemas.EventUpdate(title="Updated")
            kwargs["data"] = data
            service.update_event = AsyncMock(return_value=record)
            service.serialize_event.return_value = {"id": record.id}
            db = AsyncMock()
            db.get.return_value = record
            files = MagicMock()
            files.scalars.return_value.all.return_value = []
            count = MagicMock()
            count.scalar.return_value = 2
            db.execute.side_effect = [files, count]
            kwargs["provides"]["AsyncDatabaseSession"] = db
        else:
            service.get_event_by_id = AsyncMock(return_value=record)
            service.delete_event = AsyncMock()

    # Keep the real route, locale resolver, and optional-cache helper. Only the
    # external version write and secondary item cache are isolated.
    with (
        patch.object(CacheVersionManager, "increment", new_callable=AsyncMock) as bump,
        patch.object(module, "get_cache", return_value=NullCache()),
    ):
        result = await call_injected(handler, **kwargs)

    if cache_state == "present":
        bump.assert_awaited_once_with(cache)
    else:
        bump.assert_not_awaited()
    if handler in (news.delete_news, events.delete_event):
        assert result == {"ok": True}
        getattr(service, handler.__name__).assert_awaited_once_with(record.id)
    else:
        assert result == {"id": record.id}
        serialize = (
            service.serialize_news if module is news else service.serialize_event
        )
        assert serialize.call_args.args == (record, "ru")
        if handler is news.create_news:
            service.create_news.assert_awaited_once_with(data)
            notifications.dispatch_news_created.assert_awaited_once_with(
                record.id, "ru", background
            )
        else:
            getattr(service, handler.__name__).assert_awaited_once_with(record.id, data)
        if handler is events.update_event:
            assert serialize.call_args.kwargs == {"participant_count": 2, "files": []}
    if module is events:
        checker.check_permission.assert_awaited_once_with(
            resource_type="event",
            resource_id=str(record.id),
            permission="edit" if handler is events.update_event else "delete",
            user_id=str(user.id),
        )
