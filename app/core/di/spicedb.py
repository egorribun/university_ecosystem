"""SpiceDB Dishka DI provider.

TD-14-05 (audit 2026-03-18): Promote the gRPC channel to Scope.APP so it is
opened once at startup and reused across all requests via HTTP/2 multiplexing,
rather than performing a TCP+TLS handshake on every permission check.

The PermissionChecker itself remains Scope.REQUEST because it holds
per-call context; it simply receives the shared singleton channel.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from dishka import Provider, Scope, provide

logger = logging.getLogger(__name__)


class SpiceDBProvider(Provider):
    """Provides the SpiceDB gRPC channel at APP scope and PermissionChecker at REQUEST scope.

    Channel lifecycle:
    - Opened once when the Dishka container starts (app startup).
    - Shared across all requests via HTTP/2 stream multiplexing.
    - Closed cleanly when the container shuts down (app shutdown).

    This eliminates the TCP+TLS handshake cost on every permission check
    (TD-14-05) while keeping the PermissionChecker decoupled from transport.
    """

    @provide(scope=Scope.APP)
    async def spicedb_channel(self) -> AsyncIterator[Any]:
        """Singleton async gRPC channel — opened once per app process.

        Yields:
            grpc.aio.Channel connected to SpiceDB (TLS or insecure based on config).
        """
        import grpc

        from app.core.config import settings
        from app.core.spicedb import _parse_endpoint

        host, port, use_ssl = _parse_endpoint(settings.spicedb_endpoint)
        target = f"{host}:{port}"
        token = settings.spicedb_preshared_key

        # TD-W5-08 / Wave 13: keepalive options detect dead connections quickly.
        _KEEPALIVE_OPTIONS = [
            ("grpc.keepalive_time_ms", 10_000),
            ("grpc.keepalive_timeout_ms", 5_000),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.max_reconnect_backoff_ms", 5_000),
            ("grpc.http2.min_time_between_pings_ms", 10_000),
        ]

        if use_ssl:
            from grpcutil import bearer_token_credentials  # type: ignore[import]

            credentials = bearer_token_credentials(token)
            channel = grpc.aio.secure_channel(
                target, credentials, options=_KEEPALIVE_OPTIONS
            )
        else:
            channel = grpc.aio.insecure_channel(target, options=_KEEPALIVE_OPTIONS)

        logger.info(
            "SpiceDB singleton channel opened: %s (ssl=%s)",
            target,
            use_ssl,
        )
        try:
            yield channel
        finally:
            await channel.close()
            logger.info("SpiceDB singleton channel closed: %s", target)

    @provide(scope=Scope.REQUEST)
    def permission_checker(self, channel: Any) -> Any:
        """Construct a PermissionChecker for this request using the singleton channel.

        Returns:
            PermissionChecker wired to the APP-scoped gRPC channel.
        """
        from app.auth.rbac import PermissionChecker

        return PermissionChecker(channel)
