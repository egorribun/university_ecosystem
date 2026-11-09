"""The privileged reminder worker must retain authoritative tenant ownership."""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.models import User
from app.services.notifications import schedule_reminders
from app.workers import notifications as worker


class _Result:
    def __init__(self, rows=(), scalars=(), value=None):
        self.rows = list(rows)
        self.values = list(scalars)
        self.value = value

    def __iter__(self):
        return iter(self.rows)

    def scalars(self):
        return SimpleNamespace(all=lambda: self.values)

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_bypass_scheduler_partitions_reminders_by_trusted_tenant(monkeypatch):
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    groups = [uuid.uuid4() for _ in range(4)]
    users = [uuid.uuid4() for _ in range(6)]
    fixed_now = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)
    clock = SimpleNamespace(**vars(dt))

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                fixed_now.replace(tzinfo=None)
                if tz is None
                else fixed_now.astimezone(tz)
            )

    clock.datetime = FixedDateTime
    monkeypatch.setattr(schedule_reminders, "dt", clock)
    monkeypatch.setattr(
        schedule_reminders.settings, "campus_timezone", "Europe/Istanbul"
    )
    monkeypatch.setattr(
        schedule_reminders,
        "build_schedule_reminder_message",
        lambda schedule, **_: (
            schedule.subject,
            "body",
            str(schedule.id),
            {},
            {},
            {},
            str(schedule.id),
        ),
    )
    schedules = [
        SimpleNamespace(
            id=uuid.uuid4(),
            group_id=group,
            subject=title,
            weekday="monday",
            parity="both",
            start_time=dt.datetime(1970, 1, 5, 3, tzinfo=dt.UTC),
        )
        for group, title in zip(
            groups, ("A", "B", "unowned", "wrong group"), strict=True
        )
    ]
    schedule_rows = [
        (schedules[0], tenant_a, tenant_a),
        (schedules[1], tenant_b, tenant_b),
        (schedules[2], None, None),
        (schedules[3], tenant_a, tenant_b),
    ]
    user_rows = [
        (users[0], groups[0], tenant_a),
        (users[1], groups[1], tenant_b),
        (users[2], groups[0], tenant_b),
        (users[3], groups[0], None),
        (users[4], groups[2], tenant_a),
        (users[5], groups[3], tenant_a),
    ]
    stale_notifications = [
        (users[0], str(schedules[0].id), None),
        (users[1], str(schedules[1].id), tenant_a),
    ]

    class Session:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        committed = False

        def __init__(self):
            self.settings: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, statement, params=None, **_kwargs):
            sql = str(statement)
            if "current_setting" in sql:
                return _Result(value="original-scope")
            if "FROM schedule" in sql:
                return _Result(rows=schedule_rows, scalars=schedules)
            if "FROM users" in sql:
                rows = (
                    user_rows
                    if "users.tenant_id" in sql
                    else [row[:2] for row in user_rows]
                )
                return _Result(rows=rows)
            if "FROM notifications" in sql:
                rows = (
                    stale_notifications
                    if "notifications.tenant_id" in sql
                    else [row[:2] for row in stale_notifications]
                )
                return _Result(rows=rows)
            if "set_config" in sql:
                self.settings.append(params["tenant_id"])
                return _Result()
            raise AssertionError(f"Unexpected query: {sql}")

        async def commit(self):
            self.committed = True

    session = Session()
    monkeypatch.setattr(worker, "async_session", lambda: session)
    produced = []

    async def create(_db, *, title, user_ids, user_filter, **_kwargs):
        assert bypass_rls_ctx.get() is False
        params = user_filter(select(User.id)).compile().params.values()
        assert uuid.UUID(get_current_tenant()) in params
        assert groups[0 if title == "A" else 1] in params
        produced.append((title, get_current_tenant(), set(user_ids)))
        return len(user_ids)

    monkeypatch.setattr(schedule_reminders, "create_notifications_for_users", create)
    scheduler = worker.NotificationsScheduler(
        poll_seconds=1, window_minutes=10, max_backoff_seconds=1
    )
    tenant_token = tenant_id_ctx.set("ambient")
    bypass_token = bypass_rls_ctx.set(True)
    try:
        assert await scheduler.run_once() == 2
        assert set(
            (title, tenant, frozenset(ids)) for title, tenant, ids in produced
        ) == {
            ("A", str(tenant_a), frozenset({users[0]})),
            ("B", str(tenant_b), frozenset({users[1]})),
        }
        assert get_current_tenant() == "ambient"
        assert bypass_rls_ctx.get() is True
        assert set(session.settings[:-1]) == {str(tenant_a), str(tenant_b)}
        assert session.settings[-1] == "original-scope"
        assert session.committed
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bypass", "restore_fails"), [(True, False), (False, False), (True, True)]
)
async def test_reminder_scan_restores_context_after_failure(
    monkeypatch: pytest.MonkeyPatch, bypass: bool, restore_fails: bool
) -> None:
    tenant = str(uuid.uuid4())
    original_guc = str(uuid.uuid4())
    restoration = SQLAlchemyError("restore failed") if restore_fails else _Result()
    db = AsyncSession()
    monkeypatch.setattr(
        db,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    execute = AsyncMock(side_effect=[_Result(value=original_guc), restoration])
    monkeypatch.setattr(db, "execute", execute)

    async def fail_scan(*_args, **_kwargs):
        assert get_current_tenant() == ("" if bypass else tenant)
        assert bypass_rls_ctx.get() is False
        raise ValueError("scan failed")

    monkeypatch.setattr(schedule_reminders, "_generate_schedule_reminders", fail_scan)
    tenant_token = tenant_id_ctx.set(tenant)
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        with pytest.raises(ValueError, match="scan failed") as raised:
            await schedule_reminders.generate_schedule_reminders(db)
        assert get_current_tenant() == tenant
        assert bypass_rls_ctx.get() is bypass
        assert execute.await_args.args[1] == {"tenant_id": original_guc}
        if restore_fails:
            assert "roll back the transaction" in raised.value.__notes__[0]
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await db.close()


@pytest.mark.asyncio
async def test_reminder_scan_rejects_unsupported_database_dialects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSession() as db:
        monkeypatch.setattr(
            db,
            "get_bind",
            lambda: SimpleNamespace(dialect=SimpleNamespace(name="other")),
        )
        with pytest.raises(RuntimeError, match="Unsupported reminder database dialect"):
            await schedule_reminders.generate_schedule_reminders(db)


@pytest.mark.asyncio
async def test_restoration_error_after_success_is_not_silenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = str(uuid.uuid4())
    async with AsyncSession() as db:
        monkeypatch.setattr(
            db,
            "get_bind",
            lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        )
        monkeypatch.setattr(
            db,
            "execute",
            AsyncMock(side_effect=[_Result(), SQLAlchemyError("restore failed")]),
        )
        monkeypatch.setattr(
            schedule_reminders,
            "_generate_schedule_reminders",
            AsyncMock(return_value=0),
        )
        tenant_token = tenant_id_ctx.set(tenant)
        bypass_token = bypass_rls_ctx.set(True)
        try:
            with pytest.raises(SQLAlchemyError, match="restore failed"):
                await schedule_reminders.generate_schedule_reminders(db)
            assert get_current_tenant() == tenant
            assert bypass_rls_ctx.get() is True
        finally:
            bypass_rls_ctx.reset(bypass_token)
            tenant_id_ctx.reset(tenant_token)
