"""Email MFA preserves the security epoch of password/session validation."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal, TypedDict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import BackgroundTasks, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa.email_otp import EmailOtpService, IssuedEmailOtp, MfaOtpRejected
from app.auth.schemas import PendingMfaResponse
from app.auth.security import get_password_hash
from app.models import MfaChallenge, RecoveryCode, User
from app.repositories.auth_repository import AuthRepository
from app.repositories.unit_of_work import UnitOfWork, uow_from_session
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import UserPasswordChangeIn
from app.services.auth.login_service import LoginService
from app.services.auth_service import AuthService

OLD_PASSWORD = "Old-email-mfa-password-11!"  # pragma: allowlist secret
NEW_PASSWORD = "New-email-mfa-password-22!"  # pragma: allowlist secret
FINGERPRINT = "f" * 64
IP = "203.0.113.8"
SESSION = "verified-password-nonce"


class _ChallengeBinding(TypedDict):
    challenge_token: str
    user_id: UUID
    flow: str
    session_identifier: str
    client_fingerprint: str
    client_ip: str


def _request() -> Request:
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = None
    return request


@pytest.fixture
async def prepared(
    db_session: AsyncSession, test_user: User
) -> tuple[EmailOtpService, AuthService, UnitOfWork]:
    test_user.hashed_password = await get_password_hash(OLD_PASSWORD)
    test_user.email_verified_at = datetime.now(UTC)
    test_user.email_mfa_enabled_at = datetime.now(UTC)
    test_user.mfa_required = True
    test_user.mfa_default_method = "email_otp"
    test_user.mfa_epoch = 0
    await db_session.commit()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=SimpleNamespace(enforce=AsyncMock()),
    )
    uow = uow_from_session(db_session)
    auth = AuthService(
        MagicMock(),
        AuthRepository(db_session),
        UserRepository(db_session),
        uow.sessions,
        uow,
    )
    return service, auth, uow


async def _change_password(auth: AuthService, user: User) -> None:
    with patch("app.services.auth_service.validate_password_hibp", AsyncMock()):
        await auth.change_password(
            user,
            UserPasswordChangeIn(
                current_password=OLD_PASSWORD, new_password=NEW_PASSWORD
            ),
            _request(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["verify", "opaque", "recovery", "resend"])
@pytest.mark.parametrize("change_password", [False, True])
async def test_email_challenge_cannot_survive_password_epoch_change(
    db_session: AsyncSession,
    test_user: User,
    prepared: tuple[EmailOtpService, AuthService, UnitOfWork],
    operation: Literal["verify", "opaque", "recovery", "resend"],
    change_password: bool,
) -> None:
    service, auth, _ = prepared
    issued = await service.issue(
        db_session,
        user_id=test_user.id,
        expected_mfa_epoch=int(test_user.mfa_epoch or 0),
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
    )
    recovery = RecoveryCode(
        user_id=test_user.id,
        code_hash=await get_password_hash("AABBCCDDEEFF0011", validate_policy=False),
        is_used=False,
    )
    db_session.add(recovery)
    await db_session.commit()
    if change_password:
        await _change_password(auth, test_user)

    async def consume() -> MfaChallenge | IssuedEmailOtp:
        if operation == "opaque":
            return await service.verify_opaque(
                db_session,
                challenge_token=issued.challenge_token,
                code=issued.otp,
                client_fingerprint=FINGERPRINT,
                client_ip=IP,
                login_session_identifier=SESSION,
            )
        if operation == "recovery":
            return await service.consume_recovery_opaque(
                db_session,
                challenge_token=issued.challenge_token,
                code="AABB-CCDD-EEFF-0011",
                client_fingerprint=FINGERPRINT,
                client_ip=IP,
                login_session_identifier=SESSION,
                active_session_identifier=None,
            )
        binding: _ChallengeBinding = {
            "challenge_token": issued.challenge_token,
            "user_id": test_user.id,
            "flow": "login",
            "session_identifier": SESSION,
            "client_fingerprint": FINGERPRINT,
            "client_ip": IP,
        }
        if operation == "resend":
            return await service.resend(
                db_session,
                **binding,
                locale="en",
                now=datetime.now(UTC) + timedelta(seconds=61),
            )
        return await service.verify(db_session, **binding, code=issued.otp)

    if change_password:
        with pytest.raises(MfaOtpRejected):
            await consume()
        assert recovery.is_used is False
    else:
        assert await consume() is not None


def _build_login_service(
    db_session: AsyncSession,
    prepared: tuple[EmailOtpService, AuthService, UnitOfWork],
) -> LoginService:
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.mfa_coordinator import MfaCoordinator

    service, _, uow = prepared
    repo = UserRepository(db_session)
    validator = CredentialValidator(
        uow,
        repo,
        SimpleNamespace(get_auth_user_by_email=repo.get_auth_by_email),
        SimpleNamespace(
            get_active_lockout=AsyncMock(return_value=None),
            clear_failed_attempts=AsyncMock(return_value=0),
        ),
        MagicMock(),
        MagicMock(),
    )
    coordinator = MfaCoordinator(uow, AuthRepository(db_session), service)
    return LoginService(validator, coordinator, MagicMock(), db_session)


@pytest.mark.asyncio
async def test_delayed_email_issuance_rejects_stale_validated_password_dto(
    db_session, test_user, prepared, monkeypatch: pytest.MonkeyPatch
):
    _, auth, _ = prepared
    login = _build_login_service(db_session, prepared)
    coordinator = login.mfa_coord
    original_collect = coordinator._collect_mfa_challenges
    validated = asyncio.Event()
    resume = asyncio.Event()

    async def paused_collect(*args, **kwargs):
        validated.set()
        await resume.wait()
        return await original_collect(*args, **kwargs)

    monkeypatch.setattr(coordinator, "_collect_mfa_challenges", paused_collect)
    request = _request()
    with (
        patch(
            "app.core.fingerprint.extract_request_fingerprint", return_value=FINGERPRINT
        ),
        patch("app.core.ratelimit.resolve_client_ip", return_value=IP),
    ):
        task = asyncio.create_task(
            login.perform_login(
                test_user.email, OLD_PASSWORD, request, Response(), BackgroundTasks()
            )
        )
        await asyncio.wait_for(validated.wait(), timeout=5)
        try:
            await _change_password(auth, test_user)
        finally:
            resume.set()
        with pytest.raises(MfaOtpRejected):
            await task
        result = await login.perform_login(
            test_user.email, NEW_PASSWORD, request, Response(), BackgroundTasks()
        )
    assert result is not None
    assert isinstance(result, PendingMfaResponse)
    assert [method.method for method in result.methods] == ["email_otp"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["form", "json"])
@pytest.mark.parametrize("change_password", [False, True])
async def test_http_login_maps_stale_email_issuance_to_auth_rejection(
    db_session, test_user, prepared, route, change_password, monkeypatch
):
    from dishka import Provider, Scope, make_async_container
    from dishka.integrations.fastapi import setup_dishka
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.auth import login as login_api
    from app.core.localization import translate
    from app.core.protocols import AsyncDatabaseSession
    from app.models import MfaChallenge
    from app.services.auth.login_service import LoginService

    _, auth, _ = prepared
    login = _build_login_service(db_session, prepared)
    provider = Provider(scope=Scope.REQUEST)
    provider.provide(lambda: login, provides=LoginService)
    provider.provide(lambda: db_session, provides=AsyncDatabaseSession)
    container = make_async_container(provider)
    test_app = FastAPI()
    test_app.include_router(login_api.router)
    setup_dishka(container, test_app)
    email, user_id = test_user.email, test_user.id
    validated = asyncio.Event()
    resume = asyncio.Event()
    original_collect = login.mfa_coord._collect_mfa_challenges

    async def paused_collect(*args, **kwargs):
        validated.set()
        await resume.wait()
        return await original_collect(*args, **kwargs)

    monkeypatch.setattr(login.mfa_coord, "_collect_mfa_challenges", paused_collect)
    path = "/login" if route == "form" else "/login/json"
    body = (
        {"data": {"username": email, "password": OLD_PASSWORD}}
        if route == "form"
        else {"json": {"email": email, "password": OLD_PASSWORD}}
    )
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://testserver",
        headers={"Accept-Language": "en"},
    ) as client:
        task = asyncio.create_task(client.post(path, **body))
        try:
            await asyncio.wait_for(validated.wait(), timeout=5)
            if change_password:
                await _change_password(auth, test_user)
        finally:
            resume.set()
        response = await task
    await container.close()

    if change_password:
        assert response.status_code == 401, response.text
        assert response.json() == {
            "detail": translate("errors.auth.credentials_invalid", locale="en")
        }
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert "set-cookie" not in response.headers
        assert not db_session.in_transaction()
        from sqlalchemy import select

        assert (
            await db_session.scalar(
                select(MfaChallenge).where(MfaChallenge.user_id == user_id)
            )
            is None
        )
    else:
        assert response.status_code == 202, response.text
        payload = response.json()
        assert [method["method"] for method in payload["methods"]] == ["email_otp"]
        assert payload["user_id"] == str(user_id)
        assert "mfa_pre_auth_v1=" in response.headers["set-cookie"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"mfa_epoch": "0"},
        {"mfa_epoch": True},
        {"mfa_epoch": 0.0},
        {"mfa_epoch": -1},
        {"mfa_epoch": 1},
    ],
)
async def test_unbound_or_noncanonical_challenge_epoch_is_rejected(
    db_session, test_user, prepared, payload
):
    from app.models import MfaChallenge

    service, _, _ = prepared
    issued = await service.issue(
        db_session,
        user_id=test_user.id,
        expected_mfa_epoch=0,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
    )
    challenge = await db_session.get(MfaChallenge, issued.challenge_id)
    challenge.payload = payload
    # Python considers 0 == 0.0; force the malformed JSON representation to
    # storage instead of allowing ORM equality tracking to retain integer zero.
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(challenge, "payload")
    await db_session.commit()
    with pytest.raises(MfaOtpRejected):
        await service.verify_opaque(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            login_session_identifier=SESSION,
        )
    assert challenge.attempt_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("epoch", [None, True, "0", 0.0, -1, 1])
async def test_issuance_requires_current_canonical_credential_epoch(
    db_session, test_user, prepared, epoch
):
    service, _, _ = prepared
    with pytest.raises(MfaOtpRejected):
        await service.issue(
            db_session,
            user_id=test_user.id,
            expected_mfa_epoch=epoch,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            locale="en",
        )


@pytest.mark.asyncio
async def test_public_login_persists_requested_locale_with_email_challenge(
    db_session: AsyncSession,
    test_user: User,
    prepared: tuple[EmailOtpService, AuthService, UnitOfWork],
) -> None:
    from dishka import Provider, Scope, make_async_container
    from dishka.integrations.fastapi import setup_dishka
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from app.api.auth import login as login_api
    from app.core import database
    from app.core.protocols import AsyncDatabaseSession
    from app.models import ChallengeState, MfaChallenge, MfaEmailDelivery, StoredEvent
    from app.services.auth.login_service import LoginService

    login = _build_login_service(db_session, prepared)
    provider = Provider(scope=Scope.REQUEST)
    provider.provide(lambda: login, provides=LoginService)
    provider.provide(lambda: db_session, provides=AsyncDatabaseSession)
    container = make_async_container(provider)
    test_app = FastAPI()
    test_app.include_router(login_api.router)
    setup_dishka(container, test_app)

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://testserver",
        headers={"Accept-Language": "ru"},
    ) as client:
        response = await client.post(
            "/login/json",
            json={"email": test_user.email, "password": OLD_PASSWORD},
        )
    await container.close()

    assert response.status_code == 202
    assert [method["method"] for method in response.json()["methods"]] == ["email_otp"]
    async with database.async_session() as reader:
        challenge = (
            await reader.execute(
                select(MfaChallenge).where(MfaChallenge.user_id == test_user.id)
            )
        ).scalar_one()
        delivery = (
            await reader.execute(
                select(MfaEmailDelivery).where(
                    MfaEmailDelivery.challenge_id == challenge.id
                )
            )
        ).scalar_one()
        event = (
            await reader.execute(
                select(StoredEvent).where(
                    StoredEvent.event_type == "auth.mfa_email.requested",
                    StoredEvent.aggregate_id_uuid == challenge.id,
                )
            )
        ).scalar_one()
        assert challenge.flow == "login"
        assert challenge.payload == {"mfa_epoch": 0}
        assert challenge.state == ChallengeState.PENDING
        assert challenge.consumed_at is None
        assert delivery.status == "pending"
        assert delivery.locale == "ru"
        assert event.payload["locale"] == "ru"
        assert event.payload["delivery_id"] == str(delivery.id)
