from __future__ import annotations

import uuid
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.routers import notifications
from app.schemas.notifications import PushSubscriptionIn
from tests.conftest import call_injected


def _empty_subscription_result() -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


@pytest.mark.asyncio
async def test_authenticated_subscribe_is_charged_before_dns_and_dns_failure_precedes_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "https://push.example.test/endpoint-secret-marker"
    caller_id = uuid.uuid4()
    request = MagicMock()
    request.client.host = "203.0.113.8"
    request.headers.get.return_value = "synthetic test client"
    payload = PushSubscriptionIn(
        endpoint=endpoint,
        keys={"p256dh": "synthetic-p256dh", "auth": "synthetic-auth"},
    )
    events: list[tuple[str, str]] = []
    database = AsyncMock()
    database.add = MagicMock()

    async def charge_caller(**kwargs: object) -> None:
        events.append(("rate_limit", str(kwargs["identifier"])))

    async def fail_dns(candidate: str) -> None:
        events.append(("dns", candidate))
        raise ValueError("DNS resolution failed: synthetic resolver outage")

    monkeypatch.setattr(notifications, "resolve_locale", lambda **_kwargs: "en")
    monkeypatch.setattr(notifications, "get_default_strategy", lambda name: name)
    monkeypatch.setattr(notifications, "enforce_rate_limit", charge_caller)
    monkeypatch.setattr(notifications, "_validate_public_endpoint_dns", fail_dns)
    monkeypatch.setattr(
        notifications, "settings", SimpleNamespace(is_development=False)
    )

    with pytest.raises(HTTPException) as exc:
        await call_injected(
            notifications.subscribe,
            payload=payload,
            request=request,
            user=SimpleNamespace(id=caller_id),
            provides={"AsyncDatabaseSession": database},
        )

    assert exc.value.status_code == 400
    assert events == [
        ("rate_limit", f"user:{caller_id}"),
        ("rate_limit", "ip:203.0.113.8"),
        ("dns", endpoint),
    ]
    database.execute.assert_not_awaited()
    database.add.assert_not_called()
    database.flush.assert_not_awaited()
    database.commit.assert_not_awaited()
    database.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_development", "dns_error", "accepted"),
    [
        (True, "DNS resolution failed: synthetic placeholder host", True),
        (False, "DNS resolution failed: synthetic resolver outage", False),
        (True, "resolved endpoint is not globally routable", False),
    ],
)
async def test_dns_placeholder_exception_is_tolerated_only_in_development(
    monkeypatch: pytest.MonkeyPatch,
    is_development: bool,
    dns_error: str,
    accepted: bool,
) -> None:
    endpoint = "https://push.example.test/placeholder-fixture"
    payload = PushSubscriptionIn(
        endpoint=endpoint,
        keys={"p256dh": "synthetic-p256dh", "auth": "synthetic-auth"},
    )
    resolver = AsyncMock(side_effect=ValueError(dns_error))
    monkeypatch.setattr(notifications, "_validate_public_endpoint_dns", resolver)
    monkeypatch.setattr(
        notifications, "settings", SimpleNamespace(is_development=is_development)
    )

    if accepted:
        result = await notifications._validate_subscription_payload(
            payload, locale="en"
        )
        assert result == (endpoint, "synthetic-p256dh", "synthetic-auth")
    else:
        with pytest.raises(HTTPException) as exc:
            await notifications._validate_subscription_payload(payload, locale="en")
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "invalid_subscription"

    resolver.assert_awaited_once_with(endpoint)


@pytest.mark.asyncio
async def test_integrity_failure_logs_fingerprint_without_raw_endpoint_or_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "endpoint-secret-marker-" + uuid.uuid4().hex
    endpoint = f"https://push.example.com/{token}"
    auth_marker = "synthetic-auth-secret-marker"
    payload = PushSubscriptionIn(
        endpoint=endpoint,
        keys={"p256dh": "synthetic-p256dh", "auth": auth_marker},
    )
    request = MagicMock()
    request.client = None
    request.headers.get.return_value = None
    database = AsyncMock()
    database.add = MagicMock()
    database.execute.side_effect = [_empty_subscription_result() for _ in range(4)]
    integrity_errors = [
        IntegrityError(
            f"INSERT subscription endpoint={endpoint}",
            {"endpoint": endpoint, "auth": auth_marker},
            RuntimeError(f"synthetic duplicate for {endpoint}"),
        )
        for _ in range(3)
    ]
    assert all(endpoint in str(error) for error in integrity_errors)
    database.flush = AsyncMock(side_effect=integrity_errors)
    mock_logger = MagicMock()
    monkeypatch.setattr(notifications, "logger", mock_logger)
    monkeypatch.setattr(notifications, "resolve_locale", lambda **_kwargs: "en")

    with (
        patch.object(
            notifications,
            "_validate_subscription_payload",
            new=AsyncMock(return_value=(endpoint, "synthetic-p256dh", auth_marker)),
        ),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(
            notifications, "get_default_strategy", side_effect=lambda name: name
        ),
        patch.object(notifications.asyncio, "sleep", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await call_injected(
                notifications.subscribe,
                payload=payload,
                request=request,
                user=SimpleNamespace(id=uuid.uuid4()),
                provides={"AsyncDatabaseSession": database},
            )

    logged_calls = str(mock_logger.mock_calls)
    assert exc.value.status_code == 409
    assert endpoint not in logged_calls
    assert token not in logged_calls
    assert auth_marker not in logged_calls
    assert "endpoint_prefix" not in logged_calls
    assert sha256(endpoint.encode("utf-8")).hexdigest()[:12] in logged_calls
    assert endpoint not in str(exc.value.detail)
    assert database.rollback.await_count == 3
    database.commit.assert_not_awaited()
