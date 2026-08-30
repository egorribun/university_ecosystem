"""Focused behavioral contracts for mutation-sensitive backend paths.

These tests deliberately assert the trust-boundary values that broad integration
tests do not always observe: notification metadata, atomic MFA predicates, and
stable public error responses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api import cwv as cwv_api
from app.auth.constants import MFA_METHOD_EMAIL_OTP
from app.auth.mfa.email_otp import EmailOtpService
from app.models import ChallengeState
from app.services import cwv, notification_queue
from app.services.notifications import core as notifications_core
from app.services.notifications import delivery, news_events
from app.services.webpush import WebPushResult

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def push_configured(monkeypatch: pytest.MonkeyPatch):
    """Enable the delivery path without relying on another module's fixture."""
    monkeypatch.setattr(delivery.settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(delivery.settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(delivery.settings, "vapid_subject", "mailto:test@example.com")


def _compiled(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[union-attr]


def _email_service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=AsyncMock(),
    )


def test_dead_letter_digest_uses_the_canonical_ascii_codec() -> None:
    """Queue correlation digests use the documented lowercase ASCII codec."""

    assert "ascii" in notification_queue._dead_letter_batch_digest.__code__.co_consts
    job_ids = [
        uuid.UUID("bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb"),
        uuid.UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
    ]
    expected = notification_queue.sha256(
        b"aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa\nbbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb"
    ).hexdigest()
    assert notification_queue._dead_letter_batch_digest(job_ids) == expected


def test_cwv_public_errors_keep_stable_details() -> None:
    for exc, expected_status, expected_detail in (
        (cwv.CwvConfigurationError(), 503, "CWV collection unavailable"),
        (cwv.CwvOriginError(), 403, "CWV request rejected"),
        (cwv.CwvEnvelopeError(), 422, "Invalid CWV evidence"),
    ):
        with pytest.raises(HTTPException) as caught:
            cwv_api._raise_contract_error(exc)
        assert caught.value.status_code == expected_status
        assert caught.value.detail == expected_detail


def test_cwv_exporter_bearer_error_is_stable() -> None:
    for value in (None, "x" * 8193, "Basic token", "Bearer"):
        with pytest.raises(HTTPException) as caught:
            cwv_api._bearer(value)
        assert caught.value.status_code == 401
        assert caught.value.detail == "Exporter authentication required"
    # The documented maximum is inclusive: an otherwise valid header with
    # exactly 8192 bytes is accepted, while the next byte is rejected.
    boundary_token = "x" * (8192 - len("Bearer "))
    assert cwv_api._bearer(f"Bearer {boundary_token}") == boundary_token
    with pytest.raises(HTTPException) as caught:
        cwv_api._bearer(f"Bearer {boundary_token}x")
    assert caught.value.status_code == 401
    assert caught.value.detail == "Exporter authentication required"
    assert cwv_api._bearer("bearer token") == "token"
    assert cwv_api._bearer("Bearer token extra") == "token extra"


def _event() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Лекция",
        title_en="Lecture",
        description="Описание",
        description_en="Description",
        about=None,
        about_en=None,
        location="Корпус А",
        location_en="Building A",
        event_type="Лекция",
        event_type_en="Lecture",
        speaker="Преподаватель",
        starts_at=NOW + timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_event_notification_keeps_db_topic_title_and_translations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    users = [uuid.uuid4()]
    create = AsyncMock(return_value=1)
    monkeypatch.setattr(
        news_events, "_fetch_active_user_ids", AsyncMock(return_value=users)
    )
    monkeypatch.setattr(news_events, "create_notifications_for_users", create)
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )

    result = await news_events.notify_about_event(db, _event(), locale="ru")

    assert result == 1
    assert create.await_args is not None
    assert create.await_args.args[0] is db
    kwargs = create.await_args.kwargs
    assert kwargs["title"]
    assert kwargs["title_translations"]["ru"]
    assert kwargs["title_translations"]["en"]
    assert kwargs["body_translations"]["ru"]
    assert kwargs["body_translations"]["en"]
    assert kwargs["topic"] == "events.published"


@pytest.mark.asyncio
async def test_news_notification_forwards_rendered_body_to_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    create = AsyncMock(return_value=1)
    user_ids = [uuid.uuid4()]
    monkeypatch.setattr(
        news_events, "_fetch_active_user_ids", AsyncMock(return_value=user_ids)
    )
    monkeypatch.setattr(news_events, "create_notifications_for_users", create)
    monkeypatch.setattr(
        news_events, "render_notification_template", lambda *a, **k: None
    )
    news = SimpleNamespace(
        id=uuid.uuid4(),
        title="Заголовок",
        title_en="Headline",
        content="Содержимое новости",
        content_en="News body",
    )

    assert await news_events.notify_about_news(db, news, locale="ru") == 1

    assert create.await_args is not None
    assert create.await_args.args[0] is db
    assert create.await_args.kwargs["title"] == "Новая новость: Заголовок"
    assert create.await_args.kwargs["body"] == "Содержимое новости"
    assert create.await_args.kwargs["title_translations"] == {
        "ru": "Новая новость: Заголовок",
        "en": "New article: Headline",
    }
    assert create.await_args.kwargs["body_translations"] == {
        "ru": "Содержимое новости",
        "en": "News body",
    }
    assert create.await_args.kwargs["topic"] == "news.published"


@pytest.mark.asyncio
async def test_comment_notification_passes_database_to_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    create = AsyncMock(return_value=1)
    monkeypatch.setattr(
        notifications_core, "_fetch_admin_ids", AsyncMock(return_value=[uuid.uuid4()])
    )
    monkeypatch.setattr(news_events, "create_notifications_for_users", create)
    monkeypatch.setattr(
        news_events,
        "render_notification_template",
        lambda *a, **k: {
            "title": "Comment",
            "body": "Body",
            "url": "/news/1",
            "tag": "n",
        },
    )
    news = SimpleNamespace(id=uuid.uuid4(), title="News", title_en="News")
    comment = SimpleNamespace(content="Comment")
    author = SimpleNamespace(full_name="Author", username="author")

    assert await news_events.notify_about_comment(db, news, comment, author) == 1
    assert create.await_args is not None
    assert create.await_args.args[0] is db
    assert create.await_args.kwargs["topic"] == "news.published"


@pytest.mark.asyncio
async def test_push_redelivery_records_delivery_and_counts_two_successes(
    db_session,
    user_factory,
    push_configured,
    push_subscription_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_user = await user_factory()
    second_user = await user_factory()
    first_sub = await push_subscription_factory(first_user)
    second_sub = await push_subscription_factory(second_user)

    from app.models import Notification

    first = Notification(
        user_id=first_user.id,
        title="First",
        body="Body",
        type="news",
        url="/news/1",
        created_at=NOW,
        read=False,
    )
    second = Notification(
        user_id=second_user.id,
        title="Second",
        body="Body",
        type="news",
        url="/news/2",
        created_at=NOW,
        read=False,
    )
    db_session.add_all([first, second])
    await db_session.commit()

    async def _send(subscription, _payload):
        return WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", _send)
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    outcome = await delivery.redeliver_notifications(
        db_session, notification_ids=[first.id, second.id]
    )

    assert outcome.sent == 2
    rows = (
        (
            await db_session.execute(
                select(delivery.NotificationDelivery).where(
                    delivery.NotificationDelivery.notification_id.in_(
                        [first.id, second.id]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.subscription_id for row in rows} == {first_sub.id, second_sub.id}
    assert all(row.delivered_at is not None for row in rows)


def test_email_delivery_and_outbox_contracts() -> None:
    service = _email_service()
    challenge = SimpleNamespace(id=uuid.uuid4())
    delivery_row = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=1,
        email="student@example.edu",
        otp="123456",
        locale="unsupported",
        display_name="Student",
        now=NOW,
    )
    assert delivery_row.locale == "en"
    assert delivery_row.status == "pending"
    assert delivery_row.attempt_count == 0

    event = service._build_outbox(delivery_row)
    assert event.metadata_ == {}
    assert event.payload == {
        "delivery_id": str(delivery_row.id),
        "template": "mfa_email_otp",
        "locale": "en",
        "revision": 1,
    }

    subject, plain, html = service._render_email(
        otp="654321", display_name="", locale="en"
    )
    assert subject == "Your verification code"
    assert plain.startswith("Hello!\nVerification code: 654321\n")
    assert "<p>Hello!<br>Verification code: 654321<br>" in html


@pytest.mark.asyncio
async def test_user_id_from_token_uses_exact_challenge_identity_predicate() -> None:
    service = _email_service()
    challenge_id = uuid.uuid4()
    from app.auth.mfa.email_otp import _generate_challenge_token

    token = _generate_challenge_token(challenge_id)
    db = MagicMock()
    db.scalar = AsyncMock(return_value=uuid.uuid4())

    await service._user_id_from_token(db, token)

    sql = _compiled(db.scalar.await_args.args[0])
    assert "mfa_challenges.id =" in sql
    assert "mfa_challenges.id !=" not in sql


def _challenge(*, flow: str = "login", revision: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        flow=flow,
        method=MFA_METHOD_EMAIL_OTP,
        session_identifier="session",
        client_fingerprint="f" * 64,
        revision=revision,
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=5),
        resend_available_at=NOW,
        recipient_digest="recipient",
        otp_digest="otp",
        otp_key_id="active",
        token_key_id="active",
        attempt_count=0,
    )


@pytest.mark.asyncio
async def test_resend_update_rotates_recipient_and_keeps_pending_revision_guard() -> (
    None
):
    service = _email_service()
    challenge = _challenge()
    user = SimpleNamespace(id=challenge.user_id, email="student@example.edu")
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._digest = MagicMock(return_value="digest")  # type: ignore[method-assign]
    first_result = MagicMock()
    first_result.one_or_none.return_value = (challenge.id,)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    await service.resend(
        db,
        challenge_token="token",
        user_id=challenge.user_id,
        flow=challenge.flow,
        session_identifier=challenge.session_identifier,
        client_fingerprint=challenge.client_fingerprint,
        client_ip="127.0.0.1",
        locale="en",
        now=NOW + timedelta(seconds=61),
    )

    sql = _compiled(db.execute.await_args_list[0].args[0])
    assert "recipient_digest" in sql
    assert "mfa_challenges.revision =" in sql
    assert "mfa_challenges.state =" in sql


@pytest.mark.asyncio
async def test_verify_success_update_is_bound_to_revision_and_user_devices() -> None:
    service = _email_service()
    challenge = _challenge(flow="email_mfa_enablement")
    user = SimpleNamespace(
        id=challenge.user_id,
        email="student@example.edu",
        email_mfa_enabled_at=None,
        mfa_required=False,
        mfa_epoch=0,
        mfa_default_method=None,
    )
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._digest = MagicMock(return_value="otp")  # type: ignore[method-assign]
    consumed = MagicMock()
    consumed.one_or_none.return_value = (challenge.id,)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[consumed, MagicMock()])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    await service.verify(
        db,
        challenge_token="token",
        code="654321",
        user_id=challenge.user_id,
        flow=challenge.flow,
        session_identifier=challenge.session_identifier,
        client_fingerprint=challenge.client_fingerprint,
        client_ip="127.0.0.1",
        now=NOW,
    )

    service._resolve_recipient.assert_awaited_once_with(  # type: ignore[attr-defined]
        db, user_id=challenge.user_id, flow=challenge.flow, for_update=True
    )
    consumed_sql = _compiled(db.execute.await_args_list[0].args[0])
    device_sql = _compiled(db.execute.await_args_list[1].args[0])
    assert "mfa_challenges.revision =" in consumed_sql
    assert "mfa_challenges.state =" in consumed_sql
    assert "RETURNING mfa_challenges.id" in consumed_sql
    assert "trusted_devices.user_id =" in device_sql
    assert "trusted_devices.user_id !=" not in device_sql


@pytest.mark.asyncio
async def test_verify_opaque_forwards_the_presented_code_unchanged() -> None:
    service = _email_service()
    challenge = _challenge()
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service.verify = AsyncMock(return_value=challenge)  # type: ignore[method-assign]

    await service.verify_opaque(
        MagicMock(),
        challenge_token="opaque-token",
        code="654321",
        client_fingerprint=challenge.client_fingerprint,
        client_ip="127.0.0.1",
        login_session_identifier=challenge.session_identifier,
    )

    service.verify.assert_awaited_once()
    assert service.verify.await_args.kwargs["code"] == "654321"


@pytest.mark.asyncio
async def test_resend_locks_recipient_and_cancels_only_pending_deliveries() -> None:
    service = _email_service()
    challenge = _challenge()
    user = SimpleNamespace(id=challenge.user_id, email="student@example.edu")
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._digest = MagicMock(return_value="digest")  # type: ignore[method-assign]
    first_result = MagicMock()
    first_result.one_or_none.return_value = (challenge.id,)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[first_result, MagicMock()])
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    await service.resend(
        db,
        challenge_token="token",
        user_id=challenge.user_id,
        flow=challenge.flow,
        session_identifier=challenge.session_identifier,
        client_fingerprint=challenge.client_fingerprint,
        client_ip="127.0.0.1",
        locale="en",
        now=NOW + timedelta(seconds=61),
    )

    service._resolve_recipient.assert_awaited_once_with(
        db, user_id=challenge.user_id, flow=challenge.flow, for_update=True
    )
    delivery_sql = _compiled(db.execute.await_args_list[1].args[0])
    assert "mfa_email_deliveries.status =" in delivery_sql
