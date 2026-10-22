"""Exercise the request-to-authorization, command, and session boundaries."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.requests import Request
from starlette.responses import Response

from app.api import chat, grades, news, schedule, stats, users
from app.api.deps.auth import get_current_user_from_dishka, get_permission_checker
from app.auth.rbac import SpiceDBUnavailableError
from app.cqrs.commands.schedule import DeleteScheduleHandler
from app.cqrs.queries import GetStatsHandler
from app.deps.cache import NullCache
from app.models.enums import UserRole
from app.schemas import schemas
from app.services.news_service import NewsService
from app.services.user.analytics_service import UserAnalyticsService
from tests.conftest import call_injected

# Keep the real decorated handlers even when closure suites reload modules.
_delete_schedule = schedule.delete_schedule
_update_schedule = schedule.update_schedule


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "DELETE",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.mark.parametrize(
    "role,owner,missing,status",
    [
        (UserRole.ADMIN, False, False, 200),
        (UserRole.TEACHER, True, False, 200),
        (UserRole.TEACHER, False, False, 403),
        (UserRole.ADMIN, False, True, 404),
    ],
)
async def test_schedule_delete_preserves_actor_to_actual_handler(
    role, owner, missing, status
):
    actor = SimpleNamespace(id=uuid.uuid4(), role=role)
    record = SimpleNamespace(
        creator_id=actor.id if owner else uuid.uuid4(), group_id=uuid.uuid4()
    )
    service = SimpleNamespace(
        get_by_id=AsyncMock(return_value=None if missing else record),
        delete_schedule=AsyncMock(return_value=True),
    )
    cache = AsyncMock()
    handler = DeleteScheduleHandler(service, cache)
    bus = SimpleNamespace(execute=handler.handle)
    if status == 200:
        assert await call_injected(
            _delete_schedule,
            id=uuid.uuid4(),
            request=request(),
            user=actor,
            checker=SimpleNamespace(check_admin=AsyncMock(return_value=True)),
            provides={"CommandBus": bus},
        ) == {"ok": True}
        service.delete_schedule.assert_awaited_once()
        cache.invalidate.assert_awaited_once_with(f"schedule:group:{record.group_id}")
    else:
        with pytest.raises(HTTPException) as exc:
            await call_injected(
                _delete_schedule,
                id=uuid.uuid4(),
                request=request(),
                user=actor,
                checker=SimpleNamespace(check_admin=AsyncMock(return_value=True)),
                provides={"CommandBus": bus},
            )
        assert exc.value.status_code == status
        service.delete_schedule.assert_not_awaited()


async def test_summary_uses_one_real_async_session_sequentially():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with AsyncSession(engine) as session:

            async def compute(**kwargs):
                result = await session.execute(text("SELECT 1"))
                return {"value": result.scalar_one()}

            analytics = SimpleNamespace(
                get_attendance_stats=compute,
                get_grade_stats=compute,
                get_participation_stats=compute,
            )
            handler = GetStatsHandler(session, NullCache(), analytics)
            result = await call_injected(
                stats.stats_summary,
                request=request(),
                response=Response(),
                provides={"GetStatsHandler": handler},
                period="30d",
                skip_cache=True,
                if_none_match=None,
                user=SimpleNamespace(id=uuid.uuid4()),
            )
            assert {key: value["value"] for key, value in result.items()} == {
                "attendance": 1,
                "grades": 1,
                "participation": 1,
            }
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "router,method,path",
    [
        (users.users_router, "POST", "/users"),
        (chat.router, "POST", f"/chats/{uuid.UUID(int=1)}/clear"),
        (chat.router, "DELETE", f"/chats/{uuid.UUID(int=1)}"),
    ],
)
@pytest.mark.parametrize("unavailable,status", [(False, 403), (True, 503)])
async def test_admin_routes_reject_revoked_local_admin_before_mutation(
    router, method, path, unavailable, status
):
    app = FastAPI()
    app.include_router(router)
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    checker = SimpleNamespace(
        check_admin=AsyncMock(
            side_effect=SpiceDBUnavailableError("offline") if unavailable else None,
            return_value=False,
        )
    )
    app.dependency_overrides[get_current_user_from_dishka] = lambda: actor
    app.dependency_overrides[get_permission_checker] = lambda: checker
    # The real authorization dependency remains; independent rate limiting is outside this test.
    for route in app.routes:
        if hasattr(route, "dependant"):
            for dependency in route.dependant.dependencies:
                if dependency.name is None:
                    app.dependency_overrides[dependency.call] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json={})
    assert response.status_code == status, response.text
    checker.check_admin.assert_awaited_once_with(str(actor.id), user=actor)


@pytest.mark.parametrize(
    "owner,allowed,unavailable,status",
    [
        (False, False, False, 403),
        (False, False, True, 503),
        (False, True, False, 200),
        (True, False, True, 200),
    ],
)
async def test_news_comment_ownership_or_authoritative_admin(
    owner, allowed, unavailable, status
):
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    comment = SimpleNamespace(user_id=actor.id if owner else uuid.uuid4())
    repo = SimpleNamespace(
        get_comment=AsyncMock(return_value=comment), delete_comment=AsyncMock()
    )
    uow = AsyncMock()
    uow.news = repo
    service = NewsService(uow, AsyncMock())
    checker = SimpleNamespace(
        check_admin=AsyncMock(
            return_value=allowed,
            side_effect=SpiceDBUnavailableError("offline") if unavailable else None,
        )
    )
    args = dict(
        comment_id=uuid.uuid4(),
        request=request(),
        user=actor,
        checker=checker,
        provides={"NewsService": service},
    )
    endpoint = inspect.unwrap(news.delete_comment)
    if status == 200:
        assert await call_injected(endpoint, **args) == {"ok": True}
        repo.delete_comment.assert_awaited_once_with(comment)
    else:
        with pytest.raises(HTTPException) as exc:
            await call_injected(endpoint, **args)
        assert exc.value.status_code == status
        repo.delete_comment.assert_not_awaited()
    if owner:
        checker.check_admin.assert_not_awaited()


@pytest.mark.parametrize("unavailable,status", [(False, 403), (True, 503)])
async def test_grade_ownership_override_checks_spicedb(unavailable, status):
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    service = SimpleNamespace(
        get_grade=AsyncMock(return_value=SimpleNamespace(assigned_by=uuid.uuid4())),
        modify_grade=AsyncMock(),
    )
    checker = SimpleNamespace(
        check_admin=AsyncMock(
            return_value=False,
            side_effect=SpiceDBUnavailableError("offline") if unavailable else None,
        )
    )
    with pytest.raises(HTTPException) as exc:
        await call_injected(
            grades.modify_grade,
            grade_id=uuid.uuid4(),
            data=schemas.GradeUpdate(score=4),
            request=request(),
            user=actor,
            checker=checker,
            provides={"GradeService": service, "AsyncDatabaseSession": AsyncMock()},
        )
    assert exc.value.status_code == status
    service.modify_grade.assert_not_awaited()


async def test_summary_real_analytics_and_database(db_session):
    # A new engine forces the same cold-connection provisioning that races under
    # gather; production analytics/repository queries execute against real tables.
    engine = create_async_engine(db_session.bind.url)
    try:
        async with AsyncSession(engine) as session:
            handler = GetStatsHandler(
                session, NullCache(), UserAnalyticsService(session)
            )
            response = Response()
            result = await call_injected(
                stats.stats_summary,
                request=request(),
                response=response,
                provides={"GetStatsHandler": handler},
                period="30d",
                skip_cache=True,
                if_none_match=None,
                user=SimpleNamespace(id=uuid.uuid4()),
            )
            assert result["attendance"]["total"] == 0
            assert result["grades"]["total_grades"] == 0
            assert result["participation"]["events"] == 0
            assert response.headers["ETag"]
    finally:
        await engine.dispose()


@pytest.mark.parametrize("endpoint", [_delete_schedule, _update_schedule])
@pytest.mark.parametrize("unavailable,status", [(False, 403), (True, 503)])
async def test_schedule_admin_exception_is_authoritative(endpoint, unavailable, status):
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    checker = SimpleNamespace(
        check_admin=AsyncMock(
            return_value=False,
            side_effect=SpiceDBUnavailableError("offline") if unavailable else None,
        )
    )
    bus = SimpleNamespace(execute=AsyncMock())
    kwargs = (
        {"data": schemas.ScheduleUpdate(subject="Updated")}
        if endpoint is _update_schedule
        else {}
    )
    with pytest.raises(HTTPException) as exc:
        await call_injected(
            endpoint,
            id=uuid.uuid4(),
            request=request(),
            user=actor,
            checker=checker,
            provides={"CommandBus": bus},
            **kwargs,
        )
    assert exc.value.status_code == status
    bus.execute.assert_not_awaited()
