"""NATS JetStream messaging service client.

This module provides an async client for NATS messaging with JetStream
for reliable message delivery and persistence.

Features:
- Pub/Sub messaging
- JetStream streams for persistence
- Consumer groups for load balancing
- Request/Reply patterns
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import nats
from nats.js.api import StreamConfig

if TYPE_CHECKING:
    from nats.aio.client import Client as NatsClient
    from nats.js import JetStreamContext

logger = logging.getLogger(__name__)


@dataclass
class NatsMessage:
    """Wrapper for NATS message with convenience methods."""

    subject: str
    data: bytes
    reply: str | None = None
    headers: dict[str, str] | None = None

    def json(self) -> dict[str, Any]:
        """Decode message data as JSON."""
        import orjson

        return orjson.loads(self.data)


class NatsService:
    """Async NATS client with JetStream support."""

    def __init__(
        self,
        servers: list[str] | str = "nats://localhost:4222",
        name: str = "university-ecosystem",
    ) -> None:
        self._servers = [servers] if isinstance(servers, str) else servers
        self._name = name
        self._client: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._subscriptions: list = []

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Connect to NATS server(s)."""
        if self.is_connected:
            return

        self._client = await nats.connect(
            servers=self._servers,
            name=self._name,
            reconnect_time_wait=2,
            max_reconnect_attempts=-1,  # Infinite reconnect
        )
        self._js = self._client.jetstream()
        logger.info("Connected to NATS: %s", self._servers)

    async def close(self) -> None:
        """Close NATS connection."""
        if self._client:
            # Unsubscribe all
            for sub in self._subscriptions:
                await sub.unsubscribe()
            self._subscriptions.clear()

            await self._client.drain()
            self._client = None
            self._js = None
            logger.info("NATS connection closed")

    async def ensure_stream(
        self,
        name: str,
        subjects: list[str],
        max_age: int = 86400,  # 1 day in seconds
    ) -> None:
        """Create or update a JetStream stream.

        Args:
            name: Stream name
            subjects: List of subjects to capture
            max_age: Maximum message age in seconds
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        try:
            await self._js.add_stream(
                config=StreamConfig(
                    name=name,
                    subjects=subjects,
                    max_age=max_age * 1_000_000_000,  # nanoseconds
                )
            )
            logger.info("Created/updated stream: %s", name)
        except Exception as exc:
            # Stream might already exist with different config
            logger.warning("Stream setup issue: %s", exc)

    async def publish(
        self,
        subject: str,
        data: bytes | dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish a message to a subject.

        Args:
            subject: NATS subject
            data: Message data (bytes or dict to be JSON encoded)
            headers: Optional message headers
        """
        if not self._client:
            raise RuntimeError("Not connected to NATS")

        if isinstance(data, dict):
            import orjson

            data = orjson.dumps(data)

        await self._client.publish(subject, data, headers=headers)
        logger.debug("Published to %s", subject)

    async def publish_jetstream(
        self,
        subject: str,
        data: bytes | dict[str, Any],
    ) -> None:
        """Publish a message with JetStream acknowledgment.

        Args:
            subject: NATS subject (must be in a stream)
            data: Message data
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        if isinstance(data, dict):
            import orjson

            data = orjson.dumps(data)

        ack = await self._js.publish(subject, data)
        logger.debug("Published to JetStream %s, seq=%d", subject, ack.seq)

    async def subscribe(
        self,
        subject: str,
        handler: Callable[[NatsMessage], Coroutine[Any, Any, None]],
        queue: str | None = None,
    ) -> None:
        """Subscribe to a subject with a message handler.

        Args:
            subject: NATS subject pattern
            handler: Async function to handle messages
            queue: Optional queue group for load balancing
        """
        if not self._client:
            raise RuntimeError("Not connected to NATS")

        async def _wrapper(msg):
            wrapped = NatsMessage(
                subject=msg.subject,
                data=msg.data,
                reply=msg.reply,
                headers=dict(msg.headers) if msg.headers else None,
            )
            await handler(wrapped)

        sub = await self._client.subscribe(subject, queue=queue, cb=_wrapper)
        self._subscriptions.append(sub)
        logger.info("Subscribed to %s (queue=%s)", subject, queue)

    async def subscribe_jetstream(
        self,
        stream: str,
        subject: str,
        handler: Callable[[NatsMessage], Coroutine[Any, Any, None]],
        durable: str | None = None,
    ) -> None:
        """Subscribe to a JetStream subject with acknowledgment.

        Args:
            stream: Stream name
            subject: Subject pattern
            handler: Async function to handle messages
            durable: Durable consumer name for persistence
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        async def _wrapper(msg):
            wrapped = NatsMessage(
                subject=msg.subject,
                data=msg.data,
            )
            try:
                await handler(wrapped)
                await msg.ack()
            except Exception as exc:
                logger.error("Handler error: %s", exc)
                await msg.nak()

        sub = await self._js.subscribe(
            subject,
            stream=stream,
            durable=durable,
            cb=_wrapper,
        )
        self._subscriptions.append(sub)
        logger.info("Subscribed to JetStream %s/%s", stream, subject)


# Singleton instance
_nats_service: NatsService | None = None


def get_nats_service() -> NatsService:
    """Get the configured NATS service instance."""
    global _nats_service
    if _nats_service is None:
        from app.core.config import settings

        servers = getattr(settings, "nats_servers", "nats://localhost:4222")
        _nats_service = NatsService(servers=servers)
    return _nats_service


__all__ = ["NatsService", "NatsMessage", "get_nats_service"]
