"""Stable error contracts for management-facing domain-event handlers."""

from __future__ import annotations

import pytest

from app.core.events import MfaEmailDeliveryRequested
from app.services import event_handlers


@pytest.mark.asyncio
async def test_mfa_delivery_missing_id_has_stable_exact_error_message() -> None:
    """The outbox/DLQ boundary exposes one deterministic validation message."""

    with pytest.raises(ValueError) as caught:
        await event_handlers.handle_mfa_email_delivery_requested(
            MfaEmailDeliveryRequested()
        )

    assert str(caught.value) == "MFA delivery event is missing delivery_id"
