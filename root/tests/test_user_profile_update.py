import asyncio
import io
import uuid

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers

from app.api import users
from app.auth.security import get_password_hash
from app.core.config import settings
from app.models import models


def _make_png_bytes(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_update_profile_email_normalizes(async_client, user_factory, db_session):
    password = "ChangeEmail123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        email="original@example.com",
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.put(
        "/users/me",
        json={"email": "New.Email@Example.com  "},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new.email@example.com"

    await db_session.refresh(user)
    assert user.email == "new.email@example.com"


@pytest.mark.anyio
async def test_update_profile_email_duplicate(async_client, user_factory, db_session):
    password = "DuplicateEmail123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        email="first-user@example.com",
        hashed_password=hashed,
        is_active=True,
    )
    await user_factory(email="existing@example.com", is_active=True)

    headers = await _login(async_client, user.email, password)

    headers_ru = {**headers, "Accept-Language": "ru"}

    response = await async_client.put(
        "/users/me",
        json={"email": "Existing@Example.com"},
        headers=headers_ru,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Указанный email уже используется"}

    await db_session.refresh(user)
    assert user.email == "first-user@example.com"


@pytest.mark.anyio
async def test_email_change_requires_confirmation(
    async_client, user_factory, db_session, monkeypatch
):
    password = "ConfirmEmail123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        email="change-me@example.com",
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    token_value = "confirm-token"

    def fake_blocking(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.api.users.secrets.token_urlsafe", lambda *_args, **_kwargs: token_value)
    monkeypatch.setattr("app.api.users._send_reset_email_blocking", fake_blocking)

    response = await async_client.post(
        "/users/me/email",
        json={"email": "new.confirm@example.com", "password": password},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "change-me@example.com"
    assert body.get("pending_email") == "new.confirm@example.com"

    await db_session.refresh(user)
    assert user.email == "change-me@example.com"

    result = await db_session.execute(
        select(models.EmailChangeToken).where(models.EmailChangeToken.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert not record.used

    bad_response = await async_client.post(
        "/users/me/email/confirm",
        json={"token": "wrong-token"},
        headers=headers,
    )
    assert bad_response.status_code == 400

    confirm_response = await async_client.post(
        "/users/me/email/confirm",
        json={"token": token_value},
        headers=headers,
    )

    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["email"] == "new.confirm@example.com"
    assert confirmed.get("pending_email") is None

    await db_session.refresh(user)
    assert user.email == "new.confirm@example.com"

    final = await db_session.execute(
        select(models.EmailChangeToken).where(models.EmailChangeToken.user_id == user.id)
    )
    final_record = final.scalar_one_or_none()
    assert final_record is not None
    await db_session.refresh(final_record)
    assert final_record.used


@pytest.mark.anyio
async def test_update_profile_timezone_persisted(
    async_client, user_factory, db_session
):
    password = "TimezonePersist123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.put(
        "/users/me",
        json={"timezone": "Europe/Paris"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Europe/Paris"

    await db_session.refresh(user)
    assert user.timezone == "Europe/Paris"


@pytest.mark.anyio
async def test_update_profile_timezone_invalid(async_client, user_factory):
    password = "TimezoneInvalid123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.put(
        "/users/me",
        json={"timezone": "Invalid/Zone"},
        headers=headers,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"][-1] == "timezone"
    assert detail["msg"] == "Enter a valid time zone identifier"


@pytest.mark.anyio
async def test_delete_avatar_removes_file(async_client, user_factory, db_session):
    password = "DeleteAvatar123!"
    hashed = get_password_hash(password)
    avatar_rel = f"avatars/test-avatar-{uuid.uuid4().hex}.png"
    avatar_path = settings.static_dir_path / avatar_rel
    avatar_path.parent.mkdir(parents=True, exist_ok=True)
    avatar_path.write_bytes(b"avatar")

    user = await user_factory(
        hashed_password=hashed,
        is_active=True,
        avatar_url=f"/static/{avatar_rel}",
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.delete("/users/me/avatar", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["avatar_url"] is None
    assert not avatar_path.exists()

    await db_session.refresh(user)
    assert user.avatar_url is None


@pytest.mark.anyio
@pytest.mark.parametrize("avatar_url", ["", "https://example.com/avatar.png"])
async def test_delete_avatar_ignores_invalid_path(
    async_client, user_factory, db_session, avatar_url
):
    password = "IgnoreAvatar123!"
    hashed = get_password_hash(password)
    sentinel_rel = f"avatars/sentinel-{uuid.uuid4().hex}.txt"
    sentinel_path = settings.static_dir_path / sentinel_rel
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path.write_text("keep")

    try:
        user = await user_factory(
            hashed_password=hashed,
            is_active=True,
            avatar_url=avatar_url,
        )

        headers = await _login(async_client, user.email, password)

        response = await async_client.delete("/users/me/avatar", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["avatar_url"] is None
        assert sentinel_path.exists()

        await db_session.refresh(user)
        assert user.avatar_url is None
    finally:
        sentinel_path.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_upload_avatar_cleans_up_on_commit_failure(
    tmp_path, monkeypatch, db_session, user_factory
):
    user = await user_factory(is_active=True)

    payload = _make_png_bytes()
    upload = UploadFile(
        filename="avatar.png",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "image/png"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    delete_calls: list[str] = []
    original_delete = users.delete_static_file

    async def tracking_delete(url: str) -> None:
        delete_calls.append(url)
        await original_delete(url)

    monkeypatch.setattr(users, "delete_static_file", tracking_delete)

    async def failing_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError):
        await users.upload_avatar(upload, request=None, db=db_session, user=user)

    avatar_dir = tmp_path / "avatars"
    assert delete_calls, "delete_static_file should be invoked"
    if avatar_dir.exists():
        assert not any(avatar_dir.iterdir())

    await db_session.refresh(user)
    assert user.avatar_url is None


@pytest.mark.anyio
async def test_upload_cover_cleans_up_on_commit_failure(
    tmp_path, monkeypatch, db_session, user_factory
):
    user = await user_factory(is_active=True)

    payload = _make_png_bytes(color=(0, 255, 0))
    upload = UploadFile(
        filename="cover.png",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "image/png"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    delete_calls: list[str] = []
    original_delete = users.delete_static_file

    async def tracking_delete(url: str) -> None:
        delete_calls.append(url)
        await original_delete(url)

    monkeypatch.setattr(users, "delete_static_file", tracking_delete)

    async def failing_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError):
        await users.upload_cover(upload, request=None, db=db_session, user=user)

    cover_dir = tmp_path / "covers"
    assert delete_calls, "delete_static_file should be invoked"
    if cover_dir.exists():
        assert not any(cover_dir.iterdir())

    await db_session.refresh(user)
    assert user.cover_url is None


@pytest.mark.anyio
async def test_forgot_password_sends_email_via_thread(
    async_client, user_factory, monkeypatch
):
    user = await user_factory(email="forgot-password@example.com")

    event = asyncio.Event()
    captured: dict[str, object] = {}

    async def fake_run_sync(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs
        event.set()
        return None

    def fake_blocking(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.users.anyio.to_thread.run_sync", fake_run_sync)
    monkeypatch.setattr("app.api.users._send_reset_email_blocking", fake_blocking)

    response = await async_client.post("/password/forgot", json={"email": user.email})

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    await asyncio.wait_for(event.wait(), timeout=1)
    assert captured.get("func") is fake_blocking
    assert captured.get("args") is not None
    assert captured["args"][0] == user.email
