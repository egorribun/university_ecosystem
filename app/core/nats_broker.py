from __future__ import annotations

import asyncio
import functools
import json
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast

import nats
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import settings
from app.core.logging import get_logger
from app.core.orjson_utils import orjson

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class Task(Protocol[P, R_co]):
    """Protocol for NATS tasks with 'kick' method."""

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...
    async def kick(self, *args: P.args, **kwargs: P.kwargs) -> None: ...


_logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# HIGH-W19: Module-level reference to the FastAPI application instance.
# Populated by set_app() during lifespan startup to avoid a circular import
# (app.main → app.core.nats_broker → app.main).
_app: Any = None


def set_app(application: Any) -> None:
    """Register the FastAPI app so run_worker() can access dishka_container.

    Call this from the application lifespan *before* starting the worker.
    """
    global _app
    _app = application


# P1-W5-08: Maximum seconds a single task handler may run before it is
# cancelled.  Prevents one stuck handler from blocking the entire worker loop.
_DEFAULT_TASK_TIMEOUT_S = float(os.environ.get("NATS_TASK_TIMEOUT_SECONDS", "30"))


class _NatsTaskPayload(BaseModel):  # type: ignore[no-redef]
    """P1-W5-09: Validated NATS task message schema.

    Parsing with this model rejects malformed payloads before any handler
    lookup, preventing KeyError crashes and unknown-task execution.
    """

    id: str
    name: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    trace_context: dict[str, str] = {}

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task name must not be empty")
        return v


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
        # W140 SW1: file-processor consumes `files.process` as a separate stream.
        # Backend (this broker) is the single source of truth for stream
        # creation per W140 Q2 architecture (production parity); file-processor
        # only subscribes and waits via compose depends_on (W140 SW3).
        self._files_process_stream_name = "FILES_PROCESS"
        self._files_process_subject = "files.process"

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

        # HIGH-W19: Callbacks for reconnect/disconnect logging so that connection
        # lifecycle events are visible in the application log.
        async def _on_reconnected() -> None:
            _logger.warning("NATS reconnected to server")

        async def _on_disconnected() -> None:
            _logger.warning("NATS disconnected from server")

        try:
            self._nc = await nats.connect(
                settings.nats_url,
                # HIGH-W19: Use max_reconnect_attempts=-1 (unlimited) so that after
                # a successful initial connection the client automatically reconnects
                # on transient network failures. The connect_timeout still applies to
                # the INITIAL connect attempt, guarding lifespan startup.
                max_reconnect_attempts=-1,
                connect_timeout=2,
                reconnected_cb=_on_reconnected,
                disconnected_cb=_on_disconnected,
            )
            self._js = self._nc.jetstream()

            # Ensure stream exists
            await self._js.add_stream(
                name=self._stream_name,
                subjects=[f"{self._subject_prefix}.>"],
            )
            # W140 SW1: provision file-processor's NATS stream. file-processor
            # crashes at startup if this stream is missing (W139 §Honesty #6).
            # add_stream is idempotent — re-creating the same stream is a no-op.
            await self._js.add_stream(
                name=self._files_process_stream_name,
                subjects=[self._files_process_subject],
            )
            _logger.info("Connected to NATS JetStream for task processing")
        except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — logs then re-raises (reviewed TD-27-04)
            _logger.error("Failed to connect to NATS: %s", exc)
            raise

    async def close(self) -> None:
        """Close NATS connection."""
        try:
            if self._nc and self._nc.is_connected:
                await self._nc.close()
        except (
            OSError,
            ConnectionError,
        ) as exc:  # RZ-22-01: narrowed — network errors during close
            _logger.warning("Error during NATS closure: %s", exc)
        finally:
            self._nc = None
            self._js = None

    def task(
        self, name: str | None = None
    ) -> Callable[[Callable[P, R_co]], Task[P, R_co]]:
        """Decorator to register a function as a background task."""

        def decorator(func: Callable[P, R_co]) -> Task[P, R_co]:
            task_name = name or f"{func.__module__}.{func.__name__}"
            self._tasks[task_name] = func

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # If we are in 'delay' mode (task.delay()), we push to NATS.
                # Here we just execute synchronously if called directly.
                return await cast("Awaitable[R_co]", func(*args, **kwargs))

            # Add 'kick' method to the wrapper (similar to standard background job 'delay')
            async def kick(*args: P.args, **kwargs: P.kwargs) -> None:
                await self.enqueue(task_name, *args, **kwargs)

            wrapper.kick = kick  # type: ignore[attr-defined]
            return cast(Task[P, R_co], wrapper)

        return decorator

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        """Publish a generic event to JetStream with trace context propagation.

        W-03 (audit 2026-03-10): Generic publisher for event-driven patterns where
        the payload does not represent a discrete task to be executed by the
        python-worker durable consumer.
        """
        if self._js is None:
            await self.connect()
        if self._js is None:
            raise RuntimeError("NATS JetStream not available")

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

    async def publish_core(self, subject: str, payload: dict[str, Any]) -> None:
        """Publish an ephemeral event via CORE NATS (fire-and-forget, no stream).

        W204 SW1: mirrors in-process ``ws_manager`` chat broadcasts onto the
        ws-hub ``chat.*`` core subscription (``services/ws-hub`` hub.go:375) so
        frames reach browser clients LIVE — the browser connects to ws-hub, NOT
        the in-process FastAPI WebSocket, so the in-process fan-out never reaches
        it (the messenger has been refetch/self-heal only).

        Unlike :meth:`publish` (JetStream, durable), this uses the raw core
        connection because ``chat.*`` has NO JetStream stream (only
        ``TASK_QUEUE`` + ``FILES_PROCESS``) — a JetStream publish there would
        error on the missing PubAck.  Ephemeral live frames need no persistence:
        a dropped frame self-heals via the next refetch.

        Serialises with orjson (native ``uuid.UUID`` + ``datetime`` support)
        because the ``new_message`` frame nests ``serialize_message`` output
        carrying raw ``uuid.UUID`` values (serializers.py) — stdlib
        ``json.dumps`` would raise ``TypeError``.  ``default=str`` mirrors the
        existing orjson callsite at logging.py:222.

        Best-effort: never raises on infra failure so the caller's in-process
        delivery + refetch fallback stay intact.
        """
        # Ephemeral best-effort: publish ONLY if the broker is already connected
        # (the app lifespan connects it at startup). Do NOT trigger a connect
        # from this hot path — a connect attempt would add a multi-second
        # timeout to the message-send path during a NATS outage, and would raise
        # in test/CLI contexts where NATS isn't running. A dropped frame
        # self-heals via the next refetch; the broker's own background reconnect
        # (max_reconnect_attempts=-1) restores the connection independently.
        if self._nc is None or not self._nc.is_connected:
            return

        with tracer.start_as_current_span(
            f"nats.publish_core:{subject}", kind=SpanKind.PRODUCER
        ) as span:
            headers: dict[str, str] = {}
            propagate.inject(headers)
            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", subject)
            try:
                await self._nc.publish(
                    subject,
                    orjson.dumps(payload, default=str),
                    headers=headers,
                )
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as exc:  # RZ-20-04: narrowed — NATS infra errors; ephemeral frame self-heals via refetch
                _logger.debug(
                    "publish_core failed (self-heal via refetch): subject=%s err=%s",
                    subject,
                    exc,
                )

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Push a task to the JetStream queue with trace context propagation."""
        if self._js is None:
            await self.connect()
        if self._js is None:
            raise RuntimeError("NATS JetStream not available")

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
        assert js is not None  # noqa: S101
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
                    # P1-W5-09: Validate schema before touching any field.
                    try:
                        payload = _NatsTaskPayload.model_validate(
                            json.loads(msg.data.decode())
                        )
                    except (
                        ValidationError,
                        json.JSONDecodeError,
                        UnicodeDecodeError,
                    ) as exc:
                        _logger.error(
                            "nats_invalid_payload: %s — raw=%s",
                            exc,
                            msg.data[:200],
                        )
                        # ACK to prevent infinite re-delivery of permanently invalid messages.
                        await msg.ack()
                        continue

                    task_name = payload.name
                    args = payload.args
                    kwargs = payload.kwargs
                    trace_context = payload.trace_context

                    try:
                        # Extract trace context
                        ctx = propagate.extract(trace_context)

                        with tracer.start_as_current_span(
                            f"nats.process:{task_name}",
                            context=ctx,
                            kind=SpanKind.CONSUMER,
                        ) as span:
                            span.set_attribute("messaging.system", "nats")
                            span.set_attribute("messaging.operation", "process")
                            span.set_attribute("messaging.message_id", payload.id)

                            _logger.info(
                                "Processing task: %s (id: %s)", task_name, payload.id
                            )

                            handler = self._tasks.get(task_name)
                            if not handler:
                                _logger.error(
                                    "No handler registered for task: %s", task_name
                                )
                                await msg.term()  # Terminal failure
                                continue

                            # HIGH-W19: Use the module-level _app reference set via
                            # set_app() instead of importing app.main here, which
                            # would create a circular import at import time.
                            dishka_container = getattr(
                                getattr(_app, "state", None), "dishka_container", None
                            )

                            from dishka.integrations.base import wrap_injection

                            # P1-W5-08: Wrap execution with a per-task timeout so a
                            # stuck handler cannot block the entire worker loop.
                            async def _execute() -> None:
                                if request_container_param := dishka_container:  # noqa: B023
                                    async with (
                                        request_container_param() as request_container
                                    ):
                                        if asyncio.iscoroutinefunction(handler):  # noqa: B023
                                            wrapped = wrap_injection(
                                                func=handler,  # noqa: B023
                                                container_getter=lambda _, __: (
                                                    request_container
                                                ),
                                                remove_depends=True,
                                            )
                                            await wrapped(*args, **kwargs)  # noqa: B023
                                        else:
                                            import anyio

                                            wrapped = wrap_injection(
                                                func=handler,  # noqa: B023
                                                container_getter=lambda _, __: (
                                                    request_container
                                                ),
                                                remove_depends=True,
                                            )
                                            await anyio.to_thread.run_sync(
                                                functools.partial(
                                                    wrapped,
                                                    *args,  # noqa: B023
                                                    **kwargs,  # noqa: B023
                                                ),
                                                cancellable=True,
                                            )
                                else:
                                    if asyncio.iscoroutinefunction(handler):  # noqa: B023
                                        await handler(*args, **kwargs)  # noqa: B023
                                    else:
                                        import anyio

                                        await anyio.to_thread.run_sync(
                                            functools.partial(handler, *args, **kwargs),  # noqa: B023
                                            cancellable=True,
                                        )

                            try:
                                async with asyncio.timeout(_DEFAULT_TASK_TIMEOUT_S):
                                    await _execute()
                            except TimeoutError:
                                _logger.error(
                                    "nats_task_timeout: task=%s id=%s timeout=%.0fs",
                                    task_name,
                                    payload.id,
                                    _DEFAULT_TASK_TIMEOUT_S,
                                )
                                await msg.nak()
                                continue

                        await msg.ack()
                    except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — NAKs message for JetStream retry (reviewed TD-27-04)
                        _logger.exception(
                            "Error processing task %s: %s", task_name, exc
                        )
                        # Let it retry (standard JetStream behavior for un-acked messages)
                        await msg.nak()
            except nats.errors.TimeoutError:
                continue
            except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — worker loop must survive any error (reviewed TD-27-04)
                _logger.error("Broker worker error: %s", exc)
                await asyncio.sleep(1)


# Singleton instance
broker = NatsTaskBroker()
