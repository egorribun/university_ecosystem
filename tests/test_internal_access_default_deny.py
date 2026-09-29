"""An allow-listed source IP alone must not open internal routes by default."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.internal_access import InternalAccessMiddleware


def _scope() -> dict[str, object]:
    return {
        "type": "http",
        "path": "/internal/callback",
        "headers": [],
        "client": ("10.0.0.7", 4242),
        "method": "POST",
    }


async def _call(middleware: InternalAccessMiddleware) -> list[dict[str, object]]:
    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await middleware(_scope(), AsyncMock(), send)  # type: ignore[arg-type]
    return sent


@pytest.mark.parametrize("explicit", [False, None])
async def test_allowed_ip_without_token_is_denied_unless_fallback_is_enabled(
    explicit: bool | None,
) -> None:
    app = AsyncMock()
    options = {} if explicit is None else {"allow_ip_fallback": explicit}
    middleware = InternalAccessMiddleware(
        app,
        allowed_ips=["10.0.0.7"],
        header_name="X-Internal-Token",
        header_token="secret",
        internal_prefixes=["/internal"],
        **options,
    )

    sent = await _call(middleware)

    app.assert_not_awaited()
    assert middleware.allow_ip_fallback is False
    assert sent[0]["status"] == 403


async def test_allowed_ip_is_accepted_only_when_fallback_is_explicitly_enabled() -> (
    None
):
    app = AsyncMock()
    middleware = InternalAccessMiddleware(
        app,
        allowed_ips=["10.0.0.7"],
        internal_prefixes=["/internal"],
        allow_ip_fallback=True,
    )

    await _call(middleware)

    app.assert_awaited_once()
