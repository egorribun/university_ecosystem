"""PostgreSQL proof for Dishka request-scoped database-session ownership."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
from dishka.integrations.fastapi import FromDishka, inject, setup_dishka
from fastapi import Depends, FastAPI, Request
from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_session

from app.api.deps import auth as auth_deps
from app.core import database
from app.core.di_provider import create_dishka_container
from app.core.protocols import AsyncDatabaseSession
from app.models.domain_events import StoredEvent
from app.models.users import User
from app.services.auth.redis_session import RedisSessionService
from tests.fixtures.auth.auth_fixtures import create_access_token

_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN_INTEGRATION_TESTS and _DATABASE_URL.startswith("postgresql")),
        reason=(
            "Requires RUN_INTEGRATION_TESTS=1 and a PostgreSQL DATABASE_URL; "
            "the request-session ownership proof must not silently use SQLite"
        ),
    ),
]


@dataclass
class _PoolLifecycle:
    """Count real SQLAlchemy pool and transaction events during one request."""

    checkouts: int = 0
    checkins: int = 0
    begins: int = 0
    commits: int = 0
    rollbacks: int = 0
    _listeners: list[tuple[Engine, str, Callable[..., None]]] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def attach(self, engine: Engine) -> None:
        for event_name in ("checkouts", "checkins", "begins", "commits", "rollbacks"):
            sqlalchemy_event = {
                "checkouts": "checkout",
                "checkins": "checkin",
                "begins": "begin",
                "commits": "commit",
                "rollbacks": "rollback",
            }[event_name]

            def record(*_args: object, counter: str = event_name) -> None:
                setattr(self, counter, getattr(self, counter) + 1)

            event.listen(engine, sqlalchemy_event, record)
            self._listeners.append((engine, sqlalchemy_event, record))

    def reset(self) -> None:
        self.checkouts = 0
        self.checkins = 0
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0

    def snapshot(self) -> tuple[int, int, int, int, int]:
        return (
            self.checkouts,
            self.checkins,
            self.begins,
            self.commits,
            self.rollbacks,
        )

    def detach(self) -> None:
        for engine, event_name, listener in self._listeners:
            event.remove(engine, event_name, listener)
        self._listeners.clear()


def _probe_event(event_id: UUID, request_kind: str) -> StoredEvent:
    return StoredEvent(
        id=event_id,
        event_type="be04.request_session_ownership",
        aggregate_type="request_session_ownership",
        aggregate_id=str(event_id),
        payload={"request_kind": request_kind},
    )


@pytest.mark.asyncio
async def test_postgres_dishka_request_session_identity_and_lifecycle(
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real auth and handler work share one PG session and one cleanup owner."""

    assert database.engine.dialect.name == "postgresql"

    user = await user_factory()
    token, _active_session = await create_access_token(str(user.id), db_session)
    success_event_id = uuid4()
    failure_event_id = uuid4()

    auth_sessions: dict[str, list[AsyncDatabaseSession]] = defaultdict(list)
    handler_sessions: dict[str, list[AsyncDatabaseSession]] = defaultdict(list)
    handler_user_attachment: dict[str, list[bool]] = defaultdict(list)
    failure_flushes: list[str] = []

    resolve_current_user = auth_deps._resolve_current_user

    async def observe_auth_session(
        request: Request,
        token_value: str | None,
        db: AsyncDatabaseSession,
        redis_service: RedisSessionService | None = None,
    ) -> User:
        auth_sessions[request.url.path].append(db)
        return await resolve_current_user(request, token_value, db, redis_service)

    monkeypatch.setattr(auth_deps, "_resolve_current_user", observe_auth_session)

    probe_app = FastAPI()

    @probe_app.post("/success")
    @inject
    async def successful_request(
        request: Request,
        current_user: Annotated[User, Depends(auth_deps.get_current_user_from_dishka)],
        db: FromDishka[AsyncDatabaseSession],
    ) -> dict[str, int | bool]:
        handler_sessions[request.url.path].append(db)
        same_orm_session = object_session(current_user) is db.sync_session
        handler_user_attachment[request.url.path].append(same_orm_session)
        backend_pid = await db.scalar(text("SELECT pg_backend_pid()"))
        assert backend_pid is not None
        db.add(_probe_event(success_event_id, "commit"))
        await db.flush()
        await db.commit()
        return {
            "auth_session_id": id(auth_sessions[request.url.path][-1]),
            "handler_session_id": id(db),
            "user_attached_to_handler_session": same_orm_session,
            "backend_pid": int(backend_pid),
        }

    @probe_app.post("/failure")
    @inject
    async def failed_request(
        request: Request,
        current_user: Annotated[User, Depends(auth_deps.get_current_user_from_dishka)],
        db: FromDishka[AsyncDatabaseSession],
    ) -> None:
        handler_sessions[request.url.path].append(db)
        handler_user_attachment[request.url.path].append(
            object_session(current_user) is db.sync_session
        )
        db.add(_probe_event(failure_event_id, "rollback"))
        await db.flush()
        failure_flushes.append(request.url.path)
        raise RuntimeError("simulated handler failure after database write")

    container = create_dishka_container()
    setup_dishka(container, probe_app)

    close_calls: Counter[int] = Counter()
    original_close = AsyncSession.close

    async def count_close(session: AsyncSession) -> None:
        close_calls[id(session)] += 1
        await original_close(session)

    monkeypatch.setattr(AsyncSession, "close", count_close)

    lifecycle = _PoolLifecycle()
    lifecycle.attach(database.engine.sync_engine)
    transport = httpx.ASGITransport(app=probe_app, raise_app_exceptions=False)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest"},
        ) as client:
            lifecycle.reset()
            success_response = await client.post("/success")
            success_counts = lifecycle.snapshot()

            assert success_response.status_code == 200, success_response.text
            success_body = success_response.json()
            success_auth_session = auth_sessions["/success"][0]
            success_handler_session = handler_sessions["/success"][0]
            assert success_auth_session is success_handler_session
            assert success_body["auth_session_id"] == success_body["handler_session_id"]
            assert success_body["user_attached_to_handler_session"] is True
            assert success_body["backend_pid"] > 0
            assert close_calls[id(success_handler_session)] == 1
            assert success_counts == (1, 1, 1, 1, 0)

            lifecycle.reset()
            failure_response = await client.post("/failure")
            failure_counts = lifecycle.snapshot()

            assert failure_response.status_code == 500
            assert failure_flushes == ["/failure"]
            failure_auth_session = auth_sessions["/failure"][0]
            failure_handler_session = handler_sessions["/failure"][0]
            assert failure_auth_session is failure_handler_session
            assert handler_user_attachment["/failure"] == [True]
            assert close_calls[id(failure_handler_session)] == 1
            assert failure_counts == (1, 1, 1, 0, 1)
    finally:
        lifecycle.detach()
        await container.close()

    committed_id = await db_session.scalar(
        select(StoredEvent.id).where(StoredEvent.id == success_event_id)
    )
    rolled_back_id = await db_session.scalar(
        select(StoredEvent.id).where(StoredEvent.id == failure_event_id)
    )
    assert committed_id == success_event_id
    assert rolled_back_id is None
    await db_session.rollback()
