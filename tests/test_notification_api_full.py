"""Comprehensive tests for app/api/notifications.py.

Covers: mark_read_single, mark_all_read, delete_notification,
clear_notifications, helper functions (_parse_datetime, _coerce_bool,
_coerce_int, _localized_notification_field, _serialize_notification).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
from app.models import Notification

_TEST_PASSWORD = "TestPassword123!"  # pragma: allowlist secret


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.cookies.get("access_token_v2") or client.cookies.get("access_token_v2")
    assert token, "access_token_v2 cookie not found after login"
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


async def _create_notification(
    db: AsyncSession, user_id: uuid.UUID, **kwargs
) -> Notification:
    defaults = {
        "user_id": user_id,
        "title": f"Test Notification {uuid.uuid4().hex[:6]}",
        "body": "Test body content",
        "type": "info",
        "read": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif


# ---------------------------------------------------------------------------
# PATCH /{notif_id}/read
# ---------------------------------------------------------------------------


class TestMarkReadSingle:
    @pytest.mark.asyncio
    async def test_mark_read_success(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        notif = await _create_notification(db_session, user.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            f"/notifications/{notif.id}/read", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify in DB
        await db_session.refresh(notif)
        assert notif.read is True
        assert notif.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_already_read(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        notif = await _create_notification(
            db_session, user.id, read=True, read_at=datetime.now(UTC)
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            f"/notifications/{notif.id}/read", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_mark_read_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            f"/notifications/{uuid.uuid4()}/read", headers=headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_read_other_user(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        """Cannot mark another user's notification as read."""
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        other = await user_factory(hashed_password=hashed, is_active=True)
        notif = await _create_notification(db_session, other.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            f"/notifications/{notif.id}/read", headers=headers
        )
        assert resp.status_code == 404  # Ownership check


# ---------------------------------------------------------------------------
# POST /read-all
# ---------------------------------------------------------------------------


class TestMarkAllRead:
    @pytest.mark.asyncio
    async def test_mark_all_read(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        await _create_notification(db_session, user.id)
        await _create_notification(db_session, user.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.post("/notifications/read-all", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["updated"] == 2

    @pytest.mark.asyncio
    async def test_mark_all_read_empty(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.post("/notifications/read-all", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_skips_already_read(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        await _create_notification(db_session, user.id, read=False)
        await _create_notification(
            db_session, user.id, read=True, read_at=datetime.now(UTC)
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.post("/notifications/read-all", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1


# ---------------------------------------------------------------------------
# DELETE /{notif_id}
# ---------------------------------------------------------------------------


class TestDeleteNotification:
    @pytest.mark.asyncio
    async def test_delete_success(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        notif = await _create_notification(db_session, user.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.delete(f"/notifications/{notif.id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        row = (
            await db_session.execute(
                select(Notification).where(Notification.id == notif.id)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.delete(
            f"/notifications/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_users_notification(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        other = await user_factory(hashed_password=hashed, is_active=True)
        notif = await _create_notification(db_session, other.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.delete(f"/notifications/{notif.id}", headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE / (clear all)
# ---------------------------------------------------------------------------


class TestClearNotifications:
    @pytest.mark.asyncio
    async def test_clear_all(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        await _create_notification(db_session, user.id)
        await _create_notification(db_session, user.id)
        headers = await _login(async_client, user.email)

        resp = await async_client.delete("/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["deleted"] == 2

    @pytest.mark.asyncio
    async def test_clear_empty(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.delete("/notifications", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


# ---------------------------------------------------------------------------
# GET /notifications (list)
# ---------------------------------------------------------------------------


class TestListNotifications:
    @pytest.mark.asyncio
    async def test_list_empty(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_list_with_notifications(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        await _create_notification(db_session, user.id)
        await _create_notification(
            db_session, user.id, read=True, read_at=datetime.now(UTC)
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["unread_count"] == 1
        for item in data["items"]:
            assert item["metadata"]["notificationId"] == item["id"]
            assert item["metadata"]["url"] == (item.get("url") or "/")


# ---------------------------------------------------------------------------
# Helper functions — _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_datetime_aware(self):
        from app.api.notifications import _parse_datetime

        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = _parse_datetime(dt)
        assert result == dt

    def test_datetime_naive(self):
        from app.api.notifications import _parse_datetime

        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = _parse_datetime(dt)
        assert result is not None
        assert result.tzinfo is not None

    def test_int_timestamp(self):
        from app.api.notifications import _parse_datetime

        result = _parse_datetime(1704067200)  # 2024-01-01 00:00:00 UTC
        assert result is not None
        assert result.year == 2024

    def test_int_timestamp_milliseconds(self):
        from app.api.notifications import _parse_datetime

        result = _parse_datetime(1704067200000)  # ms timestamp
        assert result is not None
        assert result.year == 2024

    def test_string_iso(self):
        from app.api.notifications import _parse_datetime

        result = _parse_datetime("2024-01-01T12:00:00Z")
        assert result is not None
        assert result.year == 2024

    def test_string_numeric(self):
        from app.api.notifications import _parse_datetime

        result = _parse_datetime("1704067200")
        assert result is not None

    def test_string_empty(self):
        from app.api.notifications import _parse_datetime

        assert _parse_datetime("") is None
        assert _parse_datetime("   ") is None

    def test_invalid_string(self):
        from app.api.notifications import _parse_datetime

        assert _parse_datetime("not-a-date") is None

    def test_none(self):
        from app.api.notifications import _parse_datetime

        assert _parse_datetime(None) is None

    def test_overflow_timestamp(self):
        from app.api.notifications import _parse_datetime

        assert _parse_datetime(99999999999999999) is None


# ---------------------------------------------------------------------------
# Helper functions — _coerce_bool, _coerce_int
# ---------------------------------------------------------------------------


class TestCoerceBool:
    def test_bool_true(self):
        from app.api.notifications import _coerce_bool

        assert _coerce_bool(True) is True
        assert _coerce_bool(False) is False

    def test_int(self):
        from app.api.notifications import _coerce_bool

        assert _coerce_bool(1) is True
        assert _coerce_bool(0) is False

    def test_string_truthy(self):
        from app.api.notifications import _coerce_bool

        for val in ("1", "true", "True", "TRUE", "t", "yes", "y", "on"):
            assert _coerce_bool(val) is True, f"Failed for {val!r}"

    def test_string_falsy(self):
        from app.api.notifications import _coerce_bool

        for val in ("0", "false", "False", "f", "no", "n", "off"):
            assert _coerce_bool(val) is False, f"Failed for {val!r}"

    def test_other(self):
        from app.api.notifications import _coerce_bool

        assert _coerce_bool([1]) is True  # truthy list
        assert _coerce_bool([]) is False  # empty list


class TestCoerceInt:
    def test_none(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int(None) == 0
        assert _coerce_int(None, default=5) == 5

    def test_bool(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int(True) == 1
        assert _coerce_int(False) == 0

    def test_int(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int(42) == 42

    def test_float(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int(3.7) == 3

    def test_string(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int("42") == 42
        assert _coerce_int("3.7") == 3

    def test_string_empty(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int("") == 0

    def test_string_invalid(self):
        from app.api.notifications import _coerce_int

        assert _coerce_int("abc") == 0
        assert _coerce_int("abc", default=99) == 99


# ---------------------------------------------------------------------------
# Helper functions — _is_missing_column_error, _ensure_utc
# ---------------------------------------------------------------------------


class TestMissingColumnError:
    def test_matching_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        from app.api.notifications import _is_missing_column_error

        exc = SQLAlchemyError("no such column: notification.body_en")
        assert _is_missing_column_error(exc) is True

    def test_non_matching_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        from app.api.notifications import _is_missing_column_error

        exc = SQLAlchemyError("connection refused")
        assert _is_missing_column_error(exc) is False


class TestEnsureUtc:
    def test_valid_datetime(self):
        from app.api.notifications import _ensure_utc

        dt = datetime(2024, 1, 1, tzinfo=UTC)
        result = _ensure_utc(dt)
        assert result == dt

    def test_invalid_value(self):
        from app.api.notifications import _ensure_utc

        result = _ensure_utc(None)
        # Should return datetime.now(UTC) as fallback
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
