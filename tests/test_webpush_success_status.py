"""Offline provider-response observability without real network delivery."""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from sqlalchemy import select

from app.models import NotificationDelivery, PushSubscription
from app.services import webpush as service
from app.services.notifications import delivery
from app.services.notifications.stats import aggregate_notification_delivery_stats
from scripts import live_push_worker_observation as observation

PRIVATE = "private-endpoint-token-user-payload"


def _response(status: object) -> requests.Response:
    response = requests.Response()
    response.__dict__["status_code"] = status
    response._content = PRIVATE.encode()
    return response


@pytest.fixture
def sender(monkeypatch: pytest.MonkeyPatch):
    subscription = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        endpoint=f"https://push.example.test/{PRIVATE}",
        p256dh=PRIVATE,
        auth=PRIVATE,
        user=None,
    )
    session = MagicMock()
    monkeypatch.setattr(
        service, "validate_and_resolve", lambda _: [("93.184.216.34", 443)]
    )
    monkeypatch.setattr(service, "_create_pinned_webpush_session", lambda *_: session)
    return subscription, session


@pytest.mark.parametrize("status", [200, 201, 202])
def test_success_preserves_real_response_status_and_emits_closed_summary(
    status: int,
    sender: tuple[SimpleNamespace, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    subscription, session = sender
    monkeypatch.setattr(service, "webpush", lambda **_: _response(status))
    with caplog.at_level(logging.INFO, logger="app.services.webpush"):
        result = service.send_web_push(subscription, {"title": PRIVATE})
    assert result.status == "sent"
    assert result.status_code == status
    assert result.error is None
    session.close.assert_called_once()
    rows = [
        record.msg
        for record in caplog.records
        if record.name == "app.services.webpush" and isinstance(record.msg, dict)
    ]
    assert len(rows) == 1
    assert rows[0]["extra"]["status_code"] == status
    summary = observation.project_worker_logs(
        (json.dumps(rows[0], default=str) + "\n").encode(), b""
    )
    assert summary is not None
    assert summary.http_classes[1] == 1
    assert summary.success_http == ((1, 0) if status == 201 else (0, 1))
    public = observation.render_summary(summary) + observation.render_success_summary(
        summary
    )
    assert PRIVATE not in public
    assert "https://" not in public and "#" not in public
    assert (
        str(subscription.id) not in public and str(subscription.user_id) not in public
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "legacy result",
        SimpleNamespace(status_code=201),
        MagicMock(),
        MagicMock(spec=requests.Response),
        _response(None),
        _response(True),
        _response("201"),
        _response(99),
        _response(600),
    ],
)
def test_legacy_or_invalid_success_response_preserves_unknown_status(
    value: object,
    sender: tuple[SimpleNamespace, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    subscription, session = sender
    monkeypatch.setattr(service, "webpush", lambda **_: value)
    with caplog.at_level(logging.INFO, logger="app.services.webpush"):
        result = service.send_web_push(subscription, {"title": PRIVATE})
    assert result.status == "sent"
    assert result.status_code is None
    session.close.assert_called_once()
    rows = [
        record.msg
        for record in caplog.records
        if record.name == "app.services.webpush" and isinstance(record.msg, dict)
    ]
    assert len(rows) == 1
    assert "status_code" not in rows[0]["extra"]
    summary = observation.project_worker_logs(
        (json.dumps(rows[0], default=str) + "\n").encode(), b""
    )
    assert summary is not None
    assert summary.http_classes[-1] == 1
    assert summary.success_http == (0, 0)
    assert PRIVATE not in observation.render_summary(summary)


def test_success_status_inspection_does_not_invoke_response_descriptors(
    sender: tuple[SimpleNamespace, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResponseWithBrokenAccessor(requests.Response):
        def __getattribute__(self, name: str):
            if name == "status_code":
                raise RuntimeError(PRIVATE)
            return super().__getattribute__(name)

    response = ResponseWithBrokenAccessor()
    response.status_code = 201
    subscription, session = sender
    monkeypatch.setattr(service, "webpush", lambda **_: response)
    result = service.send_web_push(subscription, {"title": PRIVATE})
    assert result.status == "sent"
    assert result.status_code == 201
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_real_send_status_reaches_existing_delivery_row_and_stats(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory()
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example.test/{PRIVATE}",
        p256dh=PRIVATE,
        auth=PRIVATE,
    )
    db_session.add(subscription)
    await db_session.commit()
    monkeypatch.setattr(
        service, "validate_and_resolve", lambda _: [("93.184.216.34", 443)]
    )
    session = MagicMock()
    monkeypatch.setattr(service, "_create_pinned_webpush_session", lambda *_: session)
    monkeypatch.setattr(service, "webpush", lambda **_: _response(201))
    monkeypatch.setattr(service, "process_push_results", AsyncMock())
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)

    created = await delivery.create_notifications_for_users(
        db_session, title=PRIVATE, user_ids=[user.id]
    )
    assert created == 1
    row = (await db_session.execute(select(NotificationDelivery))).scalars().one()
    assert row.status == "sent"
    assert row.status_code == 201
    stats = await aggregate_notification_delivery_stats(db_session)
    sent = next(item for item in stats if item["channel"] == "webpush")
    assert sent["status"] == "sent" and sent["count"] == 1
    assert "status_code" not in sent
    session.close.assert_called_once()
