"""PostgreSQL proof for DND wall-clock writes and the forward migration."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import time
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request

from app.core import database
from app.models import UserPreferences
from app.repositories.unit_of_work import uow_from_session
from app.schemas.users import UserProfileUpdate
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.notifications.quiet_hours import is_user_in_quiet_hours
from app.services.user.profile_service import UserProfileService

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN and _DATABASE_URL.startswith("postgresql")),
        reason=(
            "Requires RUN_INTEGRATION_TESTS=1 and a PostgreSQL DATABASE_URL; "
            "SQLite cannot prove asyncpg time codec or PostgreSQL migration behavior"
        ),
    ),
]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _PROJECT_ROOT / "alembic" / "versions" / "202610120001_dnd_wall_clock_time.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "dnd_wall_clock_time_migration", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
) -> None:
    """Exercise the production profile service and real PostgreSQL TIME codec."""
    assert database.engine.dialect.name == "postgresql"
    assert database.engine.dialect.driver == "asyncpg"
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

    async with database.async_session() as verification_session:
        stored = await verification_session.get(UserPreferences, user.id)
        assert stored is not None
        assert stored.dnd_enabled is True
        assert stored.timezone == "Europe/Istanbul"
        assert stored.dnd_start == time(0)
        assert stored.dnd_end == time(0)
        assert stored.dnd_start.tzinfo is None
        assert stored.dnd_end.tzinfo is None


@pytest.mark.asyncio
async def test_forward_migration_preserves_local_clock_and_null_values() -> None:
    """Run the real Alembic revision against temporary PostgreSQL TIMETZ data."""
    assert database.engine.dialect.name == "postgresql"
    migration = _load_migration()

    def exercise(connection: sa.Connection) -> None:
        connection.exec_driver_sql(
            """
            CREATE TEMP TABLE user_preferences (
                dnd_start TIME WITH TIME ZONE NULL,
                dnd_end TIME WITH TIME ZONE NULL
            ) ON COMMIT DROP
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO user_preferences (dnd_start, dnd_end)
            VALUES (
                '08:15:30.123456-05:30'::timetz,
                '22:45:00+03:00'::timetz
            ), (NULL, NULL)
            """
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            with pytest.raises(RuntimeError, match=migration.downgrade_reason):
                migration.downgrade()

        migrated = connection.exec_driver_sql(
            """
            SELECT dnd_start, dnd_end,
                   pg_typeof(dnd_start)::text, pg_typeof(dnd_end)::text
            FROM user_preferences
            WHERE dnd_start IS NOT NULL
            """
        ).one()
        assert migrated[0] == time(8, 15, 30, 123456)
        assert migrated[1] == time(22, 45)
        assert migrated[0].tzinfo is None
        assert migrated[1].tzinfo is None
        assert migrated[2:] == (
            "time without time zone",
            "time without time zone",
        )

        nulls = connection.exec_driver_sql(
            """
            SELECT dnd_start IS NULL, dnd_end IS NULL
            FROM user_preferences
            WHERE dnd_start IS NULL
            """
        ).one()
        assert nulls == (True, True)

    async with database.engine.begin() as connection:
        await connection.run_sync(exercise)
