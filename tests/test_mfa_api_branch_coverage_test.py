from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.auth.mfa import (
    confirm_totp_enrollment,
    delete_totp_enrollment,
    disable_email_mfa_endpoint,
    request_step_up,
)
from app.auth.schemas import TotpEnrollmentConfirmIn


@pytest.mark.asyncio
@patch("app.auth.mfa.complete_totp_enrollment", new_callable=AsyncMock)
async def test_confirm_totp_enrollment_failure(mock_complete):
    mock_complete.side_effect = HTTPException(status_code=400)

    payload = MagicMock(
        spec=TotpEnrollmentConfirmIn, enrollment_id="123", code="123456"
    )
    db = AsyncMock()
    enrollment = MagicMock(user_id="user_123")
    db.get.return_value = enrollment
    audit = MagicMock()
    user = MagicMock(id="user_123")

    request = MagicMock()
    import typing

    async def mock_get(dep, *a, **kw):
        if dep is typing.Any:
            return db
        if "AuditService" in str(dep):
            return audit

    request.state.dishka_container.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(
            payload=payload, request=request, db=db, user=user
        )
    assert exc.value.status_code == 400
    audit.log.assert_called_with(
        "auth.mfa.totp.enroll_failure",
        request,
        user_id="user_123",
        reason="invalid_code",
        extra={"enrollment_id": "123"},
    )


@pytest.mark.asyncio
async def test_confirm_totp_enrollment_not_found():
    from app.auth.schemas import TotpEnrollmentConfirmIn

    # 1. Enrollment is None
    payload = MagicMock(
        spec=TotpEnrollmentConfirmIn, enrollment_id="123", code="123456"
    )
    db = AsyncMock()
    db.get.return_value = None

    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        return db

    request.state.dishka_container.get.side_effect = mock_get

    user = MagicMock(id="user_123")

    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(
            payload=payload, request=request, db=db, user=user
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Enrollment not found"

    # 2. Enrollment belongs to different user
    enrollment = MagicMock(user_id="user_other")
    db.get.return_value = enrollment
    with pytest.raises(HTTPException) as exc:
        await confirm_totp_enrollment(
            payload=payload, request=request, db=db, user=user
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Enrollment not found"


@pytest.mark.asyncio
async def test_confirm_totp_rollback_does_not_publish_redis_revocations():
    payload = MagicMock(
        spec=TotpEnrollmentConfirmIn, enrollment_id="123", code="123456"
    )
    db = AsyncMock()
    db.get.return_value = MagicMock(user_id="user_123")
    db.commit.side_effect = RuntimeError("commit failed")
    audit = MagicMock()
    user = MagicMock(id="user_123")
    request = MagicMock()
    request.state.active_session = MagicMock(id="session_123")

    async def mock_get(dep, *a, **kw):
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)
    with (
        patch(
            "app.api.auth.mfa.mfa.complete_totp_enrollment",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.api.auth.mfa.mfa.refresh_user_mfa_preferences", AsyncMock()),
        patch(
            "app.api.auth.mfa.mfa.revoke_sibling_sessions_for_factor_change",
            AsyncMock(return_value=[MagicMock()]),
        ),
        patch("app.api.auth.mfa.mfa.record_mfa_success", AsyncMock()),
        patch(
            "app.api.auth.mfa.mfa.publish_mfa_session_revocations", AsyncMock()
        ) as publish,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            await confirm_totp_enrollment(
                payload=payload,
                request=request,
                db=db,
                user=user,
            )

    db.rollback.assert_awaited_once()
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_disable_email_commit_failure_rolls_back_without_redis_publish():
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("commit failed")
    request = MagicMock()
    user = MagicMock(id="user_123")
    pending = [MagicMock()]
    with (
        patch(
            "app.api.auth.mfa.mfa.disable_email_mfa",
            AsyncMock(return_value=pending),
        ),
        patch(
            "app.api.auth.mfa.mfa.publish_mfa_session_revocations", AsyncMock()
        ) as publish,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            await disable_email_mfa_endpoint.__dishka_orig_func__(
                request, db, MagicMock(), user
            )

    db.rollback.assert_awaited_once()
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_disable_totp_publishes_revocations_only_after_commit():
    events: list[str] = []
    db = AsyncMock()
    db.commit.side_effect = lambda: events.append("commit")
    request = MagicMock()
    user = MagicMock(id="user_123", mfa_default_method=None, mfa_required=False)
    pending = [MagicMock()]

    async def publish(_pending):
        events.append("publish")

    with (
        patch(
            "app.api.auth.mfa.mfa.disable_totp",
            AsyncMock(return_value=(1, pending)),
        ),
        patch("app.api.auth.mfa.mfa.refresh_user_mfa_preferences", AsyncMock()),
        patch(
            "app.api.auth.mfa.mfa.publish_mfa_session_revocations",
            AsyncMock(side_effect=publish),
        ),
    ):
        await delete_totp_enrollment.__dishka_orig_func__(
            "enrollment_123", request, db, MagicMock(), None, user
        )

    assert events == ["commit", "publish"]


@pytest.mark.asyncio
async def test_disable_totp_commit_failure_rolls_back_without_redis_publish():
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("commit failed")
    request = MagicMock()
    user = MagicMock(id="user_123", mfa_default_method=None, mfa_required=False)
    pending = [MagicMock()]

    with (
        patch(
            "app.api.auth.mfa.mfa.disable_totp",
            AsyncMock(return_value=(1, pending)),
        ),
        patch("app.api.auth.mfa.mfa.refresh_user_mfa_preferences", AsyncMock()),
        patch(
            "app.api.auth.mfa.mfa.publish_mfa_session_revocations", AsyncMock()
        ) as publish,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            await delete_totp_enrollment.__dishka_orig_func__(
                "enrollment_123", request, db, MagicMock(), None, user
            )

    db.rollback.assert_awaited_once()
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_step_up_missing_interactive_factor():
    db = AsyncMock()
    audit = MagicMock()
    login_service = AsyncMock()
    login_service._resolve_mfa_capabilities.return_value = {}

    request = MagicMock()
    request.state.active_session = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "LoginService" in str(dep):
            return login_service
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)

    user = MagicMock(id="user_123")

    with pytest.raises(HTTPException) as exc:
        await request_step_up(request=request, user=user)
    assert exc.value.status_code == 400


from app.api.auth.mfa import generate_recovery_codes_endpoint


@pytest.mark.asyncio
@patch("app.api.auth.mfa.mfa.generate_recovery_codes", new_callable=AsyncMock)
async def test_generate_recovery_codes_endpoint(mock_generate):
    mock_generate.return_value = ["code1", "code2"]

    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()

    async def mock_get(dep, *a, **kw):
        if "AuditService" in str(dep):
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=mock_get)
    user = MagicMock(id="user_123")

    res = await generate_recovery_codes_endpoint(request=request, db=db, user=user)
    assert res.codes == ["code1", "code2"]
    db.commit.assert_awaited_once()
    audit.log.assert_called_once()
