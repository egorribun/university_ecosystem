"""Behavioral closure tests for MFA relationship loading."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models import user_loaders


class _SlotUser:
    __slots__ = ()


@pytest.mark.asyncio
async def test_mfa_loader_handles_none_and_idempotent_users():
    db = AsyncMock()
    cached = SimpleNamespace(_mfa_loaded=True)

    assert await user_loaders.ensure_mfa_relationships_loaded(db, None) is None
    assert await user_loaders.ensure_mfa_relationships_loaded(db, cached) is cached
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_mfa_loader_returns_non_orm_object_when_inspect_fails():
    db = AsyncMock()
    value = object()

    with patch.object(user_loaders, "inspect", side_effect=RuntimeError("not ORM")):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, value) is value

    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_mfa_loader_returns_when_inspection_has_no_state():
    db = AsyncMock()
    value = SimpleNamespace()

    with patch.object(user_loaders, "inspect", return_value=None):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, value) is value

    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_mfa_loader_refreshes_only_unloaded_known_relationships():
    db = AsyncMock()
    value = SimpleNamespace()
    state = SimpleNamespace(unloaded={"totp_enrollments", "profile", "unknown"})

    with patch.object(user_loaders, "inspect", return_value=state):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, value) is value

    db.refresh.assert_awaited_once_with(
        value, attribute_names=["totp_enrollments", "profile"]
    )
    assert value._mfa_loaded is True


@pytest.mark.asyncio
async def test_mfa_loader_explicitly_refreshes_noload_relationships():
    db = AsyncMock()
    value = SimpleNamespace()
    state = SimpleNamespace(
        unloaded=set(),
        mapper=SimpleNamespace(
            relationships={
                "totp_enrollments": SimpleNamespace(lazy="noload"),
                "profile": SimpleNamespace(lazy="joined"),
            }
        ),
    )

    with patch.object(user_loaders, "inspect", return_value=state):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, value) is value

    db.refresh.assert_awaited_once_with(value, attribute_names=["totp_enrollments"])
    assert value._mfa_loaded is True


@pytest.mark.asyncio
async def test_mfa_loader_marks_loaded_without_refresh_and_handles_slots():
    db = AsyncMock()
    value = SimpleNamespace()
    state = SimpleNamespace(unloaded=set())

    with patch.object(user_loaders, "inspect", return_value=state):
        assert await user_loaders.ensure_mfa_relationships_loaded(db, value) is value

    db.refresh.assert_not_awaited()
    assert value._mfa_loaded is True

    slot_value = _SlotUser()
    with patch.object(user_loaders, "inspect", return_value=state):
        assert (
            await user_loaders.ensure_mfa_relationships_loaded(db, slot_value)
            is slot_value
        )
