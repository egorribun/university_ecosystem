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

import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import nats
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

from app.core.logging import get_logger
from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from nats.aio.client import Client as NatsClient
    from nats.js import JetStreamContext

logger = get_logger(__name__)


@dataclass
class NatsMessage:
    """Wrapper for NATS message with convenience methods."""

    subject: str
    data: bytes
    reply: str | None = None
    headers: dict[str, str] | None = None

    def json(self) -> dict[str, Any]:
        """Decode message data as JSON."""
        from typing import cast

        return cast("dict[str, Any]", orjson.loads(self.data))


class NatsService:
    """Async NATS client with JetStream support."""

    def __init__(
        self,
        servers: list[str] | str = "nats://localhost:4222",
        name: str = "university-ecosystem",
        auth_token: str | None = None,
    ) -> None:
        self._servers = [servers] if isinstance(servers, str) else servers
        self._name = name
        self._auth_token = auth_token
        self._client: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._subscriptions: list[Any] = []

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Connect to NATS server(s)."""
        if self.is_connected:
            return

        connect_options: dict[str, Any] = {
            "servers": self._servers,
            "name": self._name,
            "reconnect_time_wait": 2,
            "max_reconnect_attempts": -1,
        }
        if self._auth_token:
            connect_options["token"] = self._auth_token
        self._client = await nats.connect(
            **connect_options,
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
        max_age: int = 604_800,  # 7 days in seconds
    ) -> None:
        """Create or update a JetStream stream.

        Args:
            name: Stream name
            subjects: List of subjects to capture
            max_age: Maximum message age in seconds (default: 7 days = 604,800s)
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        try:
            await self._js.add_stream(
                config=StreamConfig(
                    name=name,
                    subjects=subjects,
                    storage=StorageType.FILE,
                    retention=RetentionPolicy.LIMITS,
                    max_age=max_age,
                )
            )
            logger.info("Created/updated stream: %s", name)
        except (
            nats.errors.Error,
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:  # RZ-20-04: Narrowed — NATS stream setup is idempotent.
            logger.warning("Stream setup issue: %s", exc)

    async def publish(
        self,
        subject: str,
        data: bytes | dict[str, Any],
        headers: dict[str, str] | None = None,
        msg_id: str | None = None,
    ) -> None:
        """Publish a message to a subject.

        Args:
            subject: NATS subject
            data: Message data (bytes or dict to be JSON encoded)
            headers: Optional message headers
            msg_id: Optional deduplication message ID
        """
        if not self._client:
            raise RuntimeError("Not connected to NATS")

        msg_headers: dict[str, str] = headers.copy() if headers else {}
        dedup_id = msg_id
        if not dedup_id and isinstance(data, dict):
            dedup_id = data.get("id") or data.get("event_id")
        if not dedup_id:
            dedup_id = str(uuid.uuid4())
        msg_headers["Nats-Msg-Id"] = str(dedup_id)

        if isinstance(data, dict):
            data = orjson.dumps(data)

        await self._client.publish(subject, data, headers=msg_headers)
        logger.debug("Published to %s", subject)

    async def publish_jetstream(
        self,
        subject: str,
        data: bytes | dict[str, Any],
        headers: dict[str, str] | None = None,
        msg_id: str | None = None,
    ) -> None:
        """Publish a message with JetStream acknowledgment.

        Args:
            subject: NATS subject (must be in a stream)
            data: Message data
            headers: Optional message headers
            msg_id: Optional deduplication message ID
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        msg_headers: dict[str, str] = headers.copy() if headers else {}
        dedup_id = msg_id
        if not dedup_id and isinstance(data, dict):
            dedup_id = data.get("id") or data.get("event_id")
        if not dedup_id:
            dedup_id = str(uuid.uuid4())
        msg_headers["Nats-Msg-Id"] = str(dedup_id)

        if isinstance(data, dict):
            data = orjson.dumps(data)

        ack = await self._js.publish(subject, data, headers=msg_headers)
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

        async def _wrapper(msg: Any) -> None:
            wrapped = NatsMessage(
                subject=msg.subject,
                data=msg.data,
                reply=msg.reply,
                headers=dict(msg.headers) if msg.headers else None,
            )
            await handler(wrapped)

        sub = await self._client.subscribe(subject, queue=queue or "", cb=_wrapper)
        self._subscriptions.append(sub)
        logger.info("Subscribed to %s (queue=%s)", subject, queue)

    async def subscribe_jetstream(
        self,
        stream: str,
        subject: str,
        handler: Callable[[NatsMessage], Coroutine[Any, Any, None]],
        durable: str | None = None,
        max_deliver: int = 5,
    ) -> None:
        """Subscribe to a JetStream subject with acknowledgment.

        Args:
            stream: Stream name
            subject: Subject pattern
            handler: Async function to handle messages
            durable: Durable consumer name for persistence
            max_deliver: Maximum delivery attempts before a message is considered
                a dead-letter (poison message).  Defaults to 5.  Without this
                cap, a handler that always raises will cause NATS to re-deliver
                indefinitely, starving healthy messages and exhausting resources.
                LOW-W19: poison-message guard — set max_deliver so that
                permanently-failing messages are moved to the dead-letter stream
                after ``max_deliver`` attempts rather than looping forever.
        """
        if not self._js:
            raise RuntimeError("Not connected to NATS")

        async def _wrapper(msg: Any) -> None:
            headers = dict(msg.header) if msg.header else None
            wrapped = NatsMessage(
                subject=msg.subject,
                data=msg.data,
                headers=headers,
                reply=msg.reply,
            )
            try:
                await handler(wrapped)
                await msg.ack()
            except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — NAKs message for retry (reviewed TD-27-04)
                # RZ-20-04: KEEP broad catch — handlers are user-defined callbacks;
                # any unhandled exception must nak() the message, never crash the
                # subscription loop. Logged at ERROR for Sentry pickup.
                logger.error("Handler error: %s", exc)
                await msg.nak()

        from nats.js.api import ConsumerConfig

        sub = await self._js.subscribe(
            subject,
            stream=stream,
            durable=durable,
            config=ConsumerConfig(max_deliver=max_deliver),
            cb=_wrapper,
        )
        self._subscriptions.append(sub)
        logger.info("Subscribed to JetStream %s/%s", stream, subject)


# Singleton instance
_nats_service: NatsService | None = None
_nats_service_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01


def get_nats_service() -> NatsService:
    """Get the configured NATS service instance."""
    global _nats_service
    if _nats_service is not None:  # RZ-33-29: fast path — no lock after init
        return _nats_service
    with _nats_service_lock:  # RZ-33-29: slow path — double-checked locking
        if _nats_service is None:
            from app.core.config import settings

            _nats_service = NatsService(
                servers=settings.nats_url,
                auth_token=settings.nats_auth_token,
            )
        return _nats_service


__all__ = ["NatsMessage", "NatsService", "get_nats_service"]
