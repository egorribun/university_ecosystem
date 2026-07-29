import asyncio
import io
import uuid

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers

import app.models as models
from app.auth.security import get_password_hash
from app.core.config import settings
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.user_service import UserService
from app.utils.files import delete_static_file


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
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_update_profile_email_normalizes(async_client, user_factory, db_session):
    password = "ChangeEmail123!"
    hashed = await get_password_hash(password)
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

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.email == "new.email@example.com"


@pytest.mark.asyncio
async def test_update_profile_email_duplicate(async_client, user_factory, db_session):
    password = "DuplicateEmail123!"
    hashed = await get_password_hash(password)
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

    assert response.status_code == 409
    assert "Запись уже существует" in response.json()["detail"]
    assert "existing@example.com" in response.json()["detail"]

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.email == "first-user@example.com"


@pytest.mark.asyncio
async def test_email_change_requires_confirmation(
    async_client, user_factory, db_session, monkeypatch
):
    password = "ConfirmEmail123!"
    hashed = await get_password_hash(password)
    user = await user_factory(
        email="change-me@example.com",
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    token_value = "confirm-token"

    class FakeTask:
        async def kiq(self, *args, **kwargs):
            return

        async def kick(self, *args, **kwargs):
            return

    monkeypatch.setattr(
        "app.services.auth_service.secrets.token_urlsafe",
        lambda *_args, **_kwargs: token_value,
    )
    monkeypatch.setattr("app.services.auth_service.send_auth_email", FakeTask())

    response = await async_client.post(
        "/users/me/email",
        json={"email": "new.confirm@example.com", "password": password},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "change-me@example.com"
    assert body.get("pending_email") == "new.confirm@example.com"

    user = await UserRepository(db_session).get(user.id)
    assert user.email == "change-me@example.com"

    result = await db_session.execute(
        select(models.EmailChangeToken).where(
            models.EmailChangeToken.user_id == user.id
        )
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

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.email == "new.confirm@example.com"

    final = await db_session.execute(
        select(models.EmailChangeToken).where(
            models.EmailChangeToken.user_id == user.id
        )
    )
    final_record = final.scalar_one_or_none()
    assert final_record is not None
    await db_session.refresh(final_record)
    assert final_record.used


@pytest.mark.asyncio
async def test_update_profile_timezone_persisted(
    async_client, user_factory, db_session
):
    password = "TimezonePersist123!"
    hashed = await get_password_hash(password)
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

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.preferences.timezone == "Europe/Paris"


@pytest.mark.asyncio
async def test_update_profile_timezone_invalid(async_client, user_factory):
    password = "TimezoneInvalid123!"
    hashed = await get_password_hash(password)
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


@pytest.mark.asyncio
async def test_delete_avatar_removes_file(async_client, user_factory, db_session):
    password = "DeleteAvatar123!"
    hashed = await get_password_hash(password)
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

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.profile.avatar_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize("avatar_url", ["", "https://example.com/avatar.png"])
async def test_delete_avatar_ignores_invalid_path(
    async_client, user_factory, db_session, avatar_url
):
    password = "IgnoreAvatar123!"
    hashed = await get_password_hash(password)
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

        user_id = user.id
        db_session.expire_all()
        user = await UserRepository(db_session).get(user_id)
        assert user.profile.avatar_url is None
    finally:
        sentinel_path.unlink(missing_ok=True)


@pytest.mark.asyncio
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

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))

    delete_calls: list[str] = []
    original_delete = delete_static_file

    async def tracking_delete(url: str) -> None:
        delete_calls.append(url)
        await original_delete(url)

    monkeypatch.setattr(
        "app.services.user.media_service.delete_static_file", tracking_delete
    )

    from unittest.mock import AsyncMock, MagicMock

    mock_uow = AsyncMock()
    mock_uow.users = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=None)
    mock_uow.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    mock_uow.rollback = AsyncMock()

    service = UserService(mock_uow, AuditService(), AsyncMock())
    service.repo.add = MagicMock()
    # W185 twin-bug fix: media update paths fetch via the eager-loading method.
    service.repo.get_orm_for_update_with_relations.return_value = user
    service.repo._get_orm.return_value = user
    service.repo._to_dto.return_value = user

    with pytest.raises(RuntimeError):
        await service.upload_avatar(user, upload)

    avatar_dir = tmp_path / "avatars"
    assert delete_calls, "delete_static_file should be invoked"
    if avatar_dir.exists():
        assert not any(avatar_dir.iterdir())


@pytest.mark.asyncio
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

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))

    delete_calls: list[str] = []
    original_delete = delete_static_file

    async def tracking_delete(url: str) -> None:
        delete_calls.append(url)
        await original_delete(url)

    monkeypatch.setattr(
        "app.services.user.media_service.delete_static_file", tracking_delete
    )

    from unittest.mock import AsyncMock, MagicMock

    mock_uow = AsyncMock()
    mock_uow.users = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=None)
    mock_uow.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    mock_uow.rollback = AsyncMock()

    service = UserService(mock_uow, AuditService(), AsyncMock())
    service.repo.add = MagicMock()
    # W185 twin-bug fix: media update paths fetch via the eager-loading method.
    service.repo.get_orm_for_update_with_relations.return_value = user
    service.repo._get_orm.return_value = user
    service.repo._to_dto.return_value = user

    with pytest.raises(RuntimeError):
        await service.upload_cover(user, upload)

    cover_dir = tmp_path / "covers"
    assert delete_calls, "delete_static_file should be invoked"
    if cover_dir.exists():
        assert not any(cover_dir.iterdir())


@pytest.mark.asyncio
async def test_delete_cover_removes_file(async_client, user_factory, db_session):
    password = "DeleteCover123!"
    hashed = await get_password_hash(password)
    cover_rel = f"covers/test-cover-{uuid.uuid4().hex}.png"
    cover_path = settings.static_dir_path / cover_rel
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"cover")

    user = await user_factory(
        hashed_password=hashed,
        is_active=True,
        cover_url=f"/static/{cover_rel}",
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.delete("/users/me/cover", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cover_url"] is None
    assert not cover_path.exists()

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.profile.cover_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cover_url", ["", "https://example.com/cover.png"])
async def test_delete_cover_ignores_invalid_path(
    async_client, user_factory, db_session, cover_url
):
    password = "IgnoreCover123!"
    hashed = await get_password_hash(password)
    sentinel_rel = f"covers/sentinel-{uuid.uuid4().hex}.txt"
    sentinel_path = settings.static_dir_path / sentinel_rel
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path.write_text("keep")

    try:
        user = await user_factory(
            hashed_password=hashed,
            is_active=True,
            cover_url=cover_url,
        )

        headers = await _login(async_client, user.email, password)

        response = await async_client.delete("/users/me/cover", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["cover_url"] is None
        assert sentinel_path.exists()

        user_id = user.id
        db_session.expire_all()
        user = await UserRepository(db_session).get(user_id)
        assert user.profile.cover_url is None
    finally:
        sentinel_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_forgot_password_sends_email_via_thread(
    async_client, user_factory, monkeypatch
):
    user = await user_factory(email="forgot-password@example.com")

    event = asyncio.Event()
    captured: dict[str, object] = {}

    class FakeTask:
        async def kiq(self, to_email, link, full_name, locale):
            captured["to_email"] = to_email
            captured["link"] = link
            captured["full_name"] = full_name
            captured["locale"] = locale
            event.set()

        async def kick(self, *args, **kwargs):
            return await self.kiq(*args, **kwargs)

    monkeypatch.setattr("app.services.auth_service.send_auth_email", FakeTask())

    response = await async_client.post("/password/forgot", json={"email": user.email})

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    await asyncio.wait_for(event.wait(), timeout=1)
    assert captured["to_email"] == user.email
    assert "reset-password" in captured["link"]
