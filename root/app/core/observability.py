from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - optional dependency guard
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    CollectorRegistry = None  # type: ignore[assignment]
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]
    REGISTRY = None  # type: ignore[assignment]

    def generate_latest(_: object) -> bytes:  # type: ignore[misc]
        raise RuntimeError("prometheus-client is required for worker metrics")


try:
    from sentry_sdk import init as sentry_init
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    try:
        from sentry_sdk.integrations.opentelemetry import (
            SentrySpanProcessor,  # type: ignore
        )
    except Exception:
        SentrySpanProcessor = None  # type: ignore[assignment]
except Exception:
    sentry_init = None  # type: ignore[assignment]
    FastApiIntegration = None  # type: ignore[assignment]
    LoggingIntegration = None  # type: ignore[assignment]
    SentrySpanProcessor = None  # type: ignore[assignment]

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings

_logging_configured = False
_otel_configured = False
_sqlalchemy_instrumented = False
_otel_logger_provider: LoggerProvider | None = None
_otel_logging_handler: LoggingHandler | None = None
_notification_queue_metrics: NotificationQueueMetrics | None = None
_periodic_task_metrics: dict[str, PeriodicTaskMetrics] = {}

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_ctx.get(None)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, header_name: str = "x-request-id") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next):
        header_value = request.headers.get(self._header_name)
        request_id = header_value or uuid.uuid4().hex
        token = _request_id_ctx.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[self._header_name] = request_id
        return response


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context is not None and span_context.is_valid:
            record.trace_id = f"{span_context.trace_id:032x}"
            record.span_id = f"{span_context.span_id:016x}"
        else:
            record.trace_id = ""
            record.span_id = ""
        request_id = get_request_id()
        record.request_id = request_id or ""
        record.service_name = settings.otel_service_name
        record.environment = settings.environment
        return True


class JSONLogFormatter(logging.Formatter):
    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
            "request_id": getattr(record, "request_id", None),
            "service_name": getattr(record, "service_name", None),
            "environment": getattr(record, "environment", None),
        }
        for key, value in extras.items():
            if value:
                log_record[key] = value
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(log_record, ensure_ascii=False)


def _resolve_headers(value: str) -> Mapping[str, str]:
    headers: dict[str, str] = {}
    if not value:
        return headers
    parts: Iterable[str] = value.split(",")
    for part in parts:
        if not part.strip():
            continue
        key, _, val = part.partition("=")
        if key and val:
            headers[key.strip()] = val.strip()
    return headers


def _configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(TraceContextFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True

    _logging_configured = True


def _configure_sentry(tracer_provider: TracerProvider | None) -> None:
    if (
        not settings.sentry_dsn
        or sentry_init is None
        or LoggingIntegration is None
        or FastApiIntegration is None
    ):
        return

    sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
    release = (settings.service_version or "").strip() or None
    sentry_init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[FastApiIntegration(), sentry_logging],
        send_default_pii=False,
        release=release,
    )

    if tracer_provider is not None and SentrySpanProcessor is not None:
        tracer_provider.add_span_processor(SentrySpanProcessor())  # type: ignore[arg-type]


def _build_otel_resource_attributes() -> dict[str, str]:
    attributes = {
        "service.name": settings.otel_service_name,
        "service.instance.id": socket.gethostname(),
        "deployment.environment": settings.environment,
    }
    version = (settings.service_version or "").strip()
    if version:
        attributes["service.version"] = version
    return attributes


def _create_otel_resource() -> Resource:
    return Resource.create(_build_otel_resource_attributes())


def _configure_otel(engine: AsyncEngine) -> TracerProvider | None:
    global _otel_configured, _sqlalchemy_instrumented
    if not settings.enable_otel:
        return None
    if _otel_configured:
        return trace.get_tracer_provider()  # type: ignore[return-value]

    resource = _create_otel_resource()

    sampler = ParentBased(
        TraceIdRatioBased(max(min(settings.otel_trace_sampler_ratio, 1.0), 0.0))
    )
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    otlp_headers = _resolve_headers(settings.otel_exporter_otlp_headers)

    span_exporter_kwargs: dict[str, Any] = {}
    if settings.otel_exporter_otlp_endpoint:
        span_exporter_kwargs["endpoint"] = settings.otel_exporter_otlp_endpoint
    if otlp_headers:
        span_exporter_kwargs["headers"] = otlp_headers
    span_exporter = OTLPSpanExporter(**span_exporter_kwargs)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    meter_readers = []
    if settings.enable_otel_metrics:
        metric_exporter_kwargs: dict[str, Any] = {}
        if settings.otel_exporter_otlp_endpoint:
            metric_exporter_kwargs["endpoint"] = settings.otel_exporter_otlp_endpoint
        if otlp_headers:
            metric_exporter_kwargs["headers"] = otlp_headers
        metric_exporter = OTLPMetricExporter(**metric_exporter_kwargs)
        reader = PeriodicExportingMetricReader(metric_exporter)
        meter_readers.append(reader)

    meter_provider = MeterProvider(resource=resource, metric_readers=meter_readers)
    metrics.set_meter_provider(meter_provider)

    global _otel_logger_provider, _otel_logging_handler

    if settings.enable_otel_logs:
        logger_provider = LoggerProvider(resource=resource)
        log_exporter_kwargs: dict[str, Any] = {}
        if settings.otel_exporter_otlp_endpoint:
            log_exporter_kwargs["endpoint"] = settings.otel_exporter_otlp_endpoint
        if otlp_headers:
            log_exporter_kwargs["headers"] = otlp_headers
        log_exporter = OTLPLogExporter(**log_exporter_kwargs)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        logging.getLogger().addHandler(handler)
        _otel_logger_provider = logger_provider
        _otel_logging_handler = handler

    if not _sqlalchemy_instrumented:
        try:
            SQLAlchemyInstrumentor().instrument(
                engine=engine.sync_engine,
                tracer_provider=tracer_provider,
                enable_metrics=settings.enable_otel_metrics,
                meter_provider=meter_provider if settings.enable_otel_metrics else None,
            )
            _sqlalchemy_instrumented = True
        except Exception:
            pass

    _otel_configured = True
    return tracer_provider


def configure_observability(app: FastAPI, *, engine: AsyncEngine) -> None:
    """Configure logging and telemetry for API handlers and background tasks."""

    if not getattr(app.state, "observability_configured", False):
        _configure_logging()
        app.add_middleware(
            CorrelationIdMiddleware, header_name=settings.request_id_header
        )
        tracer_provider = _configure_otel(engine)
        _configure_sentry(tracer_provider)

        if settings.enable_otel and not getattr(app.state, "otel_instrumented", False):
            try:
                FastAPIInstrumentor.instrument_app(
                    app,
                    tracer_provider=trace.get_tracer_provider(),
                    meter_provider=metrics.get_meter_provider(),
                )
            except Exception:
                pass
            app.state.otel_instrumented = True

        app.state.observability_configured = True


def shutdown_observability() -> None:
    provider = trace.get_tracer_provider()
    with suppress(Exception):
        if isinstance(provider, TracerProvider):
            provider.shutdown()

    meter_provider = metrics.get_meter_provider()
    with suppress(Exception):
        if isinstance(meter_provider, MeterProvider):
            meter_provider.shutdown()

    if _otel_logging_handler is not None:
        with suppress(Exception):
            logging.getLogger().removeHandler(_otel_logging_handler)

    if _otel_logger_provider is not None:
        with suppress(Exception):
            _otel_logger_provider.shutdown()


def _sanitize_metric_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_")
    return normalized or "worker"


@dataclass
class WorkerMetrics:
    """Prometheus-compatible counters for long-running workers."""

    name: str
    registry: CollectorRegistry
    runs_total: Counter
    failures_total: Counter
    notifications_created_total: Counter
    last_run_timestamp: Gauge
    last_success_timestamp: Gauge
    heartbeat_timestamp: Gauge
    _last_run: float | None = None
    _last_success: float | None = None
    _last_failure: float | None = None

    def mark_startup(self) -> None:
        now = time.time()
        self.heartbeat_timestamp.set(now)
        self._last_run = now

    def record_success(self, notifications_created: int = 0) -> None:
        self._record_cycle(success=True, notifications_created=notifications_created)

    def record_failure(self) -> None:
        self._record_cycle(success=False, notifications_created=0)

    def _record_cycle(self, *, success: bool, notifications_created: int) -> None:
        now = time.time()
        self.last_run_timestamp.set(now)
        self.heartbeat_timestamp.set(now)
        self._last_run = now
        if notifications_created:
            self.notifications_created_total.inc(notifications_created)
        if success:
            self.runs_total.inc()
            self.last_success_timestamp.set(now)
            self._last_success = now
        else:
            self.failures_total.inc()
            self._last_failure = now

    @property
    def last_run(self) -> float | None:
        return self._last_run

    @property
    def last_success(self) -> float | None:
        return self._last_success

    @property
    def last_failure(self) -> float | None:
        return self._last_failure

    @property
    def status(self) -> str:
        if self._last_failure is not None and (
            self._last_success is None or self._last_failure > self._last_success
        ):
            return "degraded"
        return "ok"


def create_worker_metrics(name: str) -> WorkerMetrics:
    if (
        CollectorRegistry is None or Counter is None or Gauge is None
    ):  # pragma: no cover - safety
        raise RuntimeError("prometheus-client is required to create worker metrics")

    metric_name = _sanitize_metric_name(name)
    registry = CollectorRegistry()
    runs = Counter(
        f"{metric_name}_runs_total",
        "Total successful scheduler iterations",
        registry=registry,
    )
    failures = Counter(
        f"{metric_name}_failures_total",
        "Total failed scheduler iterations",
        registry=registry,
    )
    notifications_created = Counter(
        f"{metric_name}_notifications_created_total",
        "Total notifications created by the scheduler",
        registry=registry,
    )
    last_run = Gauge(
        f"{metric_name}_last_run_timestamp_seconds",
        "Timestamp of the last scheduler iteration",
        registry=registry,
    )
    last_success = Gauge(
        f"{metric_name}_last_success_timestamp_seconds",
        "Timestamp of the last successful scheduler iteration",
        registry=registry,
    )
    heartbeat = Gauge(
        f"{metric_name}_heartbeat_timestamp_seconds",
        "Heartbeat timestamp updated on every scheduler iteration",
        registry=registry,
    )

    metrics = WorkerMetrics(
        name=name,
        registry=registry,
        runs_total=runs,
        failures_total=failures,
        notifications_created_total=notifications_created,
        last_run_timestamp=last_run,
        last_success_timestamp=last_success,
        heartbeat_timestamp=heartbeat,
    )
    metrics.mark_startup()
    return metrics


@dataclass(slots=True)
class PeriodicTaskRun:
    metrics: PeriodicTaskMetrics
    _deleted_total: int = 0

    def observe_deleted(self, value: int | Iterable[int | None] | None) -> None:
        total = 0
        if value is None:
            total = 0
        elif isinstance(value, Iterable) and not isinstance(value, str | bytes):
            for item in value:
                total += _coerce_deleted_value(item)
        else:
            total = _coerce_deleted_value(value)
        if total > 0:
            self._deleted_total += total

    @property
    def deleted_total(self) -> int:
        return self._deleted_total


def _coerce_deleted_value(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


@dataclass(slots=True)
class PeriodicTaskMetrics:
    name: str
    metric_prefix: str
    runs_total: Counter
    errors_total: Counter
    deleted_total: Counter
    duration_seconds: Histogram

    @asynccontextmanager
    async def track_execution(self) -> AsyncIterator[PeriodicTaskRun]:
        run = PeriodicTaskRun(self)
        start = time.perf_counter()
        try:
            yield run
        except asyncio.CancelledError:
            raise
        except Exception:
            elapsed = max(time.perf_counter() - start, 0.0)
            self.errors_total.inc()
            self.duration_seconds.observe(elapsed)
            raise
        else:
            elapsed = max(time.perf_counter() - start, 0.0)
            self.runs_total.inc()
            if run.deleted_total > 0:
                self.deleted_total.inc(run.deleted_total)
            self.duration_seconds.observe(elapsed)


def get_periodic_task_metrics(name: str) -> PeriodicTaskMetrics:
    if Counter is None or Histogram is None:  # pragma: no cover - safety
        raise RuntimeError("prometheus-client is required for periodic task metrics")

    metric_key = _sanitize_metric_name(name)
    if metric_key in _periodic_task_metrics:
        return _periodic_task_metrics[metric_key]

    prefix = f"periodic_task_{metric_key}"
    runs = Counter(
        f"{prefix}_runs_total",
        "Total successful executions of the periodic task",
    )
    errors = Counter(
        f"{prefix}_errors_total",
        "Total exceptions raised by the periodic task",
    )
    deleted = Counter(
        f"{prefix}_deleted_total",
        "Total database rows deleted by the periodic task",
    )
    duration = Histogram(
        f"{prefix}_duration_seconds",
        "Runtime of the periodic task execution in seconds",
        buckets=(
            0.01,
            0.05,
            0.1,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
            30.0,
            60.0,
            120.0,
        ),
    )

    metrics = PeriodicTaskMetrics(
        name=name,
        metric_prefix=prefix,
        runs_total=runs,
        errors_total=errors,
        deleted_total=deleted,
        duration_seconds=duration,
    )
    _periodic_task_metrics[metric_key] = metrics
    return metrics


def create_worker_monitoring_app(
    *, worker_name: str, metrics: WorkerMetrics
) -> FastAPI:
    """Build a lightweight ASGI app exposing worker metrics and health."""

    app = FastAPI(title=f"{worker_name} worker monitor", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        payload = {
            "status": metrics.status,
            "worker": worker_name,
            "last_run": metrics.last_run,
            "last_success": metrics.last_success,
            "last_failure": metrics.last_failure,
        }
        return JSONResponse(payload)

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        content = generate_latest(metrics.registry)
        return Response(content, media_type=CONTENT_TYPE_LATEST)

    return app


async def start_worker_monitoring_server(
    app: FastAPI, *, host: str, port: int
) -> Callable[[], Awaitable[None]]:
    """Start an embedded Uvicorn server for worker monitoring endpoints."""

    if port <= 0:
        raise ValueError("port must be a positive integer")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        loop="asyncio",
        access_log=False,
        log_config=None,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    await server.started.wait()

    async def _stop() -> None:
        if not server.should_exit:
            server.should_exit = True
        await task

    return _stop


def configure_worker_observability(*, worker_name: str | None = None) -> None:
    """Configure logging for standalone worker processes."""

    _configure_logging()
    if worker_name:
        logging.getLogger(__name__).info(
            "Worker %s observability configured", worker_name
        )


@dataclass
class NotificationQueueMetrics:
    """Prometheus metrics describing the notification queue state."""

    queue_size: Gauge
    dropped_jobs_total: Counter
    failed_jobs_total: Counter
    enqueue_failures_total: Counter
    processed_jobs_total: Counter
    processing_latency_seconds: Histogram
    queue_wait_time_seconds: Histogram
    retry_delay_seconds: Histogram
    dead_lettered_jobs: Gauge
    oldest_dead_letter_age_seconds: Histogram | None
    registry: CollectorRegistry

    def reset(self) -> None:
        """Best-effort helper used by tests to zero recorded values."""

        collectors = [
            self.queue_size,
            self.dropped_jobs_total,
            self.failed_jobs_total,
            self.enqueue_failures_total,
            self.processed_jobs_total,
            self.processing_latency_seconds,
            self.queue_wait_time_seconds,
            self.retry_delay_seconds,
            self.dead_lettered_jobs,
        ]
        if self.oldest_dead_letter_age_seconds is not None:
            collectors.append(self.oldest_dead_letter_age_seconds)

        for collector in collectors:
            with suppress(KeyError):
                self.registry.unregister(collector)

        fresh = create_notification_queue_metrics(registry=self.registry)
        self.queue_size = fresh.queue_size
        self.dropped_jobs_total = fresh.dropped_jobs_total
        self.failed_jobs_total = fresh.failed_jobs_total
        self.enqueue_failures_total = fresh.enqueue_failures_total
        self.processed_jobs_total = fresh.processed_jobs_total
        self.processing_latency_seconds = fresh.processing_latency_seconds
        self.queue_wait_time_seconds = fresh.queue_wait_time_seconds
        self.retry_delay_seconds = fresh.retry_delay_seconds
        self.dead_lettered_jobs = fresh.dead_lettered_jobs
        self.oldest_dead_letter_age_seconds = fresh.oldest_dead_letter_age_seconds


def get_notification_queue_metrics() -> NotificationQueueMetrics:
    """Return a singleton bundle of Prometheus metrics for the queue."""

    global _notification_queue_metrics
    if _notification_queue_metrics is None:
        if (
            Gauge is None
            or Counter is None
            or Histogram is None
            or CollectorRegistry is None
            or REGISTRY is None
        ):  # pragma: no cover
            raise RuntimeError(
                "prometheus-client is required to create notification queue metrics"
            )

        _notification_queue_metrics = create_notification_queue_metrics(
            registry=REGISTRY
        )

    return _notification_queue_metrics


def create_notification_queue_metrics(
    *, registry: CollectorRegistry | None = None
) -> NotificationQueueMetrics:
    """Create a new bundle of notification queue metrics."""

    if (
        Gauge is None
        or Counter is None
        or Histogram is None
        or CollectorRegistry is None
        or REGISTRY is None
    ):  # pragma: no cover - optional dependency guard
        raise RuntimeError(
            "prometheus-client is required to create notification queue metrics"
        )

    target_registry = registry or REGISTRY

    metrics = NotificationQueueMetrics(
        queue_size=Gauge(
            "notification_queue_size",
            "Number of pending notification jobs awaiting processing",
            registry=target_registry,
        ),
        dropped_jobs_total=Counter(
            "notification_queue_dropped_jobs_total",
            "Total notification jobs dropped due to queue saturation",
            labelnames=("kind",),
            registry=target_registry,
        ),
        failed_jobs_total=Counter(
            "notification_queue_failed_jobs_total",
            "Total notification jobs permanently failed or dead-lettered",
            labelnames=("kind",),
            registry=target_registry,
        ),
        enqueue_failures_total=Counter(
            "notification_queue_enqueue_failures_total",
            "Total notification jobs that failed to be enqueued",
            labelnames=("kind",),
            registry=target_registry,
        ),
        processed_jobs_total=Counter(
            "notification_queue_processed_jobs_total",
            "Total notification jobs successfully processed",
            labelnames=("kind",),
            registry=target_registry,
        ),
        processing_latency_seconds=Histogram(
            "notification_queue_processing_latency_seconds",
            "Time spent processing individual notification jobs in seconds",
            buckets=(
                0.01,
                0.05,
                0.1,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
            ),
            registry=target_registry,
        ),
        queue_wait_time_seconds=Histogram(
            "notification_queue_queue_wait_time_seconds",
            "Time notification jobs spend waiting in the queue before processing",
            labelnames=("kind",),
            buckets=(
                0.01,
                0.05,
                0.1,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                30.0,
                60.0,
            ),
            registry=target_registry,
        ),
        retry_delay_seconds=Histogram(
            "notification_queue_retry_delay_seconds",
            "Delay applied before retrying failed notification jobs",
            labelnames=("kind",),
            buckets=(
                0.01,
                0.05,
                0.1,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                30.0,
                60.0,
                120.0,
            ),
            registry=target_registry,
        ),
        dead_lettered_jobs=Gauge(
            "notification_queue_dead_lettered_jobs",
            "Number of notification jobs in the dead-letter queue",
            registry=target_registry,
        ),
        oldest_dead_letter_age_seconds=Histogram(
            "notification_queue_oldest_dead_letter_age_seconds",
            "Age in seconds of the oldest dead-lettered notification job",
            buckets=(
                1.0,
                5.0,
                10.0,
                30.0,
                60.0,
                300.0,
                600.0,
                1800.0,
                3600.0,
            ),
            registry=target_registry,
        ),
        registry=target_registry,
    )
    metrics.queue_size.set(0)
    metrics.dead_lettered_jobs.set(0)
    return metrics


def reinitialize_notification_queue_metrics(
    *, registry: CollectorRegistry | None = None
) -> NotificationQueueMetrics:
    """Replace the cached notification queue metrics with a fresh instance."""

    global _notification_queue_metrics

    if _notification_queue_metrics is not None:
        previous_collectors = [
            _notification_queue_metrics.queue_size,
            _notification_queue_metrics.dropped_jobs_total,
            _notification_queue_metrics.failed_jobs_total,
            _notification_queue_metrics.enqueue_failures_total,
            _notification_queue_metrics.processed_jobs_total,
            _notification_queue_metrics.processing_latency_seconds,
            _notification_queue_metrics.queue_wait_time_seconds,
            _notification_queue_metrics.retry_delay_seconds,
            _notification_queue_metrics.dead_lettered_jobs,
        ]
        if _notification_queue_metrics.oldest_dead_letter_age_seconds is not None:
            previous_collectors.append(
                _notification_queue_metrics.oldest_dead_letter_age_seconds
            )
        for collector in previous_collectors:
            with suppress(KeyError):
                _notification_queue_metrics.registry.unregister(collector)

    target_registry = registry or (CollectorRegistry() if CollectorRegistry else None)
    metrics = create_notification_queue_metrics(registry=target_registry)
    _notification_queue_metrics = metrics
    return metrics
