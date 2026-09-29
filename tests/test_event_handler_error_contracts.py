"""Stable error contracts for management-facing domain-event handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.auth.mfa import email_otp
from app.core.events import DurableEventDeferred, MfaEmailDeliveryRequested
from app.services import event_handlers


@pytest.mark.asyncio
async def test_mfa_delivery_missing_id_has_stable_exact_error_message() -> None:
    """The outbox/DLQ boundary exposes one deterministic validation message."""

    with pytest.raises(ValueError) as caught:
        await event_handlers.handle_mfa_email_delivery_requested(
            MfaEmailDeliveryRequested()
        )

    assert str(caught.value) == "MFA delivery event is missing delivery_id"


@pytest.mark.asyncio
async def test_mfa_delivery_handler_does_not_expose_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_error = RuntimeError("recipient user@example.test, code 123456")
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(event_handlers, "async_session", lambda: context)
    service = AsyncMock()
    service.deliver.side_effect = secret_error
    monkeypatch.setattr(
        email_otp, "build_configured_email_delivery_service", lambda: service
    )

    with pytest.raises(email_otp.MfaDeliveryError) as caught:
        await event_handlers.handle_mfa_email_delivery_requested(
            MfaEmailDeliveryRequested(delivery_id=uuid4())
        )

    assert str(caught.value) == "MFA delivery failed"
    assert caught.value.__suppress_context__ is True
    assert caught.value.__cause__ is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mfa_delivery_handler_preserves_lease_deferral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(event_handlers, "async_session", lambda: context)
    service = AsyncMock()
    service.deliver.side_effect = DurableEventDeferred()
    monkeypatch.setattr(
        email_otp, "build_configured_email_delivery_service", lambda: service
    )

    with pytest.raises(DurableEventDeferred):
        await event_handlers.handle_mfa_email_delivery_requested(
            MfaEmailDeliveryRequested(delivery_id=uuid4())
        )
    session.commit.assert_not_awaited()
