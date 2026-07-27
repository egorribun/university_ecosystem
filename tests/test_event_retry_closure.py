"""Branch closure tests for event retry middleware."""

from types import SimpleNamespace

import pytest

from app.core.event_retry import RetryMiddleware


@pytest.mark.asyncio
async def test_retry_metadata_without_retry_count_is_left_untouched():
    event = SimpleNamespace(event_type="metadata-edge", metadata=SimpleNamespace())

    async def handle(_event):
        return None

    await RetryMiddleware(max_retries=0)(event, handle)

    assert not hasattr(event.metadata, "retry_count")


@pytest.mark.asyncio
async def test_negative_retry_budget_exits_without_an_error():
    event = SimpleNamespace(event_type="empty-budget")

    await RetryMiddleware(max_retries=-1)(event, lambda _event: None)
