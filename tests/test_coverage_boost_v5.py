import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.api.notifications import _decode_cursor, _encode_cursor
from app.models import models
from app.utils import ratelimit, sanitization
from tests.fixtures.auth.auth_fixtures import create_access_token


def test_sanitization_html():
    scr = "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert sanitization.sanitize_html("<script>alert(1)</script>") == scr
    assert (
        sanitization.sanitize_html("<b>Bold</b>", allow_basic_tags=True)
        == "<b>Bold</b>"
    )
    assert sanitization.sanitize_html(None) == ""


def test_sanitization_rich_text():
    html = (
        "<p>Hello <script>alert(1)</script> "
        '<a href="https://example.com" onclick="bad()">Link</a></p>'
    )
    sanitized = sanitization.sanitize_rich_text(html)
    assert "<script>" not in sanitized
    assert "onclick" not in sanitized
    assert (
        '<a href="https://example.com" rel="noopener noreferrer" target="_blank">'
        in sanitized
    )
    assert "<p>" in sanitized
    assert "</p>" in sanitized
    assert sanitization.sanitize_rich_text(None) == ""


def test_sanitization_filename():
    assert (
        sanitization.sanitize_filename("test/../../../etc/passwd")
        == "test_._._._etc_passwd"
    )
    assert sanitization.sanitize_filename("file\x00name.txt") == "filename.txt"
    assert (
        sanitization.sanitize_filename("a" * 300 + ".txt") == "a" * (255 - 4) + ".txt"
    )
    assert sanitization.sanitize_filename(None) == "unnamed"


def test_sanitization_path(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    assert sanitization.sanitize_path("test.txt", base) == base / "test.txt"
    assert sanitization.sanitize_path("../outside.txt", base) is None


def test_sanitization_url():
    assert sanitization.sanitize_url("https://google.com") == "https://google.com"
    assert sanitization.sanitize_url("javascript:alert(1)") is None
    assert sanitization.sanitize_url("https://127.0.0.1") is None
    assert sanitization.sanitize_url("https://localhost") is None
    assert sanitization.sanitize_url("https://user:pass@google.com") is None


def test_truncate():
    assert sanitization.truncate("Hello World", 5) == "He..."
    assert sanitization.truncate("Hi", 5) == "Hi"
    assert sanitization.truncate(None, 5) is None


def test_sanitize_optional_text():
    assert sanitization.sanitize_optional_text("  ") is None
    assert sanitization.sanitize_optional_text(b"bytes") == "bytes"
    assert sanitization.sanitize_optional_text(123) == "123"


def test_ratelimit_memory():
    limiter = ratelimit.MemoryLimiter()
    limiter.check("test", 2, 60, message="Error")
    limiter.check("test", 2, 60, message="Error")
    with pytest.raises(HTTPException):  # raise_http_error
        limiter.check("test", 2, 60, message="Error")
    limiter.reset()
    limiter.check("test", 2, 60, message="Error")


def test_ratelimit_utils():
    assert ratelimit._normalize_ip("[::1]") == "::1"
    assert ratelimit._normalize_ip("1.2.3.4:80") == "1.2.3.4"

    # Forwarded header parsing
    header = 'for=192.0.2.60; proto=http, for="[2001:db8:cafe::17]:4711"'
    assert ratelimit._extract_ip_from_forwarded(header) == "192.0.2.60"


@pytest.mark.asyncio
async def test_notification_clear_single(
    root_client: AsyncClient, db_session, user_factory
):
    user = await user_factory()
    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    n = models.Notification(
        id=uuid.uuid4(), user_id=user.id, title="To Clear", created_at=datetime.now(UTC)
    )
    db_session.add(n)
    await db_session.commit()

    response = await root_client.delete(
        f"/api/v1/notifications/{n.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    # Check it's gone
    from sqlalchemy import select

    res = await db_session.execute(
        select(models.Notification).where(models.Notification.id == n.id)
    )
    assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_notification_clear_all(
    root_client: AsyncClient, db_session, user_factory
):
    user = await user_factory()
    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    for i in range(3):
        n = models.Notification(
            id=uuid.uuid4(),
            user_id=user.id,
            title=f"N{i}",
            created_at=datetime.now(UTC),
        )
        db_session.add(n)
    await db_session.commit()

    response = await root_client.delete(
        "/api/v1/notifications", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] >= 3


def test_notification_cursor_edge_cases():
    dt = datetime(2025, 1, 1, tzinfo=UTC)
    uid = uuid.uuid4()
    cursor = _encode_cursor(dt, uid)
    decoded_dt, decoded_uid = _decode_cursor(cursor)
    assert decoded_dt.replace(tzinfo=UTC) == dt
    assert decoded_uid == str(uid)

    assert _decode_cursor("invalid-base64") is None
    assert _decode_cursor("bm90LWEtc2VwYXJhdG9y") is None  # "not-a-separator"
