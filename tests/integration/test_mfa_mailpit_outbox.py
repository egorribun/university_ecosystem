"""Opt-in local SMTP acceptance: MFA API handlers, outbox, and Mailpit."""

from __future__ import annotations

import asyncio
import base64
import os
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException, Request, Response
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.config as config
from app.api.auth import login as login_api
from app.api.auth import mfa as mfa_api
from app.auth.mfa.email_otp import build_configured_email_otp_service
from app.auth.schemas import EmailOtpResendIn, MfaVerifyIn
from app.core.events import EventBus
from app.models import MfaChallenge, MfaEmailDelivery, StoredEvent, User
from app.services import event_handlers
from app.workers import outbox as outbox_module
from tests.integration.test_mfa_email_otp_postgres import (
    _postgres_acceptance_urls,
    _upgrade,
)

pytestmark = pytest.mark.skipif(
    not (os.getenv("MFA_TEST_MAILPIT_API") and os.getenv("MFA_TEST_SMTP_PORT")),
    reason="requires an explicit local-only Mailpit SMTP/API sink",
)


class _LocalLimiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        return None


def _sink_coordinates() -> tuple[str, int]:
    api_url = os.environ["MFA_TEST_MAILPIT_API"].rstrip("/")
    parsed = urlsplit(api_url)
    port = int(os.environ["MFA_TEST_SMTP_PORT"])
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not 0 < port < 65536
    ):
        raise ValueError("MFA Mailpit acceptance requires loopback-only endpoints")
    return api_url, port


def _request(session_id: object) -> Request:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/mfa/email/verification/start",
            "raw_path": b"/api/v1/auth/mfa/email/verification/start",
            "query_string": b"",
            "headers": [
                (b"user-agent", b"local-mfa-mailpit-acceptance"),
                (b"accept-language", b"en"),
            ],
            "client": ("127.0.0.1", 10000),
            "server": ("testserver", 80),
        }
    )
    request.state.active_session = SimpleNamespace(id=session_id)
    return request


def _mailpit_messages(api_url: str, recipient: str) -> list[dict[str, object]]:
    with httpx.Client(timeout=5, trust_env=False) as client:
        listing = client.get(f"{api_url}/api/v1/messages")
        listing.raise_for_status()
        messages: list[dict[str, object]] = []
        for summary in listing.json()["messages"]:
            message_id = quote(str(summary["ID"]), safe="")
            detail = client.get(f"{api_url}/api/v1/message/{message_id}")
            detail.raise_for_status()
            message = detail.json()
            if any(address.get("Address") == recipient for address in message["To"]):
                message["_mailpit_id"] = str(summary["ID"])
                messages.append(message)
        return messages


async def _await_messages(
    api_url: str, recipient: str, expected: int
) -> list[dict[str, object]]:
    for _ in range(40):
        messages = await asyncio.to_thread(_mailpit_messages, api_url, recipient)
        if len(messages) == expected:
            return messages
        await asyncio.sleep(0.05)
    pytest.fail(f"Mailpit did not receive {expected} local MFA messages")


def _mail_code(message: dict[str, object]) -> str:
    plain = message["Text"]
    assert isinstance(plain, str)
    matches = re.findall(r"(?<!\d)\d{6}(?!\d)", plain)
    assert len(matches) == 1
    return matches[0]


@pytest.mark.asyncio
async def test_email_mfa_handler_outbox_smtp_retry_and_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_url, smtp_port = _sink_coordinates()
    recipient = f"mfa-acceptance-{uuid4().hex}@example.test"
    user_id, session_id = uuid4(), uuid4()
    hmac_key = base64.urlsafe_b64encode(b"h" * 32).decode().rstrip("=")
    delivery_key = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    smtp_settings = SimpleNamespace(
        mfa_email_otp_hmac_keys=f"test-hmac:{hmac_key}",
        mfa_email_otp_active_hmac_key_id="test-hmac",
        mfa_email_delivery_keks=f"test-kek:{delivery_key}",
        mfa_email_delivery_active_kek_id="test-kek",
        smtp_host="127.0.0.1",
        smtp_port=1,  # Deliberate local connection refusal for the RED retry check.
        smtp_security="none",
        smtp_starttls=False,
        smtp_user="",
        smtp_password="",
        mail_from="no-reply@example.test",
    )
    monkeypatch.setattr(config, "settings", smtp_settings)
    service = build_configured_email_otp_service(rate_limiter=_LocalLimiter())
    completed = object()
    login_service = SimpleNamespace(
        get_email_otp_service=lambda: service,
        complete_step_up=AsyncMock(return_value=completed),
        publish_completed_step_up=AsyncMock(),
    )
    request = _request(session_id)
    monkeypatch.setattr(
        login_api,
        "_load_optional_active_session",
        AsyncMock(return_value=request.state.active_session),
    )

    with _postgres_acceptance_urls() as (async_url, sync_url):
        _upgrade(sync_url, "head")
        sync_engine = create_engine(sync_url)
        try:
            with sync_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (id,email,hashed_password,role,is_active) "
                        "VALUES (:id,:email,:password,'student',true)"
                    ),
                    {
                        "id": user_id,
                        "email": recipient,
                        "password": "not-used-in-acceptance",  # pragma: allowlist secret
                    },
                )
        finally:
            sync_engine.dispose()

        engine = create_async_engine(async_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(outbox_module, "async_session", sessions)
        monkeypatch.setattr(event_handlers, "async_session", sessions)
        bus = EventBus()
        bus.subscribe(
            "auth.mfa_email.requested",
            event_handlers.handle_mfa_email_delivery_requested,
        )
        monkeypatch.setattr(outbox_module, "event_bus", bus)
        worker = outbox_module.OutboxWorker(batch_size=1, max_retries=3)
        try:
            async with sessions() as db:
                user = await db.get(User, user_id)
                assert user is not None
                initial = await mfa_api.start_email_verification.__dishka_orig_func__(
                    request, db, login_service, user
                )
            assert initial.method == "email_otp"
            assert initial.delivery_hint != recipient
            assert await worker.process_batch() == 1
            async with sessions() as db:
                event = (await db.execute(select(StoredEvent))).scalar_one()
                delivery = (await db.execute(select(MfaEmailDelivery))).scalar_one()
                assert event.processed_at is None
                assert event.error_count == 1
                assert delivery.status == "pending"
            assert await asyncio.to_thread(_mailpit_messages, api_url, recipient) == []

            smtp_settings.smtp_port = smtp_port
            assert await worker.process_batch() == 1
            messages = await _await_messages(api_url, recipient, 1)
            initial_code = _mail_code(messages[0])
            initial_mailpit_id = messages[0]["_mailpit_id"]
            async with sessions() as db:
                event = (await db.execute(select(StoredEvent))).scalar_one()
                delivery = (await db.execute(select(MfaEmailDelivery))).scalar_one()
                assert event.processed_at is not None
                assert delivery.status == "sent"
                assert delivery.envelope_ciphertext is None
                await db.execute(
                    update(MfaChallenge)
                    .where(MfaChallenge.user_id == user_id)
                    .values(
                        resend_available_at=datetime.now(UTC) - timedelta(seconds=1)
                    )
                )
                await db.commit()

            async with sessions() as db:
                rotated = (
                    await login_api.resend_email_mfa_challenge.__dishka_orig_func__(
                        EmailOtpResendIn(challenge_token=initial.challenge_token),
                        request,
                        login_service,
                        db,
                    )
                )
            assert rotated.revision == 2
            assert rotated.challenge_token != initial.challenge_token
            assert await worker.process_batch() == 1
            messages = await _await_messages(api_url, recipient, 2)
            newly_delivered = [
                message
                for message in messages
                if message["_mailpit_id"] != initial_mailpit_id
            ]
            assert len(newly_delivered) == 1
            new_code = _mail_code(newly_delivered[0])

            async with sessions() as db:
                with pytest.raises(HTTPException) as rejected:
                    await login_api.verify_mfa_challenge.__dishka_orig_func__(
                        MfaVerifyIn(
                            method="email_otp",
                            challenge_token=initial.challenge_token,
                            code=initial_code,
                        ),
                        Response(),
                        request,
                        BackgroundTasks(),
                        login_service,
                        db,
                    )
            assert rejected.value.status_code == 400
            assert rejected.value.detail == "MFA verification failed"
            async with sessions() as db:
                result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
                    MfaVerifyIn(
                        method="email_otp",
                        challenge_token=rotated.challenge_token,
                        code=new_code,
                    ),
                    Response(),
                    request,
                    BackgroundTasks(),
                    login_service,
                    db,
                )
            assert result is completed
            async with sessions() as db:
                user = await db.get(User, user_id)
                assert user is not None and user.email_verified_at is not None
        finally:
            await engine.dispose()
