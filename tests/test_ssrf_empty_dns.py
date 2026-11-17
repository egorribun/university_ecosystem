"""DNS validation must fail closed when a resolver returns no addresses."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.ssrf import (
    _check_resolved,
    validate_url_not_internal,
    validate_url_not_internal_async,
)


def test_resolved_guard_rejects_empty_answer() -> None:
    with pytest.raises(ValueError, match="SSRF blocked: no valid addresses"):
        _check_resolved("example.test", [])


def test_sync_validator_rejects_empty_answer() -> None:
    with patch("app.core.ssrf.socket.getaddrinfo", return_value=[]):
        with pytest.raises(ValueError, match="SSRF blocked: no valid addresses"):
            validate_url_not_internal("https://example.test/resource")


@pytest.mark.asyncio
async def test_async_validator_rejects_empty_answer() -> None:
    loop = AsyncMock()
    loop.getaddrinfo.return_value = []
    with patch("app.core.ssrf.asyncio.get_running_loop", return_value=loop):
        with pytest.raises(ValueError, match="SSRF blocked: no valid addresses"):
            await validate_url_not_internal_async("https://example.test/resource")
    loop.getaddrinfo.assert_awaited_once_with("example.test", None)
