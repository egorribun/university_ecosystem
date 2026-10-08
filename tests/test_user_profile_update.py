import asyncio
import io
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import Headers

import app.models as models
from app.auth.security import get_password_hash
from app.core.config import settings
from app.repositories.user_repository import UserRepository
from app.schemas.users import UserProfileUpdate
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
async def test_update_profile_rejects_email_and_preserves_verified_email_state(
    async_client, user_factory, db_session
):
    password = "ChangeEmail123!"
    hashed = await get_password_hash(password)
    user = await user_factory(
        email="original@example.com",
        hashed_password=hashed,
        is_active=True,
        email_verified_at=datetime.now(UTC),
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.put(
        "/users/me",
        json={"email": "New.Email@Example.com  "},
        headers=headers,
    )

    assert response.status_code == 422
    assert "use /users/me/email" in response.text

    user_id = user.id
    db_session.expire_all()
    user = await UserRepository(db_session).get(user_id)
    assert user.email == "original@example.com"
    assert user.email_verified_at is not None
    assert user.email_mfa_enabled_at is None


@pytest.mark.asyncio
async def test_controlled_email_change_rejects_duplicate_after_normalization(
    async_client, user_factory, db_session
):
    password = "DuplicateEmail123!"
    hashed = await get_password_hash(password)
    user = await user_factory(
        email="first-user@example.com",
        hashed_password=hashed,
        is_active=True,
    )
    await user_factory(email="existing@example.com", is_active=True)

    headers = await _login(async_client, user.email, password)

    response = await async_client.post(
        "/users/me/email",
        json={"email": "Existing@Example.com", "password": password},
        headers=headers,
    )

    assert response.status_code == 400

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
        json={"email": "New.Confirm@Example.com", "password": password},
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
async def test_self_profile_responses_include_nested_profile_detail(
    async_client, user_factory, db_session
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    user_id = user.id
    user_role = user.role.value
    headers = await _login(async_client, user.email, password)

    update_response = await async_client.put(
        "/users/me",
        json={
            "full_name": "Profile Detail User",
            "profile_detail": {
                "about": "Synthetic profile bio",
                "department": "Synthetic department",
            },
            "education_path": {
                "institute": "Synthetic institute",
                "course": "Synthetic course",
            },
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    update_body = update_response.json()
    assert update_body["about"] == "Synthetic profile bio"
    assert update_body["profile_detail"]["about"] == "Synthetic profile bio"
    assert update_body["profile_detail"]["department"] == "Synthetic department"
    assert update_body["education_path"]["institute"] == "Synthetic institute"
    assert update_body["education_path"]["course"] == "Synthetic course"

    read_response = await async_client.get("/users/me", headers=headers)

    assert read_response.status_code == 200
    read_body = read_response.json()
    assert read_body["about"] == "Synthetic profile bio"
    assert read_body["profile_detail"]["about"] == "Synthetic profile bio"
    assert read_body["profile_detail"]["department"] == "Synthetic department"
    assert read_body["education_path"]["institute"] == "Synthetic institute"
    assert read_body["education_path"]["course"] == "Synthetic course"

    partial_response = await async_client.put(
        "/users/me",
        json={
            "about": "Flat profile bio",
            "profile_detail": {"department": None},
            "education_path": {"course": "Updated course"},
        },
        headers=headers,
    )

    assert partial_response.status_code == 200
    partial_body = partial_response.json()
    assert partial_body["about"] == "Flat profile bio"
    assert partial_body["profile_detail"]["about"] == "Flat profile bio"
    assert partial_body["profile_detail"]["department"] is None
    assert partial_body["education_path"]["institute"] == "Synthetic institute"
    assert partial_body["education_path"]["course"] == "Updated course"

    db_session.expire_all()
    partially_stored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == user_id)
    )
    assert partially_stored_profile is not None
    assert partially_stored_profile.about == "Flat profile bio"
    assert partially_stored_profile.department is None
    partially_stored_education = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == user_id)
    )
    assert partially_stored_education is not None
    assert partially_stored_education.institute == "Synthetic institute"
    assert partially_stored_education.course == "Updated course"

    null_response = await async_client.put(
        "/users/me",
        json={"profile_detail": None, "education_path": None},
        headers=headers,
    )

    assert null_response.status_code == 200
    null_body = null_response.json()
    assert null_body["about"] == "Flat profile bio"
    assert null_body["profile_detail"]["about"] == "Flat profile bio"
    assert null_body["education_path"] is None

    null_read_response = await async_client.get("/users/me", headers=headers)
    assert null_read_response.status_code == 200
    null_read_body = null_read_response.json()
    assert null_read_body["about"] == "Flat profile bio"
    assert null_read_body["profile_detail"]["about"] == "Flat profile bio"
    assert null_read_body["education_path"] is None

    role_response = await async_client.put(
        "/users/me", json={"role": "admin"}, headers=headers
    )
    assert role_response.status_code == 422
    role_read_response = await async_client.get("/users/me", headers=headers)
    assert role_read_response.status_code == 200
    assert role_read_response.json()["role"] == user_role

    db_session.expire_all()
    stored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == user_id)
    )
    assert stored_profile is not None
    assert stored_profile.about == "Flat profile bio"
    assert stored_profile.department is None
    stored_education = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == user_id)
    )
    assert stored_education is None


@pytest.mark.asyncio
async def test_profile_about_accepts_database_limit_for_flat_and_nested_updates(
    async_client, user_factory, db_session
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    user_id = user.id
    headers = await _login(async_client, user.email, password)

    flat_about = "f" * 4096
    flat_response = await async_client.put(
        "/users/me", json={"about": flat_about}, headers=headers
    )

    assert flat_response.status_code == 200
    assert flat_response.json()["about"] == flat_about

    nested_about = "n" * 4096
    nested_response = await async_client.put(
        "/users/me",
        json={"profile_detail": {"about": nested_about}},
        headers=headers,
    )

    assert nested_response.status_code == 200
    nested_body = nested_response.json()
    assert nested_body["about"] == nested_about
    assert nested_body["profile_detail"]["about"] == nested_about

    db_session.expire_all()
    stored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == user_id)
    )
    assert stored_profile is not None
    assert stored_profile.about == nested_about


@pytest.mark.asyncio
async def test_profile_about_over_database_limit_is_rejected_without_persisting(
    async_client, user_factory
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    headers = await _login(async_client, user.email, password)

    before_response = await async_client.get("/users/me", headers=headers)
    assert before_response.status_code == 200
    before_body = before_response.json()

    flat_response = await async_client.put(
        "/users/me",
        json={"about": "x" * 4097},
        headers=headers,
    )

    assert flat_response.status_code == 422
    nested_response = await async_client.put(
        "/users/me",
        json={"profile_detail": {"about": "x" * 4097}},
        headers=headers,
    )

    assert nested_response.status_code == 422
    after_response = await async_client.get("/users/me", headers=headers)
    assert after_response.status_code == 200
    after_body = after_response.json()
    assert after_body["about"] == before_body["about"]
    assert after_body["profile_detail"] == before_body["profile_detail"]


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


_PROFILE_AND_EDUCATION_COLUMN_LIMITS = (
    (("full_name",), 256),
    (("about",), 4096),
    (("telegram",), 128),
    (("status",), 256),
    (("achievements",), 2048),
    (("department",), 256),
    (("position",), 256),
    (("profile_detail", "about"), 4096),
    (("profile_detail", "telegram"), 128),
    (("profile_detail", "status"), 256),
    (("profile_detail", "achievements"), 2048),
    (("profile_detail", "department"), 256),
    (("profile_detail", "position"), 256),
    (("institute",), 512),
    (("course",), 64),
    (("education_level",), 128),
    (("track",), 256),
    (("program",), 512),
    (("record_book_number",), 64),
    (("education_path", "institute"), 512),
    (("education_path", "course"), 64),
    (("education_path", "education_level"), 128),
    (("education_path", "track"), 256),
    (("education_path", "program"), 512),
    (("education_path", "record_book_number"), 64),
)


def _profile_update_body(path: tuple[str, ...], value: str) -> dict[str, object]:
    if len(path) == 1:
        return {path[0]: value}
    parent, child = path
    return {parent: {child: value}}


@pytest.mark.parametrize(("path", "limit"), _PROFILE_AND_EDUCATION_COLUMN_LIMITS)
def test_profile_update_schema_accepts_database_string_limits(
    path: tuple[str, ...], limit: int
) -> None:
    body = _profile_update_body(path, "x" * limit)
    parsed = UserProfileUpdate.model_validate(body)

    assert parsed.model_dump(exclude_unset=True) == body


@pytest.mark.parametrize(("path", "limit"), _PROFILE_AND_EDUCATION_COLUMN_LIMITS)
def test_profile_update_schema_rejects_database_string_overflow(
    path: tuple[str, ...], limit: int
) -> None:
    body = _profile_update_body(path, "x" * (limit + 1))

    with pytest.raises(ValidationError) as error:
        UserProfileUpdate.model_validate(body)

    assert path in {tuple(item["loc"]) for item in error.value.errors()}


@pytest.mark.parametrize(
    ("body", "path"),
    [
        ({"timezone": "x" * 65}, ("timezone",)),
        ({"preferences": {"timezone": "x" * 65}}, ("preferences", "timezone")),
    ],
)
def test_timezone_update_rejects_values_over_its_database_column_limit(
    body: dict[str, object], path: tuple[str, ...]
) -> None:
    assert (
        UserProfileUpdate(timezone="America/Argentina/ComodRivadavia").timezone
        == "America/Argentina/ComodRivadavia"
    )

    with pytest.raises(ValidationError) as error:
        UserProfileUpdate.model_validate(body)

    assert any(
        tuple(item["loc"]) == path and item["type"] == "string_too_long"
        for item in error.value.errors()
    )


@pytest.mark.asyncio
async def test_profile_and_education_column_limits_persist_at_flat_and_nested_paths(
    async_client, user_factory, db_session
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    user_id = user.id
    headers = await _login(async_client, user.email, password)

    flat_profile = {
        "full_name": "n" * 256,
        "telegram": "t" * 128,
        "status": "s" * 256,
        "achievements": "a" * 2048,
        "department": "d" * 256,
        "position": "p" * 256,
    }
    flat_education = {
        "institute": "i" * 512,
        "course": "c" * 64,
        "education_level": "l" * 128,
        "track": "t" * 256,
        "program": "p" * 512,
        "record_book_number": "r" * 64,
    }
    flat_response = await async_client.put(
        "/users/me",
        json={**flat_profile, **flat_education, "timezone": "UTC"},
        headers=headers,
    )
    assert flat_response.status_code == 200
    assert flat_response.json()["full_name"] == flat_profile["full_name"]

    nested_profile = {
        key: value for key, value in flat_profile.items() if key != "full_name"
    }
    nested_education = {
        "institute": "I" * 512,
        "course": "C" * 64,
        "education_level": "L" * 128,
        "track": "T" * 256,
        "program": "P" * 512,
        "record_book_number": "R" * 64,
    }
    nested_response = await async_client.put(
        "/users/me",
        json={
            "profile_detail": nested_profile,
            "education_path": nested_education,
            "preferences": {"timezone": "UTC"},
        },
        headers=headers,
    )
    assert nested_response.status_code == 200
    nested_body = nested_response.json()
    for field, value in nested_profile.items():
        assert nested_body["profile_detail"][field] == value
    assert nested_body["education_path"] == nested_education

    db_session.expire_all()
    stored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == user_id)
    )
    stored_education = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == user_id)
    )
    assert stored_profile is not None
    assert stored_profile.full_name == flat_profile["full_name"]
    for field, value in nested_profile.items():
        assert getattr(stored_profile, field) == value
    assert stored_education is not None
    for field, value in nested_education.items():
        assert getattr(stored_education, field) == value


@pytest.mark.asyncio
async def test_profile_column_overflow_returns_422_without_changing_profile(
    async_client, user_factory
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    headers = await _login(async_client, user.email, password)
    before_response = await async_client.get("/users/me", headers=headers)
    assert before_response.status_code == 200
    before_body = before_response.json()

    overflow_body = {
        "full_name": "n" * 257,
        "telegram": "t" * 129,
        "profile_detail": {"department": "d" * 257},
        "institute": "i" * 513,
        "education_path": {"program": "p" * 513},
    }
    response = await async_client.put("/users/me", json=overflow_body, headers=headers)

    assert response.status_code == 422
    error_locations = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert {
        ("body", "full_name"),
        ("body", "telegram"),
        ("body", "profile_detail", "department"),
        ("body", "institute"),
        ("body", "education_path", "program"),
    } <= error_locations

    after_response = await async_client.get("/users/me", headers=headers)
    assert after_response.status_code == 200
    assert after_response.json() == before_body


@pytest.mark.asyncio
async def test_full_name_column_limit_counts_unicode_codepoints_without_normalizing(
    async_client, user_factory, db_session
):
    password = f"Profile{secrets.token_hex(12)}Aa1!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    user_id = user.id
    headers = await _login(async_client, user.email, password)

    astral_name = "🙂" * 256
    assert len(astral_name) == 256
    astral_response = await async_client.put(
        "/users/me", json={"full_name": astral_name}, headers=headers
    )
    assert astral_response.status_code == 200
    assert astral_response.json()["full_name"] == astral_name

    decomposed_name = "e\u0301" * 128
    assert len(decomposed_name) == 256
    assert unicodedata.normalize("NFC", decomposed_name) != decomposed_name
    decomposed_response = await async_client.put(
        "/users/me", json={"full_name": decomposed_name}, headers=headers
    )
    assert decomposed_response.status_code == 200
    assert decomposed_response.json()["full_name"] == decomposed_name

    overflow_response = await async_client.put(
        "/users/me",
        json={"full_name": decomposed_name + "x"},
        headers=headers,
    )
    assert overflow_response.status_code == 422
    unchanged_response = await async_client.get("/users/me", headers=headers)
    assert unchanged_response.status_code == 200
    assert unchanged_response.json()["full_name"] == decomposed_name

    db_session.expire_all()
    stored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == user_id)
    )
    assert stored_profile is not None
    assert stored_profile.full_name == decomposed_name
