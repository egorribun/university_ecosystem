"""Closure tests for MFA relationship loading safeguards."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models import user_loaders


@pytest.mark.asyncio
async def test_ensure_mfa_relationships_loaded_handles_none_and_cached_user():
    db = AsyncMock()
    assert await user_loaders.ensure_mfa_relationships_loaded(db, None) is None

    cached = SimpleNamespace(_mfa_loaded=True)
    assert await user_loaders.ensure_mfa_relationships_loaded(db, cached) is cached
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_mfa_relationships_loaded_refreshes_unloaded_relationships():
    db = AsyncMock()
    user = SimpleNamespace()
    state = SimpleNamespace(
        unloaded={"preferences", "profile", "not_a_user_relationship"}
    )

    with patch.object(user_loaders, "inspect", return_value=state):
        result = await user_loaders.ensure_mfa_relationships_loaded(db, user)

    assert result is user
    db.refresh.assert_awaited_once_with(
        user, attribute_names=["preferences", "profile"]
    )
    assert user._mfa_loaded is True


@pytest.mark.asyncio
async def test_ensure_mfa_relationships_loaded_skips_refresh_when_state_is_complete():
    db = AsyncMock()
    user = SimpleNamespace()
    state = SimpleNamespace(unloaded=set())

    with patch.object(user_loaders, "inspect", return_value=state):
        result = await user_loaders.ensure_mfa_relationships_loaded(db, user)

    assert result is user
    db.refresh.assert_not_awaited()
    assert user._mfa_loaded is True


@pytest.mark.asyncio
async def test_ensure_mfa_relationships_loaded_handles_inspection_failure_and_none_state():
    db = AsyncMock()
    first = SimpleNamespace()
    with patch.object(user_loaders, "inspect", side_effect=RuntimeError("not ORM")):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, first) is first

    second = SimpleNamespace()
    with patch.object(user_loaders, "inspect", return_value=None):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, second) is second


@pytest.mark.asyncio
async def test_ensure_mfa_relationships_loaded_tolerates_frozen_objects():
    class Frozen:
        __slots__ = ()

    db = AsyncMock()
    user = Frozen()
    state = SimpleNamespace(unloaded=set())

    with patch.object(user_loaders, "inspect", return_value=state):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, user) is user

    db.refresh.assert_not_awaited()
