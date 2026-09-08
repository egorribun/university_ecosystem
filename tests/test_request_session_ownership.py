"""BE-04 request session ownership regressions.

The probe uses real SQLite async engines so a passing identity assertion cannot
be produced by equal mock return values.  The route dependency assertion is
the owning S0/S3b contract: it turns red while step-up still resolves the
legacy authentication adapter and turns green when the route is migrated.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.auth import mfa as mfa_api
from app.api.deps import auth as auth_deps
from tests.helpers.request_session_probe import RequestSessionProbe


def test_step_up_auth_dependency_is_dishka_adapter() -> None:
    implementation = mfa_api.request_step_up.__dishka_orig_func__
    dependency = inspect.signature(implementation).parameters["user"].default
    adapter = getattr(auth_deps, "get_current_user_from_dishka", None)
    assert adapter is not None
    assert dependency.dependency is adapter


@pytest.mark.asyncio
async def test_real_session_probe_records_identity_and_cleanup() -> None:
    async with RequestSessionProbe() as probe:
        async with probe.request() as sessions:
            owner = await probe.execute("auth", sessions.legacy)
            same_owner = await probe.execute("handler", sessions.legacy)
            assert owner == same_owner
            probe.observation.assert_single_owner("auth", "handler")

    assert probe.observation.exits == 2
    assert probe.observation.checkouts == probe.observation.checkins


@pytest.mark.asyncio
async def test_real_probe_detects_duplicate_session_identities() -> None:
    async with RequestSessionProbe() as probe:
        async with probe.request() as sessions:
            await probe.execute("legacy_auth", sessions.legacy)
            await probe.execute("dishka_handler", sessions.dishka)
            with pytest.raises(AssertionError, match="duplicate request session"):
                probe.observation.assert_single_owner("legacy_auth", "dishka_handler")


@pytest.mark.asyncio
async def test_real_session_probe_closes_and_rolls_back_on_handler_failure() -> None:
    with pytest.raises(RuntimeError, match="handler failed"):
        async with RequestSessionProbe() as probe:
            async with probe.request() as sessions:
                await probe.execute("auth", sessions.legacy)
                raise RuntimeError("handler failed")

            raise AssertionError("request context must propagate the handler failure")

    assert probe.observation.exits == 2
    assert probe.observation.checkouts == probe.observation.checkins
    assert probe.observation.rollbacks >= 1


@pytest.mark.asyncio
async def test_probe_has_independent_session_factories() -> None:
    async with RequestSessionProbe() as probe:
        async with probe.request() as sessions:
            legacy_id = await probe.execute("legacy", sessions.legacy)
            dishka_id = await probe.execute("dishka", sessions.dishka)

    assert legacy_id != dishka_id


@pytest.mark.asyncio
async def test_dishka_adapter_forwards_the_canonical_session() -> None:
    request = MagicMock()
    db = object()
    redis_service = object()
    user = object()
    implementation = auth_deps.get_current_user_from_dishka.__dishka_orig_func__

    with patch.object(
        auth_deps, "_resolve_current_user", new=AsyncMock(return_value=user)
    ) as resolve:
        result = await implementation(request, "token", db, redis_service)

    assert result is user
    resolve.assert_awaited_once_with(request, "token", db, redis_service)


@pytest.mark.asyncio
async def test_legacy_adapter_and_dishka_adapter_share_the_same_core() -> None:
    request = MagicMock()
    db = object()
    redis_service = object()
    user = object()
    with patch.object(
        auth_deps, "_resolve_current_user", new=AsyncMock(return_value=user)
    ) as resolve:
        assert (
            await auth_deps.get_current_user(request, "token", db, redis_service)
            is user
        )

    resolve.assert_awaited_once_with(request, "token", db, redis_service)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 503])
async def test_dishka_optional_adapter_only_hides_auth_rejections(
    status_code: int,
) -> None:
    implementation = (
        auth_deps.get_current_user_optional_from_dishka.__dishka_orig_func__
    )
    request = MagicMock()
    db = object()
    redis_service = object()
    with patch.object(
        auth_deps,
        "_resolve_current_user",
        new=AsyncMock(side_effect=HTTPException(status_code=status_code)),
    ):
        if status_code == 401:
            assert await implementation(request, None, db, redis_service) is None
        else:
            with pytest.raises(HTTPException) as exc_info:
                await implementation(request, None, db, redis_service)
            assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_dishka_fresh_mfa_guard_uses_the_same_session() -> None:
    implementation = auth_deps.require_fresh_mfa_from_dishka.__dishka_orig_func__
    request = MagicMock(state=SimpleNamespace())
    user = SimpleNamespace(email_mfa_enabled_at=None)
    db = object()
    with (
        patch.object(
            auth_deps, "ensure_mfa_relationships_loaded", new=AsyncMock()
        ) as load,
        patch.object(
            auth_deps.mfa, "has_totp_enabled", new=AsyncMock(return_value=False)
        ) as has_totp,
    ):
        await implementation(request, user, db)

    load.assert_awaited_once_with(db, user)
    has_totp.assert_awaited_once_with(db, user)


@pytest.mark.asyncio
async def test_dishka_fresh_mfa_guard_enforces_when_factor_is_enabled() -> None:
    implementation = auth_deps.require_fresh_mfa_from_dishka.__dishka_orig_func__
    request = MagicMock(state=SimpleNamespace())
    user = SimpleNamespace(email_mfa_enabled_at=None)
    db = object()
    with (
        patch.object(auth_deps, "ensure_mfa_relationships_loaded", new=AsyncMock()),
        patch.object(
            auth_deps.mfa, "has_totp_enabled", new=AsyncMock(return_value=True)
        ),
        patch.object(auth_deps, "_enforce_fresh_mfa") as enforce,
    ):
        await implementation(request, user, db)

    enforce.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_step_up_route_and_login_service_share_real_session() -> None:
    """The highest-risk MFA path must keep one session through challenge setup."""

    class SessionBoundLoginService:
        def __init__(self, session: object) -> None:
            self.session = session
            self.capability_session_ids: list[int] = []
            self.challenge_session_ids: list[int] = []

        async def _resolve_mfa_capabilities(self, _user: object) -> dict[str, bool]:
            self.capability_session_ids.append(id(self.session))
            return {"totp": True, "email_otp": False}

        async def _collect_mfa_challenges(
            self,
            _user: object,
            _locale: str,
            _capabilities: dict[str, bool],
            session: object,
            **_kwargs: object,
        ) -> list[object]:
            assert getattr(session, "id", None) is not None
            self.challenge_session_ids.append(id(self.session))
            return []

    async with RequestSessionProbe() as probe:
        async with probe.request() as sessions:
            db = sessions.legacy
            request = MagicMock(
                state=SimpleNamespace(active_session=SimpleNamespace(id=uuid4()))
            )
            user = SimpleNamespace(id=uuid4(), mfa_default_method="totp")
            login_service = SessionBoundLoginService(db)
            with patch("app.core.localization.resolve_locale", return_value="en"):
                result = await mfa_api.request_step_up.__dishka_orig_func__(
                    request,
                    db,
                    MagicMock(),
                    login_service,
                    user,
                )

            assert result.default_method == "totp"
            assert login_service.capability_session_ids == [id(db)]
            assert login_service.challenge_session_ids == [id(db)]

        assert probe.observation.exits == 2
        assert probe.observation.checkouts == probe.observation.checkins
