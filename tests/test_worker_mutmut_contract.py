from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import worker


@pytest.mark.asyncio
async def test_worker_main_delegates_to_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the NATS worker entrypoint mapped in the full mutmut universe."""

    run_worker = AsyncMock()
    monkeypatch.setattr(worker.broker, "run_worker", run_worker)

    await worker.main()

    run_worker.assert_awaited_once_with()
