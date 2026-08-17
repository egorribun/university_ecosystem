from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import Request
from prometheus_client import Counter
from starlette.responses import JSONResponse, Response

from app.core.exceptions.handlers import asgi_json_problem
from app.core.localization import resolve_locale
from app.core.ratelimit.contract import RateLimitStrategy
from app.core.ratelimit.models import EndpointRateLimit, RateLimitInfo
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy
from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy
from app.core.ratelimit.utils import resolve_client_ip

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.security.ratelimit")

_rate_limit_fallback_total = Counter(
    "rate_limit_fallback_total",
    "Times rate limiter fell back from primary strategy (PERF-27-03)",
    ["reason"],
)


class RateLimitMiddleware:
    """Pure ASGI rate-limiting middleware."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_url: str | None = None,
        limit: int = 120,
        window_seconds: int = 60,
        enabled: bool = True,
        headers_enabled: bool = True,
        storage_backend: str = "redis",
        endpoint_limits: tuple[EndpointRateLimit, ...] | None = None,
    ) -> None:
        self._app = app
        backend = (storage_backend or "redis").strip().lower()
        self._storage_backend = backend
        self._redis_url = (redis_url or "").strip() if backend == "redis" else ""
        self._limit = max(int(limit), 0)
        self._window_seconds = max(int(window_seconds), 0)
        self._enabled = enabled and self._limit > 0 and self._window_seconds > 0
        self._headers_enabled = headers_enabled
        self._endpoint_limits = endpoint_limits or ()
        self._namespace = f"middleware:{uuid.uuid4().hex}"

        if self._storage_backend == "redis":
            self._strategy: RateLimitStrategy = RedisSlidingWindowStrategy(
                self._redis_url
            )
        else:
            self._strategy = MemorySlidingWindowStrategy(self._namespace)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method.upper()
        path = request.url.path or ""

        if method == "HEAD" and self._is_static_like_path(path):
            response = Response(status_code=200)
            await response(scope, receive, send)
            return

        if not self._enabled or self._should_skip(method, path):
            await self._app(scope, receive, send)
            return

        path_limit, path_window, path_pattern = self._get_limits_for_path(path)
        base_identifier = self._build_identifier(request)
        identifier = (
            f"{base_identifier}:{path_pattern}" if path_pattern else base_identifier
        )

        try:
            # Compatibility shim: call an internal method that tests might monkeypatch.
            # In regular operation, this just proxies to the strategy.
            info = await self._check_limit(identifier, path_limit, path_window)
        except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — falls back to stricter in-memory limiter (reviewed TD-27-04)
            # HIGH-05 (audit 2026-03-11): Fail-CLOSED with in-memory fallback.
            # Previous fail-open behavior allowed rate limit bypass if Redis was down.
            # We now switch to a local memory strategy with stricter limits (50%).
            if self._storage_backend == "redis":
                logger.warning(
                    "Redis rate limiting unavailable, falling back to in-memory (fail-closed)"
                )
                _rate_limit_fallback_total.labels(
                    reason="redis_unavailable"
                ).inc()  # PERF-27-03
                # Stricter local limit to prevent resource exhaustion during Redis outage
                fallback_limit = max(path_limit // 2, 1)
                fallback_strategy = MemorySlidingWindowStrategy(
                    f"{self._namespace}:fallback"
                )
                info = await fallback_strategy.check(
                    identifier, fallback_limit, path_window
                )
                if not info.allowed:
                    logger.error(
                        "Rate limit exceeded (fallback-mode): identifier=%s, path=%s",
                        identifier,
                        path,
                    )
            else:
                # RZ-27-03: Double-failure path (Redis + memory). Fail-closed with
                # 503 to prevent rate-limit bypass. Log at ERROR for alerting.
                logger.error(
                    "Rate limiting fully unavailable (Redis + memory fallback failed) "
                    "— failing closed with 503",
                    extra={"identifier": identifier, "path": path},
                )
                _rate_limit_fallback_total.labels(
                    reason="double_failure"
                ).inc()  # PERF-27-03
                response = JSONResponse(
                    {"detail": "Service temporarily unavailable"},
                    status_code=503,
                    headers={"Retry-After": "30"},
                )
                await response(scope, receive, send)
                return

        if not info.allowed:
            logger.warning(
                "Rate limit exceeded: identifier=%s, path=%s, limit=%d",
                identifier,
                path,
                path_limit,
            )
            retry_after_seconds = max(0, info.retry_after)
            headers = {"Retry-After": str(retry_after_seconds)}
            if self._headers_enabled:
                headers["X-RateLimit-Limit"] = str(path_limit)
                headers["X-RateLimit-Remaining"] = "0"
                headers["X-RateLimit-Reset"] = str(
                    int(time.time()) + retry_after_seconds
                )

            locale = resolve_locale(request=request)
            # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string
            await asgi_json_problem(
                send,
                status_code=429,
                title_key="titles.rate_limit_exceeded",
                detail_key="errors.rate_limit.generic",
                locale=locale,
                instance=str(request.url),
                headers=headers,
            )
            return

        if self._headers_enabled:
            remaining = str(max(0, info.remaining))
            limit_str = str(path_limit)

            async def send_with_headers(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers_list = list(message.get("headers", []))
                    existing_names = {h[0].lower() for h in headers_list}
                    if b"x-ratelimit-limit" not in existing_names:
                        headers_list.append((b"x-ratelimit-limit", limit_str.encode()))
                    if b"x-ratelimit-remaining" not in existing_names:
                        headers_list.append(
                            (b"x-ratelimit-remaining", remaining.encode())
                        )
                    message = {**message, "headers": headers_list}
                await send(message)

            await self._app(scope, receive, send_with_headers)
        else:
            await self._app(scope, receive, send)

    def _get_limits_for_path(self, path: str) -> tuple[int, int, str]:
        for endpoint_limit in self._endpoint_limits:
            if path.startswith(endpoint_limit.pattern):
                return (
                    endpoint_limit.limit,
                    endpoint_limit.window_seconds,
                    endpoint_limit.pattern,
                )
        return self._limit, self._window_seconds, "default"

    def _build_identifier(self, request: Request) -> str:
        """Build a unique identifier for the request.
        Prioritizes Authorization header, then access_token cookie, then IP.
        """
        # RATE-1 (audit 2026-03): Never store the raw JWT as a Redis key.
        # A 500-char JWT in the keyspace reveals token material to any process
        # with Redis keyspace-notification access (Pub/Sub, RedisInsight, etc.).
        # SHA-256 of the token is collision-resistant and exposes nothing.
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if token:
                token_digest = hashlib.sha256(token.encode()).hexdigest()
                return f"token:{token_digest}"

        cookie = request.cookies.get(
            "access_token_v2"
        )  # RZ-33-04: match canonical cookie name
        if cookie:
            cookie_digest = hashlib.sha256(cookie.encode()).hexdigest()
            redis_identifier = "cookie:" + cookie_digest
            return redis_identifier  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string

        ip = resolve_client_ip(request)
        return f"ip:{ip}"

    # MED-W19: Paths that are always exempt from rate limiting (health/metrics).
    _HEALTH_PATHS: frozenset[str] = frozenset({"/", "/healthz", "/ready", "/metrics"})

    def _should_skip(self, method: str, path: str) -> bool:
        if method == "OPTIONS":
            return True
        # MED-W19: Only skip HEAD for health/metrics endpoints, not all endpoints.
        # Previously all HEAD requests bypassed rate limiting, allowing attackers
        # to probe endpoints at unlimited speed using HEAD to avoid logging.
        if path in self._HEALTH_PATHS:
            return True
        return bool(self._is_static_like_path(path) and method in {"GET", "HEAD"})

    async def _check_limit(
        self, identifier: str, limit: int, window: int
    ) -> RateLimitInfo:
        """Internal method to allow monkeypatching in tests."""
        return await self._strategy.check(identifier, limit, window)

    @staticmethod
    def _is_static_like_path(path: str) -> bool:
        return path.startswith(("/static/", "/media/", "/storage/", "/assets/"))
