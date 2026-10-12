"""Closure tests for cover media operations and rollback cleanup."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

import app.utils.files as file_utils
from app.core.exceptions.domain import EntityNotFound
from app.services.storage import StaticFSStorage
from app.services.user.media_service import UserMediaService


def _uow(user):
    uow = MagicMock()
    uow.users = MagicMock()
    uow.users.get_orm_for_update_with_relations = AsyncMock(return_value=user)
    uow.users._to_dto.return_value = SimpleNamespace(id=user.id) if user else None
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    return uow


def _upload() -> MagicMock:
    return MagicMock(spec=UploadFile)


@pytest.mark.asyncio
async def test_upload_cover_success_without_old_cover():
    user = SimpleNamespace(id=uuid4(), profile=SimpleNamespace(cover_url=None))
    uow = _uow(user)

    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value="new-cover"),
        ),
        patch("app.services.user.media_service.update_user_attributes") as update,
    ):
        result = await UserMediaService(uow).upload_cover(user.id, _upload())

    assert result.id == user.id
    update.assert_called_once_with(user, {"cover_url": "new-cover"})
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_avatar_success_without_old_avatar():
    user = SimpleNamespace(id=uuid4(), profile=SimpleNamespace(avatar_url=None))
    uow = _uow(user)

    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value="new-avatar"),
        ),
        patch("app.services.user.media_service.update_user_attributes") as update,
    ):
        result = await UserMediaService(uow).upload_avatar(user.id, _upload())

    assert result.id == user.id
    update.assert_called_once_with(user, {"avatar_url": "new-avatar"})


@pytest.mark.asyncio
async def test_upload_avatar_rolls_back_and_deletes_new_file_on_failure():
    user = SimpleNamespace(id=uuid4(), profile=None)
    uow = _uow(user)
    delete = AsyncMock()

    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value="new-avatar"),
        ),
        patch("app.services.user.media_service.delete_static_file", new=delete),
        patch(
            "app.services.user.media_service.update_user_attributes",
            side_effect=RuntimeError("update failed"),
        ),
    ):
        with pytest.raises(RuntimeError):
            await UserMediaService(uow).upload_avatar(user.id, _upload())

    uow.rollback.assert_awaited_once()
    delete.assert_awaited_once_with("new-avatar", owner_id=user.id, media_kind="avatar")


@pytest.mark.asyncio
async def test_upload_cover_removes_old_cover_and_cleans_up_on_failure():
    user = SimpleNamespace(id=uuid4(), profile=SimpleNamespace(cover_url="old-cover"))
    uow = _uow(user)
    delete = AsyncMock()

    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value="new-cover"),
        ),
        patch("app.services.user.media_service.delete_static_file", new=delete),
        patch(
            "app.services.user.media_service.update_user_attributes",
            side_effect=RuntimeError("commit preparation failed"),
        ),
    ):
        with pytest.raises(RuntimeError):
            await UserMediaService(uow).upload_cover(user.id, _upload())

    assert delete.await_args_list[0].args == ("old-cover",)
    assert delete.await_args_list[0].kwargs == {
        "owner_id": user.id,
        "media_kind": "cover",
    }
    assert delete.await_args_list[1].args == ("new-cover",)
    assert delete.await_args_list[1].kwargs == {
        "owner_id": user.id,
        "media_kind": "cover",
    }
    uow.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_cover_success_and_avatar_not_found():
    user = SimpleNamespace(id=uuid4(), profile=SimpleNamespace(cover_url="old-cover"))
    uow = _uow(user)
    with (
        patch(
            "app.services.user.media_service.delete_static_file", new=AsyncMock()
        ) as delete,
        patch("app.services.user.media_service.update_user_attributes") as update,
    ):
        result = await UserMediaService(uow).delete_cover(user.id)

    assert result.id == user.id
    delete.assert_awaited_once_with("old-cover", owner_id=user.id, media_kind="cover")
    update.assert_called_once_with(user, {"cover_url": None})

    missing_uow = _uow(None)
    with pytest.raises(EntityNotFound):
        await UserMediaService(missing_uow).upload_cover(uuid4(), _upload())
    with pytest.raises(EntityNotFound):
        await UserMediaService(missing_uow).delete_avatar(uuid4())
    with pytest.raises(EntityNotFound):
        await UserMediaService(missing_uow).delete_cover(uuid4())


@pytest.mark.asyncio
async def test_delete_avatar_and_cover_without_existing_files():
    user = SimpleNamespace(
        id=uuid4(), profile=SimpleNamespace(avatar_url=None, cover_url=None)
    )
    uow = _uow(user)
    with (
        patch(
            "app.services.user.media_service.delete_static_file", new=AsyncMock()
        ) as delete,
        patch("app.services.user.media_service.update_user_attributes"),
    ):
        await UserMediaService(uow).delete_avatar(user.id)
        await UserMediaService(uow).delete_cover(user.id)

    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_avatar_paths_handle_missing_and_existing_avatar_files():
    missing_uow = _uow(None)
    with pytest.raises(EntityNotFound):
        await UserMediaService(missing_uow).upload_avatar(uuid4(), _upload())

    user = SimpleNamespace(id=uuid4(), profile=SimpleNamespace(avatar_url="old-avatar"))
    uow = _uow(user)
    delete = AsyncMock()
    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value="new-avatar"),
        ),
        patch("app.services.user.media_service.delete_static_file", new=delete),
        patch("app.services.user.media_service.update_user_attributes"),
    ):
        await UserMediaService(uow).upload_avatar(user.id, _upload())
        await UserMediaService(uow).delete_avatar(user.id)

    assert delete.await_args_list[0].args == ("old-avatar",)
    assert delete.await_args_list[1].args == ("old-avatar",)


@pytest.mark.asyncio
@pytest.mark.parametrize("media_kind", ["avatar", "cover"])
@pytest.mark.parametrize("asset_owner", ["current", "foreign", "legacy"])
async def test_media_replacement_deletes_only_the_current_users_asset(
    tmp_path, monkeypatch, media_kind, asset_owner
):
    owner_id = uuid4()
    stored_owner_id = owner_id if asset_owner == "current" else uuid4()
    directory = "avatars" if media_kind == "avatar" else "covers"
    profile_field = f"{media_kind}_url"
    token = "a" * 32
    relative_path = (
        f"{directory}/another-users-file.png"
        if asset_owner == "legacy"
        else f"{directory}/user_{stored_owner_id}_{media_kind}_{token}.png"
    )
    file_url = f"/static/{relative_path}"
    asset_path = tmp_path / relative_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"profile media")

    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: backend)
    user = SimpleNamespace(
        id=owner_id, profile=SimpleNamespace(**{profile_field: file_url})
    )
    uow = _uow(user)
    new_file_url = f"/static/{directory}/user_{owner_id}_{media_kind}_{'b' * 32}.png"

    with (
        patch(
            "app.services.user.media_service.save_upload",
            new=AsyncMock(return_value=new_file_url),
        ),
        patch("app.services.user.media_service.update_user_attributes"),
    ):
        upload_method = getattr(UserMediaService(uow), f"upload_{media_kind}")
        await upload_method(user.id, _upload())

    assert asset_path.exists() == (asset_owner != "current")
