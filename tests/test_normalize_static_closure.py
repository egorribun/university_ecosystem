"""Closure tests for static filename normalization and URL migrations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.management import normalize_static


def test_normalize_path_skips_directories_and_already_safe_names(tmp_path: Path):
    directory = tmp_path / "directory"
    directory.mkdir()
    assert normalize_static._normalize_path(directory) is None

    safe = tmp_path / "safe_image.jpg"
    safe.write_bytes(b"image")
    assert normalize_static._normalize_path(safe) is None


def test_normalize_path_normalizes_prefix_and_avoids_collision(tmp_path: Path):
    directory = tmp_path / "avatars"
    directory.mkdir()
    source = directory / "Unsafe_file.png"
    source.write_bytes(b"source")

    is_case_insensitive = (directory / "unsafe_file.png").exists()
    if not is_case_insensitive:
        (directory / "unsafe_file.png").write_bytes(b"existing")

    result = normalize_static._normalize_path(source)

    if is_case_insensitive:
        assert result == (
            directory / "unsafe_file.png",
            "/static/avatars/unsafe_file.png",
        )
    else:
        assert result == (
            directory / "unsafe_file-1.png",
            "/static/avatars/unsafe_file-1.png",
        )


def test_is_same_file_returns_false_for_filesystem_errors():
    source = MagicMock()
    source.samefile.side_effect = OSError("filesystem race")
    assert normalize_static._is_same_file(source, MagicMock()) is False


def test_normalize_path_advances_through_multiple_collisions(tmp_path: Path):
    directory = tmp_path / "avatars"
    directory.mkdir()
    source = directory / "Unsafe_file.png"
    source.write_bytes(b"source")
    (directory / "unsafe_file.png").write_bytes(b"first")
    (directory / "unsafe_file-1.png").write_bytes(b"second")

    with patch.object(normalize_static, "_is_same_file", return_value=False):
        result = normalize_static._normalize_path(source)

    assert result == (
        directory / "unsafe_file-2.png",
        "/static/avatars/unsafe_file-2.png",
    )


def test_rename_files_handles_missing_subdirs_and_both_mappings(tmp_path: Path):
    avatars = tmp_path / "avatars"
    avatars.mkdir(exist_ok=True)
    covers = tmp_path / "covers"
    covers.mkdir(exist_ok=True)
    for stale in list(avatars.glob("*")):
        if stale.is_file():
            stale.unlink()
    for stale in list(covers.glob("*")):
        if stale.is_file():
            stale.unlink()

    (avatars / "Bad_avatar.jpg").write_bytes(b"avatar")
    (avatars / "safe.jpg").write_bytes(b"safe")
    (avatars / "nested").mkdir(exist_ok=True)
    (covers / "Cover_image.jpg").write_bytes(b"cover")

    avatar_mapping, cover_mapping = normalize_static._rename_files(tmp_path)

    assert avatar_mapping == {
        "/static/avatars/Bad_avatar.jpg": "/static/avatars/bad_avatar.jpg"
    }
    assert cover_mapping == {
        "/static/covers/Cover_image.jpg": "/static/covers/cover_image.jpg"
    }
    assert (avatars / "bad_avatar.jpg").exists()
    assert (covers / "cover_image.jpg").exists()


def test_rename_files_skips_missing_static_subdirectories(tmp_path: Path):
    assert normalize_static._rename_files(tmp_path) == ({}, {})


@pytest.mark.asyncio
async def test_update_column_skips_empty_mapping_and_executes_updates():
    session = AsyncMock()

    await normalize_static._update_column(session, {}, "avatar_url")
    session.execute.assert_not_awaited()

    await normalize_static._update_column(
        session,
        {"/static/avatars/old.jpg": "/static/avatars/new.jpg"},
        "avatar_url",
    )
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_returns_without_db_work_when_assets_are_normalized():
    with (
        patch.object(normalize_static, "_rename_files", return_value=({}, {})),
        patch.object(normalize_static, "async_session") as session_factory,
    ):
        await normalize_static.main()

    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_main_updates_avatar_and_cover_urls_after_renaming(tmp_path: Path):
    session = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=session)
    transaction.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=transaction)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)

    avatars = {"/static/avatars/old.jpg": "/static/avatars/new.jpg"}
    covers = {"/static/covers/old.jpg": "/static/covers/new.jpg"}
    with (
        patch.object(normalize_static, "_rename_files", return_value=(avatars, covers)),
        patch.object(normalize_static, "async_session", return_value=session_context),
        patch.object(normalize_static, "_update_column", new=AsyncMock()) as update,
    ):
        await normalize_static.main()

    assert update.await_args_list[0].args[1:] == (avatars, "avatar_url")
    assert update.await_args_list[1].args[1:] == (covers, "cover_url")
