from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.auth.login_service import LoginService

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_user_service():
    return AsyncMock()


@pytest.fixture
def mock_session_service():
    return AsyncMock()


@pytest.fixture
def mock_lockout_service():
    service = AsyncMock()
    # Default: no active lockout, 0 cleared attempts
    service.get_active_lockout.return_value = None
    service.clear_failed_attempts.return_value = 0
    service.register_failed_attempt.return_value = (None, False, 1)

    # Synchronous methods
    service.get_lockout_message = MagicMock()
    service.format_duration = MagicMock()

    return service


@pytest.fixture
def mock_audit_service():
    return MagicMock()


@pytest.fixture
def login_service(
    mock_db,
    mock_user_service,
    mock_session_service,
    mock_lockout_service,
    mock_audit_service,
):
    return LoginService(
        db=mock_db,
        user_service=mock_user_service,
        session_service=mock_session_service,
        lockout_service=mock_lockout_service,
        audit=mock_audit_service,
    )


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.headers = {"user-agent": "test-agent", "x-forwarded-for": "127.0.0.1"}
    req.client.host = "127.0.0.1"
    return req


@pytest.fixture
def mock_background_tasks():
    return MagicMock()


async def test_perform_login_success_no_mfa(
    login_service,
    mock_user_service,
    mock_request,
    mock_background_tasks,
    mock_session_service,
):
    # Setup
    email = "test@example.com"
    password = "password"
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = "$argon2id$..."  # Mock hash
    user.mfa_required = False

    mock_user_service.get_user_by_email.return_value = user

    # Mock password verification
    with patch(
        "app.services.auth.login_service.verify_and_update_password",
        return_value=(True, None),
    ):
        # Mock mfa check
        with patch.object(
            login_service, "_resolve_mfa_capabilities", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = {}
            # Mock finalization
            token_response = MagicMock()
            login_service.finalize_login = AsyncMock(return_value=token_response)

            # Execute
            result = await login_service.perform_login(
                email, password, mock_request, MagicMock(), mock_background_tasks
            )

            # Assert
            assert result == token_response
            login_service.finalize_login.assert_called_once()


async def test_perform_login_user_not_found(
    login_service, mock_user_service, mock_request, mock_background_tasks
):
    email = "unknown@example.com"
    password = "password"
    mock_user_service.get_user_by_email.return_value = None

    # Needs to handle the exception raised by _handle_invalid_user
    # The actual implementation raises HTTP 401
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await login_service.perform_login(
            email, password, mock_request, MagicMock(), mock_background_tasks
        )

    assert exc.value.status_code == 401


async def test_perform_login_locked_out(
    login_service,
    mock_user_service,
    mock_lockout_service,
    mock_request,
    mock_background_tasks,
):
    email = "locked@example.com"
    mock_user_service.get_user_by_email.return_value = MagicMock()

    # Simulate lockout
    lock_until = datetime.now(UTC) + timedelta(minutes=15)
    mock_lockout_service.get_active_lockout.return_value = lock_until
    mock_lockout_service.get_lockout_message.return_value = ("Locked", 60)
    mock_lockout_service.format_duration.return_value = "15 minutes"

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await login_service.perform_login(
            email, "password", mock_request, MagicMock(), mock_background_tasks
        )

    assert exc.value.status_code == 423


async def test_perform_login_invalid_password(
    login_service,
    mock_user_service,
    mock_request,
    mock_background_tasks,
    mock_lockout_service,
):
    email = "test@example.com"
    password = "wrongpassword"
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = "hash"

    mock_user_service.get_user_by_email.return_value = user

    with patch(
        "app.services.auth.login_service.verify_and_update_password",
        return_value=(False, None),
    ):
        # Should raise 401
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await login_service.perform_login(
                email, password, mock_request, MagicMock(), mock_background_tasks
            )
        assert exc.value.status_code == 401

    # Should register failed attempt
    mock_lockout_service.register_failed_attempt.assert_called()


async def test_perform_login_mfa_required_no_factors(
    login_service, mock_user_service, mock_request, mock_background_tasks
):
    email = "test@example.com"
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = "hash"
    user.mfa_required = True
    user.mfa_default_method = None

    mock_user_service.get_user_by_email.return_value = user

    with patch(
        "app.services.auth.login_service.verify_and_update_password",
        return_value=(True, None),
    ):
        # Mock no active factors found during resolve
        with patch.object(
            login_service, "_resolve_mfa_capabilities", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = {}
            with patch.object(
                login_service, "_collect_mfa_challenges", new_callable=AsyncMock
            ) as mock_collect:
                mock_collect.return_value = []

                from fastapi import HTTPException

                with pytest.raises(HTTPException) as exc:
                    await login_service.perform_login(
                        email,
                        "password",
                        mock_request,
                        MagicMock(),
                        mock_background_tasks,
                    )
                assert exc.value.status_code == 400


async def test_perform_login_mfa_required_success(
    login_service, mock_user_service, mock_request, mock_background_tasks
):
    email = "test@example.com"
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = "hash"
    user.mfa_required = True  # strict MFA
    user.mfa_default_method = None  # Fix mock

    mock_user_service.get_user_by_email.return_value = user

    with patch(
        "app.services.auth.login_service.verify_and_update_password",
        return_value=(True, None),
    ):
        # Mock mfa setup
        with patch.object(
            login_service, "_resolve_mfa_capabilities", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = {"totp": True}

            # Use real model
            from app.auth.schemas import MfaMethodChallengeOut

            challenge_model = MfaMethodChallengeOut(
                method="totp",
                challenge_token="token",
                challenge_expires_at=datetime.now(UTC) + timedelta(minutes=5),
                attempt_count=0,
                attempt_limit=3,
                remaining_attempts=3,
            )

            with patch.object(
                login_service, "_collect_mfa_challenges", new_callable=AsyncMock
            ) as mock_collect:
                mock_collect.return_value = [challenge_model]

                response = MagicMock()
                result = await login_service.perform_login(
                    email, "password", mock_request, response, mock_background_tasks
                )

                assert result.status == "mfa_required"
                assert response.status_code == 202


async def test_finalize_login_success(
    login_service, mock_session_service, mock_request, mock_background_tasks
):
    user = MagicMock()
    user.id = uuid4()
    user.mfa_required = False

    # Mock session creation
    session = MagicMock()
    session.jti = "jti-123"
    session.mfa_verified_at = datetime.now(UTC)
    mock_session_service.create_access_token.return_value = ("token_string", session)

    response = MagicMock()

    # Create a real UserOut object to return
    from app.schemas.schemas import UserOut

    real_user_out = UserOut(id=user.id, email="test@example.com", is_active=True)

    # Bypass UserOut validation by returning our pre-made object
    with patch(
        "app.services.auth.login_service.schemas.UserOut.model_validate"
    ) as mock_validate:
        mock_validate.return_value = real_user_out

        # Mock Redis session service (patch at source)
        with patch("app.services.auth.redis_session.RedisSessionService") as MockRedis:
            redis_instance = MockRedis.return_value
            redis_instance.create_session = AsyncMock()

            # Execute
            result = await login_service.finalize_login(
                user, mock_request, response, mock_background_tasks, mfa_completed=True
            )

            assert result.access_token == "token_string"
            assert result.user.id == user.id

            # Verify cookie set
            response.set_cookie.assert_called()
            args, kwargs = response.set_cookie.call_args
            assert args[0] == "access_token_v2"
            assert args[1] == "token_string"
            assert kwargs["httponly"] is True


async def test_collect_mfa_challenges_totp_flow(login_service):
    user = MagicMock()
    user.id = uuid4()

    capabilities = {"totp": True, "webauthn": False}

    with patch(
        "app.services.auth.login_service.mfa.start_totp_verification",
        new_callable=AsyncMock,
    ) as mock_start:
        challenge = MagicMock()
        challenge.token = "auth-token"
        challenge.expires_at = datetime.now(UTC)
        mock_start.return_value = challenge

        with patch(
            "app.services.auth.login_service.mfa.describe_challenge_attempts",
            return_value=(0, 3, 3),
        ):
            challenges = await login_service._collect_mfa_challenges(
                user, "en", capabilities
            )

            assert len(challenges) == 1
            assert challenges[0].method == "totp"
            assert challenges[0].challenge_token == "auth-token"
            assert challenges[0].challenge_expires_at == challenge.expires_at


async def test_resolve_mfa_capabilities(login_service, mock_db):
    user = MagicMock()
    user.id = uuid4()
    user.mfa_default_method = None

    # Mock DB execution
    mock_result_totp = MagicMock()
    mock_result_totp.scalars.return_value.first.return_value = uuid4()

    mock_result_webauthn = MagicMock()
    mock_result_webauthn.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_result_totp, mock_result_webauthn]

    caps = await login_service._resolve_mfa_capabilities(user)

    assert caps["totp"] is True
    assert caps["webauthn"] is False


async def test_resolve_mfa_capabilities_legacy_totp(login_service, mock_db):
    user = MagicMock()
    user.id = uuid4()
    user.mfa_default_method = "totp"  # Trigger legacy check

    # Mock DB execution
    # 1. Active TOTP -> None
    # 2. Legacy TOTP -> Found
    # 3. WebAuthn -> None

    mock_active = MagicMock()
    mock_active.scalars.return_value.first.return_value = None

    mock_legacy = MagicMock()
    mock_legacy.scalars.return_value.first.return_value = uuid4()

    mock_webauthn = MagicMock()
    mock_webauthn.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_active, mock_legacy, mock_webauthn]

    caps = await login_service._resolve_mfa_capabilities(user)

    assert caps["totp"] is True
    assert caps["webauthn"] is False


async def test_collect_mfa_challenges_webauthn_flow(login_service):
    user = MagicMock()
    user.id = uuid4()

    capabilities = {"totp": False, "webauthn": True}

    with patch(
        "app.services.auth.login_service.mfa.issue_challenge", new_callable=AsyncMock
    ) as mock_issue:
        challenge = MagicMock()
        challenge.token = "webauthn-token"
        challenge.expires_at = datetime.now(UTC)
        mock_issue.return_value = challenge

        # Mock WebAuthn service via correct path
        with patch("app.services.webauthn.WebAuthnService") as MockService:
            service = MockService.return_value
            service.get_authentication_options = AsyncMock(
                return_value={"challenge": "stuff"}
            )

            with patch(
                "app.services.auth.login_service.mfa.describe_challenge_attempts",
                return_value=(0, 3, 3),
            ):
                challenges = await login_service._collect_mfa_challenges(
                    user, "en", capabilities
                )

                assert len(challenges) == 1
                assert challenges[0].method == "webauthn"
                assert challenges[0].challenge_token == "webauthn-token"
                assert challenges[0].challenge_expires_at == challenge.expires_at


def test_extract_client_info_forwarded(login_service):
    req = MagicMock()
    req.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2", "user-agent": "client-ua"}

    ip, ua = login_service._extract_client_info(req)
    assert ip == "10.0.0.1"
    assert ua == "client-ua"
