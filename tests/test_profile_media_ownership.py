from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

import app.services.user.logic as user_logic
import app.utils.files as file_utils
from app.services.storage import S3Storage, StaticFSStorage

_OWNER = UUID("0190d1c2-6c1a-7b3d-8e4f-1234567890ab")
_FOREIGN_OWNER = UUID("0190d1c2-6c1a-7b3d-8e4f-abcdefabcdef")


def _profile_key(owner_id: UUID, kind: str) -> str:
    folder = "avatars" if kind == "avatar" else "covers"
    filename = file_utils._gen_name(f"user_{owner_id}_{kind}", ".webp")
    return f"{folder}/{filename}"


@pytest.mark.asyncio
async def test_s3_deletes_a_parsed_current_owner_key_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = S3Storage(
        bucket="profile-media", base_url="https://media.example.test/static"
    )
    file_url = f"{storage.base_url}/{_profile_key(_OWNER, 'avatar')}"
    delete = AsyncMock()
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)
    monkeypatch.setattr(user_logic, "delete_static_file", delete)

    deleted = await user_logic.delete_owned_profile_media(
        file_url, owner_id=_OWNER, media_kind="avatar"
    )

    assert deleted is True
    delete.assert_awaited_once_with(file_url)


@pytest.mark.asyncio
async def test_s3_preserves_a_parsed_foreign_owner_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = S3Storage(
        bucket="profile-media", base_url="https://media.example.test/static"
    )
    file_url = f"{storage.base_url}/{_profile_key(_FOREIGN_OWNER, 'avatar')}"
    delete = AsyncMock()
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)
    monkeypatch.setattr(user_logic, "delete_static_file", delete)

    deleted = await user_logic.delete_owned_profile_media(
        file_url, owner_id=_OWNER, media_kind="avatar"
    )

    assert deleted is False
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_owner_avatar_is_preserved_when_requested_as_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StaticFSStorage(tmp_path, base_url="/static")
    key = _profile_key(_OWNER, "avatar")
    target = tmp_path / key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"profile image")
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)

    deleted = await user_logic.delete_owned_profile_media(
        f"{storage.base_url}/{key}", owner_id=_OWNER, media_kind="cover"
    )

    assert deleted is False
    assert target.is_file()


@pytest.mark.asyncio
async def test_unknown_backend_cannot_authorize_profile_media_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delete = AsyncMock()
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(user_logic, "delete_static_file", delete)

    deleted = await user_logic.delete_owned_profile_media(
        f"/static/{_profile_key(_OWNER, 'avatar')}",
        owner_id=_OWNER,
        media_kind="avatar",
    )

    assert deleted is False
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_static_filesystem_deletes_the_exact_owned_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StaticFSStorage(tmp_path, base_url="/static")
    key = _profile_key(_OWNER, "cover")
    file_url = await storage.save_file(key, b"profile image")
    target = tmp_path / key
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)

    deleted = await user_logic.delete_owned_profile_media(
        file_url, owner_id=_OWNER, media_kind="cover"
    )

    assert deleted is True
    assert not target.exists()


@pytest.mark.asyncio
async def test_s3_rejects_traversal_and_non_exact_keys_before_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = S3Storage(
        bucket="profile-media", base_url="https://media.example.test/static"
    )
    filename = _profile_key(_OWNER, "avatar").split("/", maxsplit=1)[1]
    urls = (
        f"{storage.base_url}/avatars/../avatars/{filename}",
        f"{storage.base_url}/avatars//{filename}",
        f"{storage.base_url}/avatars/nested/{filename}",
    )
    delete = AsyncMock()
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)
    monkeypatch.setattr(user_logic, "delete_static_file", delete)

    results = [
        await user_logic.delete_owned_profile_media(
            file_url, owner_id=_OWNER, media_kind="avatar"
        )
        for file_url in urls
    ]

    assert storage._extract_key(urls[0]) is None
    assert storage._extract_key(urls[1]) is None
    assert results == [False, False, False]
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_static_filesystem_preserves_a_traversal_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StaticFSStorage(tmp_path, base_url="/static")
    key = _profile_key(_OWNER, "avatar")
    target = tmp_path / key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"profile image")
    traversal_url = f"{storage.base_url}/avatars/../{key}"
    monkeypatch.setattr(file_utils, "_get_storage_backend", lambda: storage)

    deleted = await user_logic.delete_owned_profile_media(
        traversal_url, owner_id=_OWNER, media_kind="avatar"
    )

    assert storage._extract_relative_path(traversal_url) is None
    assert deleted is False
    assert target.is_file()
