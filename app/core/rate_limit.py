"""
Shim for backward compatibility.
The actual implementation has been moved to app.core.ratelimit package.
(Audit 2026-02-27: Decomposition into app.core.ratelimit)
"""
# ruff: noqa

from __future__ import (
    annotations,  # Kept original as `from __future__ import asyncio` is syntactically incorrect
)

import asyncio
import time
from typing import Any

from app.core.config import settings as _settings
from app.core.ratelimit import *

# Explicitly re-export for tests monkeypatching these
settings = _settings
time = time

# Cleanup functions are already exported by *, but we explicitly list them if needed for clarity
# or if tests import them from the shim specifically.
from app.core.ratelimit.delay import (
    PROGRESSIVE_DELAY_MAX as _PDM,
)
from app.core.ratelimit.delay import (
    PROGRESSIVE_DELAY_STEPS as _PDS,
)
from app.core.ratelimit.delay import (
    PROGRESSIVE_DELAY_TTL as _PDT,
)
from app.core.ratelimit.delay import (
    _delay_memory as _pdm,
)
from app.core.ratelimit.delay import (
    _delay_memory_lock as _pdml,
)
from app.core.ratelimit.middleware import RateLimitMiddleware as _RateLimitMiddleware
from app.core.ratelimit.strategies.base import _shared_clients as _sc
from app.core.ratelimit.strategies.base import _shared_clients_write_lock as _scwl
from app.core.ratelimit.strategies.base import get_shared_client as _get_shared_client
from app.core.ratelimit.strategies.memory import _memory_locks as _ml
from app.core.ratelimit.strategies.memory import _memory_windows as _mw

# Forward compatibility aliases for symbols that tests might monkeypatch
_memory_locks = _ml
_memory_counters = _mw  # Legacy name used in tests
_shared_clients = _sc
_shared_clients_write_lock = _scwl
_get_shared_client = _get_shared_client

# Progressive delay aliases for tests
PROGRESSIVE_DELAY_MAX = _PDM
PROGRESSIVE_DELAY_STEPS = _PDS
PROGRESSIVE_DELAY_TTL = _PDT

# Internal delay memory for tests
_progressive_delay_memory = _pdm
_progressive_delay_memory_lock = _pdml


def _calculate_delay(failures: int) -> float:
    """Standalone delay calculation for tests."""
    if failures <= 0:
        return 0.0
    index = failures - 1
    if index < len(PROGRESSIVE_DELAY_STEPS):
        return PROGRESSIVE_DELAY_STEPS[index]
    return PROGRESSIVE_DELAY_MAX


class RateLimitMiddleware(_RateLimitMiddleware):  # type: ignore[no-redef]
    """Alias for backward compatibility."""

    async def _check_limit(
        self,
        identifier: str,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> Any:
        """Legacy internal method used in tests.
        In the new middleware, logic is in __call__ and calls strategy.check.
        """
        return await super()._check_limit(identifier, limit or 100, window_seconds or 60)


class _Limiter:
    """Shim for legacy tests."""

    def reset(self) -> None:
        try:
            from app.core.ratelimit import clear_delay_memory, clear_memory_state

            loop = asyncio.get_running_loop()

            async def _reset():
                clear_memory_state()
                clear_delay_memory()

            task = loop.create_task(_reset())
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)
        except (RuntimeError, ImportError):
            from app.core.ratelimit import clear_delay_memory, clear_memory_state

            # Sync fallback for tests without a running loop
            clear_memory_state()
            clear_delay_memory()

    async def check(self, *args, **kwargs) -> None:
        """Mock-ready check method."""
        pass


_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
limiter = _Limiter()


async def clear_all_rate_limit_memory() -> None:
    """Legacy compatibility function."""
    from app.core.ratelimit import clear_delay_memory, clear_memory_state

    clear_memory_state()
    clear_delay_memory()


# Internal symbols for tests
_TIME_UNITS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


def _redis_rate_limit(*args, **kwargs):
    """Shim for tests monkeypatching the redis execution function."""
    raise NotImplementedError(
        "Direct _redis_rate_limit access is deprecated. "
        "Tests should monkeypatch strategies or logic."
    )
