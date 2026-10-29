from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, TypeVar, cast

import nats
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import BadRequestError
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind
from prometheus_client import Counter
from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import settings
from app.core.logging import get_logger
from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Hint

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)

_SEVEN_DAYS_SECONDS = 7 * 24 * 3600  # 604,800 seconds


class Task(Protocol[P, R_co]):
    """Protocol for NATS tasks with 'kick' method."""

    async def __call__(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> R_co: ...  # pragma: no branch - protocol stub has no runtime branch
    async def kick(self, *args: P.args, **kwargs: P.kwargs) -> None: ...


_logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


def _worker_stacktrace_without_broker_vars(stacktrace: Any) -> Any:
    """Copy one native SDK stacktrace without broker-frame local variables."""
    if type(stacktrace) is not dict:
        return stacktrace
    frames = stacktrace.get("frames")
    if type(frames) is not list:
        return stacktrace

    protected_frames: list[Any] = []
    for frame in frames:
        if type(frame) is dict:
            module = frame.get("module")
            if type(module) is str and module == __name__:
                protected_frame = frame.copy()
                protected_frame.pop("vars", None)
                protected_frames.append(protected_frame)
                continue
        protected_frames.append(frame)
    protected_stacktrace = stacktrace.copy()
    protected_stacktrace["frames"] = protected_frames
    return protected_stacktrace


def _worker_error_event_without_broker_vars(event: Event, _hint: Hint) -> Event:
    """Copy SDK stack containers, omitting only broker orchestration locals."""
    protected: dict[str, Any] = dict(event)
    if "stacktrace" in event:
        protected["stacktrace"] = _worker_stacktrace_without_broker_vars(
            event["stacktrace"]
        )
    for section_name in ("exception", "threads"):
        section = event.get(section_name)
        if type(section) is not dict:
            continue
        values = section.get("values")
        if type(values) is not list:
            continue

        protected_section = section.copy()
        protected_values: list[Any] = []
        for value in values:
            if type(value) is dict and "stacktrace" in value:
                protected_value = value.copy()
                protected_value["stacktrace"] = _worker_stacktrace_without_broker_vars(
                    value["stacktrace"]
                )
                protected_values.append(protected_value)
            else:
                protected_values.append(value)
        protected_section["values"] = protected_values
        protected[section_name] = protected_section
    return cast("Event", protected)


def _log_worker_task_failure(task_name: str, error: Exception) -> None:
    """Keep exception diagnostics without exporting the raw fetched task batch."""
    try:
        import sentry_sdk
    except ImportError:
        # Match observability's optional SDK support without an unsafe raw
        # traceback fallback. Task retry handling remains owned by the caller.
        _logger.error(
            "Error processing task %s (Sentry SDK unavailable)",
            task_name,
            exc_info=False,
            stack_info=False,
        )
        return

    with sentry_sdk.new_scope() as scope:
        scope.add_event_processor(_worker_error_event_without_broker_vars)
        _logger.exception("Error processing task %s: %s", task_name, error)


# A CORE-NATS publish is intentionally best-effort, but a disconnected broker
# must remain observable.  The event itself can self-heal through the next
# refetch; this counter lets operators distinguish that bounded loss from a
# healthy live fan-out.
nats_publish_core_skipped_total = Counter(
    "nats_publish_core_skipped_total",
    "CORE-NATS publishes skipped because the broker is disconnected",
)

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
# A task that keeps failing is retried with exponential back-off and, after
# ``_MAX_DELIVERIES`` attempts, parked in the database dead-letter queue instead
# of being NAKed forever (an un-bounded redelivery loop hammers the broker and
# starves healthy tasks in the same batch).
_MAX_DELIVERIES = max(1, int(os.environ.get("NATS_TASK_MAX_DELIVERIES", "5")))
_RETRY_BASE_DELAY_S = float(os.environ.get("NATS_TASK_RETRY_BASE_DELAY_SECONDS", "5"))
_RETRY_MAX_DELAY_S = 300.0
_CONNECT_TIMEOUT_S = 5.0
_CLIENT_CLOSE_TIMEOUT_S = 2.0
_WORKER_RETRY_DELAY_S = 1.0


def _serialize_task_uuid(value: Any) -> str:
    """Serialize UUIDs for task JSON without accepting arbitrary objects."""
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


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
        self._connect_lock = asyncio.Lock()
        self._tasks: dict[str, Callable[..., Any]] = {}
        self._stream_name = "TASK_QUEUE"
        self._subject_prefix = "tasks"
        # W140 SW1: file-processor consumes `files.process` as a separate stream.
        # Backend (this broker) is the single source of truth for stream
        # creation per W140 Q2 architecture (production parity); file-processor
        # only subscribes and waits via compose depends_on (W140 SW3).
        self._files_process_stream_name = "FILES_PROCESS"
        self._files_process_subject = "files.process"
        self._chat_events_stream_name = "CHAT_EVENTS"
        self._chat_events_subject = "chat.*"
        self._notifications_events_stream_name = "NOTIFICATIONS_EVENTS"
        self._notifications_events_subject = "notifications.*"
        self._outbox_events_stream_name = "OUTBOX_EVENTS"
        self._outbox_events_subject = "outbox.*"
        self._cache_invalidations_stream_name = "CACHE_INVALIDATIONS"
        self._cache_invalidations_subject = "cache.invalidate"

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
        deadline = asyncio.get_running_loop().time() + _CONNECT_TIMEOUT_S
        async with asyncio.timeout_at(deadline):
            await self._connect_lock.acquire()

        try:
            if self._nc is not None and self._js is not None:
                return

            # Keep a client reference before awaiting its initial connection so
            # cancellation can close its socket and any reconnect machinery.
            client = NATS()
            self._nc = client

            # HIGH-W19: callbacks make connection lifecycle changes visible.
            async def _on_reconnected() -> None:
                _logger.warning("NATS reconnected to server")

            async def _on_disconnected() -> None:
                _logger.warning("NATS disconnected from server")

            initial_handshake = True

            async def _on_error(exc: Exception) -> None:
                permanent_protocol_error = type(exc) is nats.errors.Error or isinstance(
                    exc,
                    (
                        nats.errors.AuthorizationError,
                        nats.errors.InvalidUserCredentialsError,
                    ),
                )
                if initial_handshake and permanent_protocol_error:
                    raise exc
                _logger.warning("NATS connection event: %s", exc)

            try:
                async with asyncio.timeout_at(deadline):
                    await client.connect(
                        settings.nats_url,
                        token=settings.nats_auth_token,
                        max_reconnect_attempts=-1,
                        connect_timeout=2,
                        reconnected_cb=_on_reconnected,
                        disconnected_cb=_on_disconnected,
                        error_cb=_on_error,
                    )
                    initial_handshake = False
                    js = client.jetstream()

                    # Provision file-backed streams with 7-day retention policy.
                    streams = [
                        StreamConfig(
                            name=self._stream_name,
                            subjects=[f"{self._subject_prefix}.>"],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                        StreamConfig(
                            name=self._files_process_stream_name,
                            subjects=[self._files_process_subject],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                        StreamConfig(
                            name=self._chat_events_stream_name,
                            subjects=[self._chat_events_subject],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                        StreamConfig(
                            name=self._notifications_events_stream_name,
                            subjects=[self._notifications_events_subject],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                        StreamConfig(
                            name=self._outbox_events_stream_name,
                            subjects=[self._outbox_events_subject],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                        StreamConfig(
                            name=self._cache_invalidations_stream_name,
                            subjects=[self._cache_invalidations_subject],
                            storage=StorageType.FILE,
                            retention=RetentionPolicy.LIMITS,
                            max_age=_SEVEN_DAYS_SECONDS,
                        ),
                    ]

                    for stream_cfg in streams:
                        try:
                            await js.add_stream(config=stream_cfg)
                        except BadRequestError as exc:
                            if exc.err_code != 10058:
                                raise
                            # Reconcile existing streams without deleting messages.
                            await js.update_stream(config=stream_cfg)
                            _logger.info(
                                "Reconciled existing NATS JetStream stream %s",
                                stream_cfg.name,
                            )

                    # Publish the initialized context only after every stream is ready.
                    self._js = js
                    _logger.info(
                        "Connected to NATS JetStream (6 file-backed streams provisioned)"
                    )
            except asyncio.CancelledError:
                await self._cleanup_after_connect_failure()
                raise
            except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — preserves connection/provisioning failure
                _logger.error("Failed to connect to NATS: %s", exc)
                await self._cleanup_after_connect_failure()
                raise
        finally:
            self._connect_lock.release()

    async def _cleanup_after_connect_failure(self) -> None:
        try:
            await self._close_unlocked()
        except Exception as cleanup_exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — preserves original connection failure
            _logger.warning("Failed to close partial NATS connection: %s", cleanup_exc)
            self._nc = None
            self._js = None

    async def close(self) -> None:
        """Close NATS connection without racing an in-flight initialization."""
        async with self._connect_lock:
            await self._close_unlocked()

    async def _close_unlocked(self) -> None:
        client = self._nc
        try:
            if client is not None:
                async with asyncio.timeout(_CLIENT_CLOSE_TIMEOUT_S):
                    await client.close()
        except (OSError, ConnectionError, TimeoutError, nats.errors.Error) as exc:
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

    async def publish(
        self,
        subject: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        msg_id: str | None = None,
    ) -> None:
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
            msg_headers: dict[str, str] = headers.copy() if headers else {}
            propagate.inject(msg_headers)

            dedup_id = (
                msg_id
                or payload.get("id")
                or payload.get("event_id")
                or str(uuid.uuid4())
            )
            msg_headers["Nats-Msg-Id"] = str(dedup_id)

            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", subject)
            span.set_attribute("messaging.message_id", str(dedup_id))

            if self._js:
                await self._js.publish(
                    subject,
                    json.dumps(payload).encode(),
                    headers=msg_headers,
                )

    async def publish_core(
        self,
        subject: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        msg_id: str | None = None,
        *,
        strict: bool = False,
    ) -> None:
        """Publish via CORE NATS without waiting for a JetStream PubAck.

        W204 SW1: mirrors in-process ``ws_manager`` chat broadcasts onto the
        ws-hub ``chat.*`` core subscription (``services/ws-hub`` hub.go:375) so
        frames reach browser clients LIVE — the browser connects to ws-hub, NOT
        the in-process FastAPI WebSocket, so the in-process fan-out never reaches
        it (the messenger has been refetch/self-heal only).

        Unlike :meth:`publish`, this uses the raw core connection and does not
        wait for a JetStream PubAck. The configured ``CHAT_EVENTS`` stream
        captures ``chat.*``, but returning from this method does not confirm
        stream persistence or delivery to a subscriber or browser. Refetch
        remains the recovery path for a missed live frame.

        Serialises with orjson (native ``uuid.UUID`` + ``datetime`` support)
        because the ``new_message`` frame nests ``serialize_message`` output
        carrying raw ``uuid.UUID`` values (serializers.py) — stdlib
        ``json.dumps`` would raise ``TypeError``.  ``default=str`` mirrors the
        existing orjson callsite at logging.py:222.

        Best-effort by default: handled transport failures leave the caller's
        in-process delivery + refetch fallback stay intact. Outbox-backed
        callers may opt into ``strict`` so a transient publish failure returns
        to the outbox worker and can be retried.
        """
        # Ephemeral best-effort: publish ONLY if the broker is already connected
        # (the app lifespan connects it at startup). Do NOT trigger a connect
        # from this hot path — a connect attempt would add a multi-second
        # timeout to the message-send path during a NATS outage, and would raise
        # in test/CLI contexts where NATS isn't running. A dropped frame
        # self-heals via the next refetch; the broker's own background reconnect
        # (max_reconnect_attempts=-1) restores the connection independently.
        if self._nc is None or not self._nc.is_connected:
            nats_publish_core_skipped_total.inc()
            _logger.warning(
                "nats_publish_skipped_not_connected",
                subject=subject,
            )
            if strict:
                raise ConnectionError("NATS core publisher is not connected")
            return

        with tracer.start_as_current_span(
            f"nats.publish_core:{subject}", kind=SpanKind.PRODUCER
        ) as span:
            msg_headers: dict[str, str] = headers.copy() if headers else {}
            propagate.inject(msg_headers)

            dedup_id = (
                msg_id
                or payload.get("id")
                or payload.get("event_id")
                or str(uuid.uuid4())
            )
            msg_headers["Nats-Msg-Id"] = str(dedup_id)

            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", subject)
            span.set_attribute("messaging.message_id", str(dedup_id))

            try:
                await self._nc.publish(
                    subject,
                    orjson.dumps(payload, default=str),
                    headers=msg_headers,
                )
            except (
                nats.errors.Error,
                ConnectionError,
                TimeoutError,
                OSError,
            ) as exc:  # RZ-20-04: narrowed — NATS infra errors; ephemeral frame self-heals via refetch
                _logger.debug(
                    "publish_core failed (self-heal via refetch): subject=%s err=%s",
                    subject,
                    exc,
                )
                if strict:
                    raise

    async def enqueue(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Push a task to the JetStream queue with trace context propagation."""
        if task_name == "app.tasks.email.send_auth_email":
            from app.tasks.email import prepare_auth_email_payload

            protected_payload = prepare_auth_email_payload(
                {"args": list(args), "kwargs": kwargs}
            )[0]
            args = tuple(protected_payload["args"])
            kwargs = protected_payload["kwargs"]
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
            headers["Nats-Msg-Id"] = task_id

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

            subject = f"{self._subject_prefix}.{task_name}"
            if self._js:
                await self._js.publish(
                    subject,
                    orjson.dumps(payload, default=_serialize_task_uuid),
                    headers=headers,
                )
            return task_id

    @staticmethod
    def _num_delivered(msg: Any) -> int:
        try:
            return max(1, int(msg.metadata.num_delivered))
        except (AttributeError, TypeError, ValueError, nats.errors.Error):
            return 1

    async def _retry_or_dead_letter(
        self, msg: Any, payload: _NatsTaskPayload, error: str
    ) -> None:
        """NAK with back-off, or park the task in the DLQ once retries are spent."""
        delivered = self._num_delivered(msg)
        if delivered >= _MAX_DELIVERIES:
            if await self._dead_letter(payload, error, delivered):
                await msg.term()
                return
            # Persisting failed: keep the message alive rather than lose the task.
        delay = min(_RETRY_BASE_DELAY_S * 2 ** (delivered - 1), _RETRY_MAX_DELAY_S)
        await msg.nak(delay=delay)

    async def _dead_letter(
        self, payload: _NatsTaskPayload, error: str, delivered: int
    ) -> bool:
        from sqlalchemy.exc import SQLAlchemyError

        from app.core.database import async_session
        from app.workers.dead_letter_queue import DeadLetterQueue

        protection_errors: tuple[type[Exception], ...] = ()
        if payload.name == "app.tasks.email.send_auth_email":
            from app.tasks.email import AuthEmailPayloadError

            protection_errors = (AuthEmailPayloadError,)
        try:
            async with async_session() as session:
                await DeadLetterQueue(session).add_failed_job(
                    job_type=payload.name,
                    payload={"args": list(payload.args), "kwargs": payload.kwargs},
                    error_message=error[:2000],
                )
                await session.commit()
        except protection_errors:
            _logger.warning("nats_auth_email_payload_protection_failed")
            return False
        except (SQLAlchemyError, OSError) as exc:
            _logger.error(
                "nats_task_dlq_persist_failed: task=%s id=%s err=%s",
                payload.name,
                payload.id,
                exc,
            )
            return False
        _logger.error(
            "nats_task_dead_lettered: task=%s id=%s deliveries=%d",
            payload.name,
            payload.id,
            delivered,
        )
        return True

    async def replay_dead_letter(self, job_type: str, payload: dict[str, Any]) -> None:
        """Re-enqueue a dead-lettered task (handler for ``DeadLetterQueue`` replay)."""
        await self.enqueue(
            job_type,
            *payload.get("args", []),
            **payload.get("kwargs", {}),
        )

    async def run_worker(self) -> None:
        """Run the worker to process tasks from JetStream with trace continuation."""
        while True:
            try:
                if self._js is None:
                    await self.connect()
                js = self._js
                assert js is not None  # noqa: S101
                sub = await js.pull_subscribe(
                    subject=f"{self._subject_prefix}.>",
                    durable="python-worker",
                )
                break
            except asyncio.CancelledError:
                raise
            except (
                OSError,
                ConnectionError,
                TimeoutError,
                nats.errors.NoServersError,
            ) as exc:
                _logger.warning("NATS task worker connection failed; retrying: %s", exc)
                await asyncio.sleep(_WORKER_RETRY_DELAY_S)

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
                                await self._retry_or_dead_letter(
                                    msg,
                                    payload,
                                    f"no handler registered for task: {task_name}",
                                )
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
                                        if inspect.iscoroutinefunction(handler):  # noqa: B023
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
                                                abandon_on_cancel=True,
                                            )
                                else:
                                    if inspect.iscoroutinefunction(handler):  # noqa: B023
                                        await handler(*args, **kwargs)  # noqa: B023
                                    else:
                                        import anyio

                                        await anyio.to_thread.run_sync(
                                            functools.partial(handler, *args, **kwargs),  # noqa: B023
                                            abandon_on_cancel=True,
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
                                await self._retry_or_dead_letter(
                                    msg, payload, "task timed out"
                                )
                                continue

                        await msg.ack()
                    except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — NAKs message for JetStream retry (reviewed TD-27-04)
                        _log_worker_task_failure(task_name, exc)
                        await self._retry_or_dead_letter(msg, payload, str(exc))
            except nats.errors.TimeoutError:
                continue
            except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — worker loop must survive any error (reviewed TD-27-04)
                _logger.error("Broker worker error: %s", exc)
                await asyncio.sleep(1)


# Singleton instance
broker = NatsTaskBroker()
