"""Focused coverage for app-level handlers and root endpoint."""

import pytest
from fastapi import HTTPException, Request

from app.core.ratelimit.exceptions import RateLimitExceeded
from app.core.ratelimit.models import RateLimitInfo
from app.main import (
    _rate_limit_exceeded_handler,
    _rate_limit_storage_unavailable_handler,
    get_root,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.mark.asyncio
async def test_rate_limit_storage_handler_returns_retryable_503():
    response = await _rate_limit_storage_unavailable_handler(object(), Exception())

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


@pytest.mark.asyncio
async def test_rate_limit_exceeded_handler_returns_localized_429_with_retry():
    response = await _rate_limit_exceeded_handler(
        _request(), RateLimitExceeded(RateLimitInfo(False, 0, 12))
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "12"


@pytest.mark.asyncio
async def test_rate_limit_exceeded_handler_omits_zero_retry_header():
    response = await _rate_limit_exceeded_handler(
        _request(), RateLimitExceeded(RateLimitInfo(False, 0, 0))
    )

    assert response.status_code == 429
    assert "retry-after" not in response.headers


@pytest.mark.asyncio
async def test_rate_limit_exceeded_handler_delegates_unexpected_exception():
    response = await _rate_limit_exceeded_handler(
        _request(), HTTPException(status_code=418, detail="fallback")
    )

    assert response.status_code == 418


@pytest.mark.asyncio
async def test_root_returns_ok():
    response = await get_root()

    assert response.status_code == 200
    assert response.body == b'{"status":"ok"}'
