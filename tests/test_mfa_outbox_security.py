from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa.email_otp import EmailOtpService
from app.models import MfaEmailDelivery, StoredEvent, User
from app.models.failed_outbox_events import FailedOutboxEvent
from app.workers.outbox import OutboxWorker

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class _AllowAllRateLimiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        del action, identifier


async def _create_mfa_delivery(
    db: AsyncSession, user: User
) -> tuple[MfaEmailDelivery, StoredEvent]:
    user.email_verified_at = NOW - timedelta(days=1)
    user.email_mfa_enabled_at = NOW - timedelta(hours=1)
    await db.flush()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=_AllowAllRateLimiter(),
    )
    issued = await service.issue(
        db,
        user_id=user.id,
        flow="login",
        session_identifier="preauth-session",
        client_fingerprint="f" * 64,
        client_ip="203.0.113.20",
        locale="en",
        now=NOW,
    )
    delivery = (
        await db.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    event = (
        await db.execute(
            select(StoredEvent).where(
                StoredEvent.event_type == "auth.mfa_email.requested"
            )
        )
    ).scalar_one()
    return delivery, event


@pytest.mark.asyncio
async def test_terminal_mfa_delivery_failure_is_crypto_shredded_in_dlq_transaction(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    delivery, event = await _create_mfa_delivery(db_session, test_user)
    event.error_count = 5

    await OutboxWorker(max_retries=5)._move_to_dlq(
        db_session, event, "MfaDeliveryError: MFA delivery failed"
    )
    await db_session.flush()
    await db_session.refresh(delivery)

    assert event.processed_at is not None
    assert delivery.status == "cancelled"
    assert delivery.shredded_at is not None
    assert delivery.envelope_nonce is None
    assert delivery.envelope_ciphertext is None
    assert delivery.wrap_nonce is None
    assert delivery.wrapped_dek is None
    assert delivery.lease_token is None
    assert delivery.lease_expires_at is None
    failed = await db_session.scalar(
        select(FailedOutboxEvent).where(FailedOutboxEvent.original_event_id == event.id)
    )
    assert failed is not None


@pytest.mark.asyncio
async def test_non_mfa_dlq_event_does_not_shred_unrelated_mfa_delivery(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    delivery, _mfa_event = await _create_mfa_delivery(db_session, test_user)
    unrelated = StoredEvent(
        event_type="system.release",
        aggregate_type="Release",
        aggregate_id="release-1",
        payload={"version": "1.0.0"},
        metadata_={},
        error_count=5,
    )
    db_session.add(unrelated)
    await db_session.flush()

    await OutboxWorker(max_retries=5)._move_to_dlq(
        db_session, unrelated, "RuntimeError: publication failed"
    )
    await db_session.flush()
    await db_session.refresh(delivery)

    assert unrelated.processed_at is not None
    assert delivery.status == "pending"
    assert delivery.shredded_at is None
    assert delivery.envelope_ciphertext is not None
    assert delivery.wrapped_dek is not None


@pytest.mark.asyncio
async def test_terminal_mfa_event_with_invalid_delivery_id_fails_closed(
    db_session: AsyncSession,
) -> None:
    malformed = StoredEvent(
        event_type="auth.mfa_email.requested",
        aggregate_type="MfaChallenge",
        aggregate_id="challenge-1",
        payload={"delivery_id": "not-a-uuid"},
        metadata_={},
        error_count=5,
    )
    db_session.add(malformed)
    await db_session.flush()

    with pytest.raises(RuntimeError, match="invalid MFA delivery id"):
        await OutboxWorker(max_retries=5)._move_to_dlq(
            db_session, malformed, "MfaDeliveryError: MFA delivery failed"
        )

    assert malformed.processed_at is None
