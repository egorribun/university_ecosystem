from __future__ import annotations

from app.core.ratelimit.cleanup import (
    start_memory_cleanup_task,
    stop_memory_cleanup_task,
)
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.delay import (
    PROGRESSIVE_DELAY_MAX,
    PROGRESSIVE_DELAY_STEPS,
    PROGRESSIVE_DELAY_TTL,
    ProgressiveDelayTracker,
    clear_delay_memory,
)
from app.core.ratelimit.exceptions import RateLimitExceeded
from app.core.ratelimit.fastapi import (
    get_progressive_delay_tracker,
    sensitive_route_limit,
)
from app.core.ratelimit.logic import (
    check_rate_limit,
    enforce_rate_limit,
    get_default_strategy,
)
from app.core.ratelimit.middleware import RateLimitMiddleware
from app.core.ratelimit.models import (
    EndpointRateLimit,
    ProgressiveDelayInfo,
    RateLimitInfo,
)
from app.core.ratelimit.strategies.base import (
    get_shared_client,
    set_rate_limit_client_factory,
)
from app.core.ratelimit.strategies.memory import (
    MemorySlidingWindowStrategy,
    clear_memory_state,
)
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import (
    compose_identifier,
    parse_rate_limit,
    resolve_client_ip,
)

__all__ = [
    "PROGRESSIVE_DELAY_MAX",
    "PROGRESSIVE_DELAY_STEPS",
    "PROGRESSIVE_DELAY_TTL",
    "EndpointRateLimit",
    "MemorySlidingWindowStrategy",
    "ProgressiveDelayInfo",
    "ProgressiveDelayTracker",
    "RateLimitExceeded",
    "RateLimitInfo",
    "RateLimitMiddleware",
    "RateLimitStrategy",
    "RedisSlidingWindowStrategy",
    "check_rate_limit",
    "clear_delay_memory",
    "clear_memory_state",
    "compose_identifier",
    "enforce_rate_limit",
    "get_default_strategy",
    "get_progressive_delay_tracker",
    "get_shared_client",
    "parse_rate_limit",
    "resolve_client_ip",
    "sensitive_route_limit",
    "set_rate_limit_client_factory",
    "start_memory_cleanup_task",
    "stop_memory_cleanup_task",
]
