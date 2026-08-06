"""Negative-path endpoint coverage for stories API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import stories


@pytest.mark.asyncio
async def test_update_story_translates_missing_record_to_http_error():
    service = MagicMock()
    service.update_story = AsyncMock(side_effect=ValueError("missing"))

    with (
        patch.object(stories, "require_admin"),
        patch.object(stories, "resolve_locale", return_value="en"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stories.update_story(
                uuid4(),
                MagicMock(),
                data=MagicMock(),
                service=service,
                user=SimpleNamespace(id=uuid4(), role="admin"),
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_story_translates_false_result_to_http_error():
    service = MagicMock()
    service.delete_story = AsyncMock(return_value=False)

    with (
        patch.object(stories, "require_admin"),
        patch.object(stories, "resolve_locale", return_value="en"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stories.delete_story(
                uuid4(),
                MagicMock(),
                service=service,
                user=SimpleNamespace(id=uuid4(), role="admin"),
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_story_cover_scans_and_saves_file():
    upload = SimpleNamespace(size=123, filename="cover.png")

    with (
        patch.object(stories, "require_admin"),
        patch.object(stories, "resolve_locale", return_value="en"),
        patch.object(stories, "scan_for_malware", new=AsyncMock()) as scan,
        patch.object(
            stories, "save_upload", new=AsyncMock(return_value="/covers/cover.png")
        ) as save,
    ):
        result = await stories.upload_story_cover(
            file=upload,
            request=MagicMock(),
            user=SimpleNamespace(id=uuid4(), role="admin"),
        )

    assert result == {"url": "/covers/cover.png"}
    scan.assert_awaited_once_with(upload, locale="en", size_bytes=123)
    save.assert_awaited_once_with(upload, "story_covers", "stories", locale="en")
