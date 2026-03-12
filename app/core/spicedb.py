"""SpiceDB client provider.

Provides two interfaces:
- ``get_spicedb_client()``: legacy synchronous authzed.Client, kept for any
  remaining sync callers (CLI, management commands).
- ``get_async_spicedb_channel()``: async-native grpc.aio.Channel for use in
  FastAPI route handlers and async services. Calling synchronous gRPC stubs
  inside the asyncio event loop blocks the entire process — this factory
  resolves that P0 issue (RZ-1: audit 2026-02-26).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urlparse

from authzed.api.v1 import Client, InsecureClient

from app.core.config import settings

logger = logging.getLogger(__name__)


def _parse_endpoint(raw_endpoint: str) -> tuple[str, int, bool]:
    """Return (host, port, use_ssl) from a raw SpiceDB endpoint string."""
    if "://" not in raw_endpoint:
        parsed = urlparse(f"grpc://{raw_endpoint}")
        host: str = parsed.hostname or raw_endpoint
        port: int = parsed.port or 50051
        use_ssl = False
    else:
        parsed = urlparse(raw_endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 50051)
        use_ssl = parsed.scheme in ("https", "grpcs")

    allow_insecure = os.getenv("SPICEDB_INSECURE", "false").lower() == "true"
    # Force TLS unless explicitly opted out — plaintext transmits the PSK in clear.
    use_ssl = use_ssl or not allow_insecure
    return host, port, use_ssl


# ---------------------------------------------------------------------------
# Synchronous client (legacy, kept for CLI / management commands only)
# ---------------------------------------------------------------------------


class SpiceDBClient:
    """Synchronous SpiceDB client wrapper using authzed-python.

    DO NOT use inside async route handlers — use get_async_spicedb_channel().
    """

    def __init__(self) -> None:
        self.client: Client | None = None
        self._token = settings.spicedb_preshared_key
        self._endpoint = settings.spicedb_endpoint

    def _init_client(self) -> Client:
        if self.client:
            return self.client

        if not self._token:
            logger.warning(
                "SPICEDB_PRESHARED_KEY is not set. SpiceDB integration will fail."
            )

        host, port, use_ssl = _parse_endpoint(self._endpoint)
        target = f"{host}:{port}"

        if use_ssl:
            from grpcutil import bearer_token_credentials

            logger.info("SpiceDB (sync): connecting with TLS to %s", target)
            self.client = Client(
                target=target,
                credentials=bearer_token_credentials(self._token),
            )
        else:
            logger.warning(
                "SpiceDB (sync): connecting WITHOUT TLS to %s. "
                "Only acceptable in local dev (SPICEDB_INSECURE=true).",
                target,
            )
            self.client = InsecureClient(target=target, token=self._token)
        return self.client

    def get_client(self) -> Client:
        return self._init_client()


@lru_cache
def get_spicedb_client() -> Client:
    """Singleton synchronous SpiceDB client — CLI / management use only."""
    return SpiceDBClient().get_client()


# ---------------------------------------------------------------------------
# Async channel factory (for use in FastAPI route handlers and async services)
# RZ-1: audit 2026-02-26 — replaces the blocking sync gRPC call in rbac.py
# ---------------------------------------------------------------------------


async def get_async_spicedb_channel() -> AsyncIterator[object]:
    """Yield an async-native grpc.aio.Channel for the duration of a request.

    The channel is closed when the generator is exhausted (Dishka REQUEST scope
    cleans up after each request). A new connection is established per-request;
    grpc.aio handles HTTP/2 multiplexing internally so this is cost-effective.

    Usage with Dishka:
        @provide(scope=Scope.REQUEST)
        async def spicedb_channel(self) -> AsyncIterator[AsyncSpiceDBChannel]:
            async for ch in get_async_spicedb_channel():
                yield ch
    """
    import grpc

    host, port, use_ssl = _parse_endpoint(settings.spicedb_endpoint)
    target = f"{host}:{port}"
    token = settings.spicedb_preshared_key

    if use_ssl:
        from grpcutil import bearer_token_credentials

        credentials = bearer_token_credentials(token)
        channel = grpc.aio.secure_channel(target, credentials)
    else:
        channel = grpc.aio.insecure_channel(target)

    logger.debug("SpiceDB async channel opened: %s:%s ssl=%s", host, port, use_ssl)
    try:
        yield channel
    finally:
        await channel.close()
        logger.debug("SpiceDB async channel closed: %s:%s", host, port)
