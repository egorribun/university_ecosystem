"""Unit tests for GraphQL permission classes.

The two classes — ``IsAuthenticated`` and ``IsAdmin`` — gate every
authenticated GraphQL field. They must fail-closed under every
non-trivial failure mode (missing checker, SpiceDB outage, unexpected
exception) so a misconfigured deployment cannot silently expose data.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.rbac import SpiceDBUnavailableError
from app.graphql.permissions import IsAdmin, IsAuthenticated


def _info(
    *,
    is_authenticated: bool = True,
    current_user_id: uuid.UUID | None = None,
    checker: Any = None,
) -> SimpleNamespace:
    """Build a Strawberry-shaped ``Info`` mock with our context fields."""
    user = SimpleNamespace(id=current_user_id) if current_user_id is not None else None
    context = SimpleNamespace(
        is_authenticated=is_authenticated,
        current_user=user,
        checker=checker,
    )
    return SimpleNamespace(context=context)


# ── 1. IsAuthenticated — bare authentication gate ───────────────────────────


class TestIsAuthenticated:
    def test_message_is_stable(self) -> None:
        """The message string is part of the GraphQL error contract."""
        assert IsAuthenticated.message == "Authentication required"

    def test_authenticated_user_passes(self) -> None:
        info = _info(is_authenticated=True, current_user_id=uuid.uuid4())
        assert IsAuthenticated().has_permission(None, info) is True

    def test_anonymous_user_rejected(self) -> None:
        info = _info(is_authenticated=False)
        assert IsAuthenticated().has_permission(None, info) is False

    def test_does_not_inspect_current_user(self) -> None:
        """The class delegates entirely to ``is_authenticated`` — no other state read."""
        info = _info(is_authenticated=True, current_user_id=None)
        # Even with current_user=None, is_authenticated=True is enough.
        assert IsAuthenticated().has_permission(None, info) is True


# ── 2. IsAdmin — SpiceDB-backed admin gate (fail-closed) ────────────────────


class TestIsAdminFailClosedOnEdges:
    def test_message_is_stable(self) -> None:
        assert IsAdmin.message == "Admin access required"

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self) -> None:
        info = _info(is_authenticated=False)
        assert await IsAdmin().has_permission(None, info) is False

    @pytest.mark.asyncio
    async def test_authenticated_but_no_user_rejected(self) -> None:
        """Authenticated flag without a user object is rejected (defence-in-depth)."""
        info = _info(is_authenticated=True, current_user_id=None)
        # current_user is None — fail closed.
        assert await IsAdmin().has_permission(None, info) is False

    @pytest.mark.asyncio
    async def test_missing_checker_fails_closed(self) -> None:
        """Without a PermissionChecker injected, IsAdmin denies access."""
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=None,
        )
        assert await IsAdmin().has_permission(None, info) is False


class TestIsAdminWithCheckerOutcomes:
    @pytest.mark.asyncio
    async def test_checker_grants_admin(self) -> None:
        """If the checker says the user is admin, the gate opens."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(return_value=True)
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=checker,
        )
        assert await IsAdmin().has_permission(None, info) is True
        checker.check_admin.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_checker_denies_admin(self) -> None:
        """If the checker says the user is not admin, the gate stays closed."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(return_value=False)
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=checker,
        )
        assert await IsAdmin().has_permission(None, info) is False

    @pytest.mark.asyncio
    async def test_checker_called_with_string_user_id(self) -> None:
        """``check_admin`` receives ``str(user.id)`` — UUID stringification is explicit."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(return_value=True)
        user_id = uuid.uuid4()
        info = _info(
            is_authenticated=True,
            current_user_id=user_id,
            checker=checker,
        )
        await IsAdmin().has_permission(None, info)
        checker.check_admin.assert_awaited_once_with(str(user_id))

    @pytest.mark.asyncio
    async def test_truthy_non_bool_return_coerced_to_bool(self) -> None:
        """A truthy non-bool (e.g. 1) is coerced — the function must return bool."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(return_value=1)
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=checker,
        )
        result = await IsAdmin().has_permission(None, info)
        assert result is True


class TestIsAdminFailClosedOnExceptions:
    @pytest.mark.asyncio
    async def test_spicedb_unavailable_fails_closed(self) -> None:
        """SpiceDB outage → permission denied, never granted by accident."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(side_effect=SpiceDBUnavailableError("offline"))
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=checker,
        )
        assert await IsAdmin().has_permission(None, info) is False

    @pytest.mark.asyncio
    async def test_unexpected_exception_fails_closed(self) -> None:
        """Any other exception is logged-and-denied — never propagated."""
        checker = MagicMock()
        checker.check_admin = AsyncMock(side_effect=RuntimeError("unexpected"))
        info = _info(
            is_authenticated=True,
            current_user_id=uuid.uuid4(),
            checker=checker,
        )
        # The fail-closed branch swallows the error — no raise.
        assert await IsAdmin().has_permission(None, info) is False
