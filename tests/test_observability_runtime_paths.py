"""Observability configuration and worker runtime-path tests."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import app.core.observability


@pytest.fixture(autouse=True)
def reset_otel_state():
    """Reset module-level OTel flags before every test.

    _configure_otel sets _otel_configured=True and registers global
    OTel providers as a side-effect. Without cleanup the state leaks
    across tests (e.g. configure_observability sees the flag and skips
    its own setup, causing subsequent assertions to fail).

    We must also remove any LoggingHandler added to the root logger;
    leftover handlers compare log levels against their logger_provider,
    which may be a MagicMock, causing TypeError in subsequent tests.
    """
    app.core.observability._otel_configured = False
    app.core.observability._sqlalchemy_instrumented = False
    yield
    # Tear down OTel logging handler if one was installed during the test
    handler = app.core.observability._otel_logging_handler
    if handler is not None:
        import logging

        logging.getLogger().removeHandler(handler)
    app.core.observability._otel_configured = False
    app.core.observability._sqlalchemy_instrumented = False
    app.core.observability._otel_logger_provider = None
    app.core.observability._otel_logging_handler = None


def test_resolve_current_trace_id_valid_span():
    mock_span = MagicMock()
    mock_span_context = MagicMock()
    mock_span_context.is_valid = True
    mock_span_context.trace_id = 0x123456789ABCDEF0123456789ABCDEF0
    mock_span.get_span_context.return_value = mock_span_context

    with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
        res = app.core.observability._resolve_current_trace_id()
        assert res == "123456789abcdef0123456789abcdef0"  # pragma: allowlist secret


def test_configure_sentry():
    with (
        patch("app.core.observability.sentry_init") as mock_init,
        patch("app.core.observability.settings") as mock_settings,
    ):
        mock_settings.sentry_dsn = "http://dsn@sentry.io/1"
        mock_settings.sentry_environment = "test"
        mock_settings.sentry_traces_sample_rate = 1.0
        mock_settings.sentry_profiles_sample_rate = 1.0
        mock_settings.service_version = "1.0.0"

        app.core.observability._configure_sentry(MagicMock())
        mock_init.assert_called()


def test_configure_otel_concurrency():
    # _configure_otel checks settings.enable_otel before the _otel_configured
    # flag, so we must patch enable_otel=True to reach the fast-path branches.
    # We also patch trace.get_tracer_provider so the fast-paths return a mock
    # instead of starting real OTLP exporters/background threads.

    mock_provider = MagicMock()

    # Branch 1: _otel_configured=True → early-return via get_tracer_provider()
    with (
        patch("app.core.observability.settings") as mock_settings,
        patch(
            "app.core.observability.trace.get_tracer_provider",
            return_value=mock_provider,
        ),
    ):
        mock_settings.enable_otel = True
        app.core.observability._otel_configured = True
        res = app.core.observability._configure_otel(MagicMock())
        assert res is not None

    # Reset and test Branch 2: _otel_configured becomes True inside the lock
    app.core.observability._otel_configured = False

    class MockOtelLock:
        def __enter__(self):
            app.core.observability._otel_configured = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with (
        patch("app.core.observability.settings") as mock_settings,
        patch(
            "app.core.observability.trace.get_tracer_provider",
            return_value=mock_provider,
        ),
        patch("app.core.observability._otel_lock", MockOtelLock()),
    ):
        mock_settings.enable_otel = True
        res = app.core.observability._configure_otel(MagicMock())
        assert res is not None


def test_configure_otel_instrumentation_errors():
    # Mock all heavyweight OTel constructors so no real gRPC threads are
    # spawned (real OTLP exporters try to connect to localhost:4317).
    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability.TracerProvider", return_value=MagicMock()),
        patch("app.core.observability.MeterProvider", return_value=MagicMock()),
        patch("app.core.observability.LoggerProvider", return_value=MagicMock()),
        patch("app.core.observability.OTLPSpanExporter"),
        patch("app.core.observability.OTLPMetricExporter"),
        patch("app.core.observability.OTLPLogExporter"),
        patch("app.core.observability.PeriodicExportingMetricReader"),
        patch("app.core.observability.BatchSpanProcessor"),
        patch("app.core.observability.BatchLogRecordProcessor"),
        patch("app.core.observability.LoggingHandler"),
        patch("app.core.observability.trace.set_tracer_provider"),
        patch("app.core.observability.metrics.set_meter_provider"),
        patch("app.core.observability.set_global_textmap"),
        patch("app.core.observability.set_logger_provider"),
        patch(
            "app.core.observability.SQLAlchemyInstrumentor.instrument",
            side_effect=RuntimeError,
        ),
        patch(
            "app.core.observability.RedisInstrumentor.instrument",
            side_effect=RuntimeError,
        ),
        patch(
            "app.core.observability.HTTPXClientInstrumentor.instrument",
            side_effect=RuntimeError,
        ),
    ):
        mock_settings.enable_otel = True
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_settings.otel_exporter_otlp_headers = "a=b,c=d"
        mock_settings.otel_trace_sampler_ratio = 1.0
        mock_settings.enable_otel_metrics = True
        mock_settings.enable_otel_logs = True

        res = app.core.observability._configure_otel(MagicMock())
        assert res is not None


def test_configure_observability_instrument_app_error():
    mock_app = MagicMock()
    mock_app.state.observability_configured = False
    mock_app.state.otel_instrumented = False

    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability._configure_logging"),
        patch("app.core.observability._configure_sentry"),
        patch(
            "app.core.observability.FastAPIInstrumentor.instrument_app",
            side_effect=RuntimeError,
        ),
        patch("app.core.observability._configure_otel") as mock_conf_otel,
    ):
        mock_settings.enable_otel = True
        mock_conf_otel.return_value = MagicMock()

        app.core.observability.configure_observability(mock_app, engine=MagicMock())
        # Should catch RuntimeError and set app.state.otel_instrumented = True
        assert mock_app.state.otel_instrumented


def test_shutdown_observability_supports_legacy_meter_shutdown_signature():
    from opentelemetry.sdk.metrics import MeterProvider

    class LegacyMeterProvider(MeterProvider):
        def __init__(self) -> None:
            self.shutdown_calls = 0

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    meter_provider = LegacyMeterProvider()
    with (
        patch(
            "app.core.observability.trace.get_tracer_provider", return_value=MagicMock()
        ),
        patch(
            "app.core.observability.metrics.get_meter_provider",
            return_value=meter_provider,
        ),
        patch("app.core.observability._otel_logging_handler", None),
        patch("app.core.observability._otel_logger_provider", None),
    ):
        app.core.observability.shutdown_observability()

    assert meter_provider.shutdown_calls == 1


def test_get_periodic_task_metrics_cache():
    m1 = app.core.observability.get_periodic_task_metrics("test_task")
    m2 = app.core.observability.get_periodic_task_metrics("test_task")
    assert m1 is m2


@pytest.mark.asyncio
async def test_start_worker_monitoring_server_old_uvicorn():
    mock_server = MagicMock()
    mock_event = asyncio.Event()
    mock_server.started = mock_event
    mock_server.should_exit = False

    async def mock_serve():
        mock_event.set()

    mock_server.serve = mock_serve

    with patch("uvicorn.Server", return_value=mock_server):
        stop_fn = await app.core.observability.start_worker_monitoring_server(
            MagicMock(), host="127.0.0.1", port=8000
        )
        await stop_fn()


def test_configure_worker_observability():
    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability._configure_logging"),
        patch("app.core.observability._configure_otel") as mock_conf_otel,
    ):
        mock_settings.enable_otel = True
        mock_conf_otel.return_value = MagicMock()

        app.core.observability.configure_worker_observability(
            worker_name="test_worker", engine=MagicMock()
        )
        mock_conf_otel.assert_called_once()
