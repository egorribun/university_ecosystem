"""
Compatibility shim: re-exports the public API of ``app.core.ratelimit``.

The actual implementation lives in ``app.core.ratelimit`` (decomposed in audit 2026-02-27).
This file exists solely so legacy import sites (``from app.core.rate_limit import ...``)
continue to work without modification.

TD-03 (audit 2026-03-04): MIGRATION DEADLINE Q3 2026
  1. Update all import sites to ``from app.core.ratelimit import ...``.
  2. Replace custom sliding-window + progressive-delay logic with ``slowapi 0.2``
     (see audit MOD-02). Estimated saving: ~1 800 lines removed.
  3. Delete this file.
Tracking: add a GitHub issue and link it here before EOD.
"""
# ruff: noqa

from __future__ import (
    annotations,  # Kept original as `from __future__ import asyncio` is syntactically incorrect
)

import time
from typing import Any


from app.core.config import settings as _settings
from app.core.ratelimit import (
    PROGRESSIVE_DELAY_MAX,
    PROGRESSIVE_DELAY_STEPS,
    PROGRESSIVE_DELAY_TTL,
    EndpointRateLimit,
    MemorySlidingWindowStrategy,
    ProgressiveDelayInfo,
    ProgressiveDelayTracker,
    RateLimitExceeded,
    RateLimitInfo,
    # RateLimitMiddleware intentionally omitted — subclassed and re-exported below
    RateLimitStrategy,
    RedisSlidingWindowStrategy,
    check_rate_limit,
    clear_delay_memory,
    clear_memory_state,
    compose_identifier,
    enforce_rate_limit,
    get_default_strategy,
    get_progressive_delay_tracker,
    get_shared_client,
    parse_rate_limit,
    resolve_client_ip,
    sensitive_route_limit,
    set_rate_limit_client_factory,
    start_memory_cleanup_task,
    stop_memory_cleanup_task,
)

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


class RateLimitMiddleware(_RateLimitMiddleware):
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
        return await super()._check_limit(
            identifier, limit or 100, window_seconds or 60
        )


class _Limiter:
    """Shim for legacy tests."""

    def reset(self) -> None:
        # RZ-06 (audit 2026-03-04): Do NOT create an asyncio.Task here.
        # Under pytest with per-test event loops the task would target a dead loop
        # from the previous test, leaving rate-limit counters dirty (spurious 429s).
        # clear_memory_state / clear_delay_memory are fully synchronous — no I/O.
        from app.core.ratelimit import clear_delay_memory, clear_memory_state

        clear_memory_state()
        clear_delay_memory()

    async def check(self, *args, **kwargs) -> None:
        """Mock-ready check method."""
        pass


limiter = _Limiter()



async def clear_all_rate_limit_memory() -> None:
    """Legacy compatibility function."""
    from app.core.ratelimit import clear_delay_memory, clear_memory_state

    clear_memory_state()
    clear_delay_memory()


def reset_for_testing() -> None:
    """Reset all in-process rate-limit and progressive-delay state.

    P3-fix (audit 2026-02-26): Stable, documented public API for tests to reset
    state without importing private symbols (``_memory_locks``, ``_memory_windows``,
    ``_progressive_delay_memory``, etc.). Tests should call this from setUp /
    conftest fixtures instead of monkeypatching internal variables directly.

    Synchronous — safe to call from both sync and async test bodies.
    """
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


# Public API re-exported from this backward-compat shim.
# TODO: migrate callers to import directly from app.core.ratelimit and remove this file.
__all__ = [
    # Core middleware & strategy types
    "RateLimitMiddleware",
    "RateLimitStrategy",
    "RateLimitExceeded",
    # Model types
    "EndpointRateLimit",
    "RateLimitInfo",
    "ProgressiveDelayInfo",
    "ProgressiveDelayTracker",
    # Strategy implementations
    "MemorySlidingWindowStrategy",
    "RedisSlidingWindowStrategy",
    # Public functions
    "check_rate_limit",
    "enforce_rate_limit",
    "get_default_strategy",
    "get_progressive_delay_tracker",
    "get_shared_client",
    "set_rate_limit_client_factory",
    "compose_identifier",
    "parse_rate_limit",
    "resolve_client_ip",
    "sensitive_route_limit",
    "start_memory_cleanup_task",
    "stop_memory_cleanup_task",
    "clear_memory_state",
    "clear_delay_memory",
    # Testing utility (stable public API)
    "reset_for_testing",
    "clear_all_rate_limit_memory",
]
