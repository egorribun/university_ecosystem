from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.utils.files as file_utils
from app.services.user.logic import delete_static_file


@pytest.mark.asyncio
async def test_delete_static_file_delegates_to_file_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the user-profile file cleanup wrapper mapped in mutmut."""

    backend_delete = AsyncMock()
    monkeypatch.setattr(file_utils, "delete_static_file", backend_delete)

    await delete_static_file("avatars/user.png")

    backend_delete.assert_awaited_once_with("avatars/user.png")
