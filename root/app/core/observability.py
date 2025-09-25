from __future__ import annotations

import json
import logging
import socket
import uuid
from contextlib import suppress
from contextvars import ContextVar
from typing import Any, Iterable, Mapping

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, set_logger_provider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from sentry_sdk import init as sentry_init
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings


_logging_configured = False
_otel_configured = False
_sqlalchemy_instrumented = False
_otel_logger_provider: LoggerProvider | None = None
_otel_logging_handler: LoggingHandler | None = None

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the request correlation identifier from the current context."""

    return _request_id_ctx.get(None)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Populate and propagate a correlation identifier for every request."""

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
    """Append trace/span/request identifiers to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging glue
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
    """Render log records as structured JSON strings."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - logging glue
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
    if not settings.sentry_dsn:
        return

    sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
    sentry_init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[FastApiIntegration(), sentry_logging],
        send_default_pii=False,
    )

    if tracer_provider is not None:
        tracer_provider.add_span_processor(SentrySpanProcessor())


def _configure_otel(engine: AsyncEngine) -> TracerProvider | None:
    global _otel_configured, _sqlalchemy_instrumented
    if not settings.enable_otel:
        return None
    if _otel_configured:
        return trace.get_tracer_provider()  # type: ignore[return-value]

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.instance.id": socket.gethostname(),
            "deployment.environment": settings.environment,
        }
    )

    sampler = ParentBased(TraceIdRatioBased(max(min(settings.otel_trace_sampler_ratio, 1.0), 0.0)))
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
        except Exception:  # pragma: no cover - defensive guard
            pass

    _otel_configured = True
    return tracer_provider


def configure_observability(app: FastAPI, *, engine: AsyncEngine) -> None:
    """Initialise logging, tracing, metrics and error reporting."""

    if not getattr(app.state, "observability_configured", False):
        _configure_logging()
        app.add_middleware(CorrelationIdMiddleware, header_name=settings.request_id_header)
        tracer_provider = _configure_otel(engine)
        _configure_sentry(tracer_provider)

        if settings.enable_otel and not getattr(app.state, "otel_instrumented", False):
            try:
                FastAPIInstrumentor.instrument_app(
                    app,
                    tracer_provider=trace.get_tracer_provider(),
                    meter_provider=metrics.get_meter_provider(),
                )
            except Exception:  # pragma: no cover - defensive guard
                pass
            app.state.otel_instrumented = True

        app.state.observability_configured = True


def shutdown_observability() -> None:
    """Flush telemetry providers when the application stops."""

    provider = trace.get_tracer_provider()
    with suppress(Exception):  # pragma: no cover - best effort
        if isinstance(provider, TracerProvider):
            provider.shutdown()

    meter_provider = metrics.get_meter_provider()
    with suppress(Exception):  # pragma: no cover - best effort
        if isinstance(meter_provider, MeterProvider):
            meter_provider.shutdown()

    if _otel_logging_handler is not None:
        with suppress(Exception):  # pragma: no cover - best effort
            logging.getLogger().removeHandler(_otel_logging_handler)

    if _otel_logger_provider is not None:
        with suppress(Exception):  # pragma: no cover - best effort
            _otel_logger_provider.shutdown()

