import asyncio
from unittest.mock import MagicMock, patch

import pytest

import app.core.observability

# Treat deprecation warnings from opentelemetry gracefully in tests
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_resolve_current_trace_id_valid_span():
    # Setup mock trace provider and valid span context
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

        mock_provider = MagicMock()

        # Test basic sentry config
        app.core.observability._configure_sentry(mock_provider)
        mock_init.assert_called()


def test_configure_otel_concurrency():
    # Set _otel_configured = True to hit fast paths
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        app.core.observability._otel_configured = True
        res = app.core.observability._configure_otel(MagicMock())
        assert res is not None

    # Reset and test with mock lock
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        app.core.observability._otel_configured = False

        class MockOtelLock:
            def __enter__(self):
                app.core.observability._otel_configured = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("app.core.observability._otel_lock", MockOtelLock()):
            res = app.core.observability._configure_otel(MagicMock())
            assert res is not None


def test_configure_otel_instrumentation_errors():
    app.core.observability._otel_configured = False
    with (
        patch("app.core.observability.settings") as mock_settings,
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
        patch("app.core.observability.OTLPSpanExporter"),
        patch("app.core.observability.OTLPMetricExporter"),
        patch("app.core.observability.OTLPLogExporter"),
        patch("app.core.observability.BatchSpanProcessor"),
        patch("app.core.observability.PeriodicExportingMetricReader"),
        patch("app.core.observability.BatchLogRecordProcessor"),
    ):
        mock_settings.enable_otel = True
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_settings.otel_exporter_otlp_headers = "a=b,c=d"
        mock_settings.otel_trace_sampler_ratio = 1.0
        mock_settings.enable_otel_metrics = True
        mock_settings.enable_otel_logs = True
        mock_settings.otel_service_name = "test-service"
        mock_settings.environment = "testing"

        engine = MagicMock()
        res = app.core.observability._configure_otel(engine)
        assert res is not None


def test_configure_observability_instrument_app_error():
    mock_app = MagicMock()
    mock_app.state.observability_configured = False
    mock_app.state.otel_instrumented = False

    with (
        patch("app.core.observability.settings") as mock_settings,
        patch(
            "app.core.observability.FastAPIInstrumentor.instrument_app",
            side_effect=RuntimeError,
        ),
        patch("app.core.observability._configure_otel") as mock_conf_otel,
    ):
        mock_settings.enable_otel = True
        mock_settings.log_level = "INFO"
        mock_settings.environment = "testing"
        mock_settings.sentry_dsn = None
        mock_conf_otel.return_value = MagicMock()

        app.core.observability.configure_observability(mock_app, engine=MagicMock())
        # Should catch RuntimeError and set app.state.otel_instrumented = True
        assert mock_app.state.otel_instrumented


def test_get_periodic_task_metrics_cache():
    m1 = app.core.observability.get_periodic_task_metrics("test_task")
    m2 = app.core.observability.get_periodic_task_metrics("test_task")
    assert m1 is m2


@pytest.mark.asyncio
async def test_start_worker_monitoring_server_old_uvicorn():
    mock_app = MagicMock()
    mock_server = MagicMock()
    mock_event = asyncio.Event()
    mock_server.started = mock_event
    mock_server.should_exit = False

    async def mock_serve():
        mock_event.set()

    mock_server.serve = mock_serve

    with patch("uvicorn.Server", return_value=mock_server):
        stop_fn = await app.core.observability.start_worker_monitoring_server(
            mock_app, host="127.0.0.1", port=8000
        )
        await stop_fn()


def test_configure_worker_observability():
    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability._configure_otel") as mock_conf_otel,
    ):
        mock_settings.enable_otel = True
        mock_settings.log_level = "INFO"
        mock_settings.environment = "testing"
        mock_conf_otel.return_value = MagicMock()

        app.core.observability.configure_worker_observability(
            worker_name="test_worker", engine=MagicMock()
        )
        mock_conf_otel.assert_called_once()
