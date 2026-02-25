from __future__ import annotations

import asyncio
import functools
import json
import logging
import uuid
from collections.abc import Callable, Awaitable
from typing import Any, ParamSpec, TypeVar, cast

import nats
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

    Replaces TaskIQ to reduce infrastructure complexity and leverage
    JetStream's durable streams and at-least-once delivery.
    """

    def __init__(self) -> None:
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
        self._tasks: dict[str, Callable[..., Any]] = {}
        self._stream_name = "TASK_QUEUE"
        self._subject_prefix = "tasks"

    async def connect(self) -> None:
        """Connect to NATS and ensure JetStream is initialized."""
        if self._nc is not None:
            return

        try:
            self._nc = await nats.connect(settings.nats_url)
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
        if self._nc:
            await self._nc.close()
            self._nc = None
            self._js = None

    def task(self, name: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Decorator to register a function as a background task."""
        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            task_name = name or f"{func.__module__}.{func.__name__}"
            self._tasks[task_name] = func

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # If we are in 'delay' mode (task.delay()), we push to NATS.
                # Here we just execute synchronously if called directly.
                return await cast("Awaitable[R]", func(*args, **kwargs))

            # Add 'kick' method to the wrapper (similar to TaskIQ/Celery 'delay')
            async def kick(*args: P.args, **kwargs: P.kwargs) -> None:
                await self.enqueue(task_name, *args, **kwargs)

            setattr(wrapper, "kick", kick)
            return wrapper # type: ignore

        return decorator

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
                await self._js.publish(subject, json.dumps(payload).encode())
            return task_id

    async def run_worker(self) -> None:
        """Run the worker to process tasks from JetStream with trace continuation."""
        if self._js is None:
            await self.connect()

        # Create/use a pull-based durable consumer
        sub = await self._js.pull_subscribe(
            subject=f"{self._subject_prefix}.>",
            durable="python-worker",
        )

        _logger.info("NATS Task Worker started")
        while True:
            try:
                msgs = await sub.fetch(1, timeout=5)
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

                            _logger.info("Processing task: %s (id: %s)", task_name, data["id"])

                            handler = self._tasks.get(task_name)
                            if not handler:
                                _logger.error("No handler registered for task: %s", task_name)
                                await msg.term() # Terminal failure
                                continue

                            from app.main import app  # type: ignore
                            dishka_container = getattr(app.state, "dishka_container", None)

                            from dishka.integrations.base import wrap_injection

                            if request_container_param := dishka_container:
                                async with request_container_param() as request_container:
                                    if asyncio.iscoroutinefunction(handler):
                                        wrapped = wrap_injection(
                                            func=handler,
                                            container_getter=lambda _, kwargs: request_container,
                                            remove_depends=True,
                                        )
                                        await wrapped(*args, **kwargs)
                                    else:
                                        import anyio
                                        # For sync funcs, dishka needs sync container which is complex
                                        wrapped = wrap_injection(
                                            func=handler,
                                            container_getter=lambda _, kwargs: request_container,
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
                        _logger.exception("Error processing task %s: %s", task_name, exc)
                        # Let it retry (standard JetStream behavior for un-acked messages)
                        await msg.nak()
            except nats.errors.TimeoutError:
                continue
            except Exception as exc:
                _logger.error("Broker worker error: %s", exc)
                await asyncio.sleep(1)


# Singleton instance
broker = NatsTaskBroker()
