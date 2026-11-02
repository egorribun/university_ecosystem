"""Current-baseline PostgreSQL DND schema and production wall-clock writes."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import time

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import UserPreferences
from app.repositories.unit_of_work import uow_from_session
from app.schemas.users import UserProfileUpdate
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.notifications.quiet_hours import is_user_in_quiet_hours
from app.services.user.profile_service import UserProfileService
from tests.fixtures import owned_baseline_postgres as owned
from tests.fixtures.auth import auth_fixtures

user_factory = auth_fixtures.user_factory
initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="signal", func_only=False),
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest_asyncio.fixture
async def dnd_engine(request: pytest.FixtureRequest) -> AsyncIterator[AsyncEngine]:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "DND tests require --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        engine = create_async_engine(
            baseline.url.set(drivername="postgresql+asyncpg", query={}),
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 65,
                "server_settings": {
                    "lock_timeout": "10s",
                    "statement_timeout": "60s",
                    "idle_in_transaction_session_timeout": "60s",
                },
            },
        )
        try:
            yield engine
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def db_session(dnd_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(dnd_engine, expire_on_commit=False)() as session:
        yield session


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": "/api/v1/users/me",
            "raw_path": b"/api/v1/users/me",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 43120),
        }
    )


@pytest.mark.asyncio
async def test_profile_update_commits_local_dnd_times_with_asyncpg(
    db_session,
    user_factory,
    dnd_engine,
) -> None:
    """Exercise the production profile service and real PostgreSQL TIME codec."""
    assert dnd_engine.dialect.name == "postgresql"
    assert dnd_engine.dialect.driver == "asyncpg"
    assert UserPreferences.__table__.c.dnd_start.type.timezone is False
    assert UserPreferences.__table__.c.dnd_end.type.timezone is False

    user = await user_factory()
    assert await db_session.get(UserPreferences, user.id) is None

    service = UserProfileService(
        uow_from_session(db_session),
        AuditService(),
        NotificationService(db_session),
    )
    payload = UserProfileUpdate(
        timezone="Europe/Istanbul",
        dnd_enabled=True,
        dnd_start=time(0),
        dnd_end=time(0),
    )

    updated = await service.update_user_profile(user.id, payload, _request())

    assert updated.preferences is not None
    assert updated.preferences.timezone == "Europe/Istanbul"
    assert updated.preferences.dnd_start == time(0)
    assert updated.preferences.dnd_end == time(0)
    assert is_user_in_quiet_hours(updated, now_time=time(12))

    async with async_sessionmaker(dnd_engine)() as verification_session:
        stored = await verification_session.get(UserPreferences, user.id)
        assert stored is not None
        assert stored.dnd_enabled is True
        assert stored.timezone == "Europe/Istanbul"
        assert stored.dnd_start == time(0)
        assert stored.dnd_end == time(0)
        assert stored.dnd_start.tzinfo is None
        assert stored.dnd_end.tzinfo is None


@pytest.mark.asyncio
async def test_baseline_dnd_columns_are_nullable_local_time(
    dnd_engine: AsyncEngine,
) -> None:
    async with dnd_engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'user_preferences' "
                    "AND column_name IN ('dnd_start', 'dnd_end') ORDER BY column_name"
                )
            )
        ).all()
        assert [tuple(row) for row in rows] == [
            ("dnd_end", "time without time zone", "YES"),
            ("dnd_start", "time without time zone", "YES"),
        ]
