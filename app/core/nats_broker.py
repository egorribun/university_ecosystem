from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast

import nats
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from app.core.config import settings

P = ParamSpec("P")
R = TypeVar("R")

_logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class NatsTaskBroker:
    """Consolidated background task broker using NATS JetStream. (MOD-3)

    Replaces legacy orchestrators to reduce infrastructure complexity and leverage
    JetStream's durable streams and at-least-once delivery.
    """

    def __init__(self) -> None:
        self._nc: NATS | None = None
        self._js: JetStreamContext | None = None
        self._tasks: dict[str, Callable[..., Any]] = {}
        self._stream_name = "TASK_QUEUE"
        self._subject_prefix = "tasks"

    @property
    def is_connected(self) -> bool:
        """Check if broker is connected to NATS."""
        return self._nc is not None and self._nc.is_connected

    @property
    def js(self) -> JetStreamContext | None:
        """Get the JetStream context."""
        return self._js

    async def connect(self) -> None:
        """Connect to NATS and ensure JetStream is initialized."""
        if self._nc is not None:
            return

        try:
            self._nc = await nats.connect(
                settings.nats_url,
                # Fail immediately on initial connect rather than retrying forever.
                # With the default max_reconnect_attempts=-1 the nats-py client enters
                # an infinite retry loop that asyncio.wait_for cannot reliably cancel
                # in Python 3.13 + uvloop, blocking lifespan startup.
                # After a successful initial connection, disconnects are handled by the
                # caller (enqueue() re-calls connect() on the next use).
                max_reconnect_attempts=0,
                connect_timeout=2,
            )
            self._js = self._nc.jetstream()

            # Ensure stream exists
            await self._js.add_stream(
                name=self._stream_name,
                subjects=[f"{self._subject_prefix}.>"],
            )
            _logger.info("Connected to NATS JetStream for task processing")
        except Exception as exc:
            _logger.error("Failed to connect to NATS: %s", exc)
            raise

    async def close(self) -> None:
        """Close NATS connection."""
        try:
            if self._nc and self._nc.is_connected:
                await self._nc.close()
        except Exception as exc:
            _logger.warning("Error during NATS closure: %s", exc)
        finally:
            self._nc = None
            self._js = None

    def task(
        self, name: str | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Decorator to register a function as a background task."""

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            task_name = name or f"{func.__module__}.{func.__name__}"
            self._tasks[task_name] = func

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # If we are in 'delay' mode (task.delay()), we push to NATS.
                # Here we just execute synchronously if called directly.
                return await cast("Awaitable[R]", func(*args, **kwargs))

            # Add 'kick' method to the wrapper (similar to standard background job 'delay')
            async def kick(*args: P.args, **kwargs: P.kwargs) -> None:
                await self.enqueue(task_name, *args, **kwargs)

            wrapper.kick = kick  # type: ignore[attr-defined]
            return cast(Callable[P, R], wrapper)

        return decorator

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        """Publish a generic event to JetStream with trace context propagation.

        W-03 (audit 2026-03-10): Generic publisher for event-driven patterns where
        the payload does not represent a discrete task to be executed by the
        python-worker durable consumer.
        """
        if self._js is None:
            await self.connect()

        with tracer.start_as_current_span(
            f"nats.publish:{subject}", kind=SpanKind.PRODUCER
        ) as span:
            # Inject trace context into headers
            headers: dict[str, str] = {}
            propagate.inject(headers)

            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", subject)

            if self._js:
                await self._js.publish(
                    subject,
                    json.dumps(payload).encode(),
                    headers=headers,
                )

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Push a task to the JetStream queue with trace context propagation."""
        if self._js is None:
            await self.connect()

        with tracer.start_as_current_span(
            f"nats.enqueue:{task_name}", kind=SpanKind.PRODUCER
        ) as span:
            task_id = str(uuid.uuid4())

            # Inject trace context into headers/metadata
            headers: dict[str, str] = {}
            propagate.inject(headers)

            payload = {
                "id": task_id,
                "name": task_name,
                "args": args,
                "kwargs": kwargs,
                "trace_context": headers,
            }

            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", task_name)
            span.set_attribute("messaging.message_id", task_id)

            if self._js:
                subject = f"{self._subject_prefix}.{task_name}"
                await self._js.publish(
                    subject,
                    json.dumps(payload).encode(),
                    headers=headers,
                )
            return task_id

    async def run_worker(self) -> None:
        """Run the worker to process tasks from JetStream with trace continuation."""
        if self._js is None:
            await self.connect()

        # Create/use a pull-based durable consumer
        js = self._js
        assert js is not None  # nosec B101
        sub = await js.pull_subscribe(
            subject=f"{self._subject_prefix}.>",
            durable="python-worker",
        )

        # PERF-4 (audit 2026-03): Batch-fetch instead of fetch(1).
        # fetch(1) issues a separate JetStream FETCH request to the server for
        # every single message.  With 1 000 queued tasks this is ~1 000 network
        # round-trips vs. 50 with NATS_FETCH_BATCH_SIZE=20.  Processing remains
        # sequential inside each batch (safe ordering, no concurrent DB pressure)
        # while still eliminating the per-message polling overhead.
        _batch_size = max(
            1, min(100, int(os.environ.get("NATS_FETCH_BATCH_SIZE", "20")))
        )

        _logger.info("NATS Task Worker started (batch_size=%d)", _batch_size)
        while True:
            try:
                msgs = await sub.fetch(_batch_size, timeout=5)
                for msg in msgs:
                    try:
                        data = json.loads(msg.data.decode())
                        task_name = data["name"]
                        args = data.get("args", [])
                        kwargs = data.get("kwargs", {})
                        trace_context = data.get("trace_context", {})

                        # Extract trace context
                        context = propagate.extract(trace_context)

                        with tracer.start_as_current_span(
                            f"nats.process:{task_name}",
                            context=context,
                            kind=SpanKind.CONSUMER,
                        ) as span:
                            span.set_attribute("messaging.system", "nats")
                            span.set_attribute("messaging.operation", "process")
                            span.set_attribute("messaging.message_id", data["id"])

                            _logger.info(
                                "Processing task: %s (id: %s)", task_name, data["id"]
                            )

                            handler = self._tasks.get(task_name)
                            if not handler:
                                _logger.error(
                                    "No handler registered for task: %s", task_name
                                )
                                await msg.term()  # Terminal failure
                                continue

                            from app.main import app

                            dishka_container = getattr(
                                app.state, "dishka_container", None
                            )

                            from dishka.integrations.base import wrap_injection

                            if request_container_param := dishka_container:
                                async with (
                                    request_container_param() as request_container
                                ):
                                    if asyncio.iscoroutinefunction(handler):
                                        wrapped = wrap_injection(
                                            func=handler,
                                            container_getter=lambda _, kwargs: (
                                                request_container
                                            ),
                                            remove_depends=True,
                                        )
                                        await wrapped(*args, **kwargs)
                                    else:
                                        import anyio

                                        # For sync funcs, dishka needs sync container which is complex
                                        wrapped = wrap_injection(
                                            func=handler,
                                            container_getter=lambda _, kwargs: (
                                                request_container
                                            ),
                                            remove_depends=True,
                                        )
                                        await anyio.to_thread.run_sync(
                                            functools.partial(wrapped, *args, **kwargs)
                                        )
                            else:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(*args, **kwargs)
                                else:
                                    import anyio

                                    await anyio.to_thread.run_sync(
                                        functools.partial(handler, *args, **kwargs)
                                    )

                        await msg.ack()
                    except Exception as exc:
                        _logger.exception(
                            "Error processing task %s: %s", task_name, exc
                        )
                        # Let it retry (standard JetStream behavior for un-acked messages)
                        await msg.nak()
            except nats.errors.TimeoutError:
                continue
            except Exception as exc:
                _logger.error("Broker worker error: %s", exc)
                await asyncio.sleep(1)


# Singleton instance
broker = NatsTaskBroker()
