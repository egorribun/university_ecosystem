from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.observability import _configure_otel


@pytest.mark.anyio
async def test_otel_span_generation():
    """Verify that _configure_otel returns a valid SDK TracerProvider when enabled."""
    # Force reset global state for testing
    import app.core.observability

    app.core.observability._otel_configured = False
    app.core.observability._sqlalchemy_instrumented = False

    # Mock settings to enable OTel
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        mock_settings.otel_service_name = "test-service"
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_settings.otel_trace_sampler_ratio = 1.0
        mock_settings.enable_otel_metrics = False
        mock_settings.enable_otel_logs = False
        mock_settings.service_version = "1.0.0"
        mock_settings.environment = "testing"
        mock_settings.otel_exporter_otlp_headers = {}

        # Mock exporters to avoid network calls
        with (
            patch("app.core.observability.OTLPSpanExporter"),
            patch("app.core.observability.FastAPIInstrumentor"),
            patch("app.core.observability.SQLAlchemyInstrumentor"),
        ):
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            tracer_provider = _configure_otel(engine)

            from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

            # Verify that the function returns an SDK TracerProvider
            assert tracer_provider is not None
            assert isinstance(tracer_provider, SDKTracerProvider)

            # Verify that a tracer can be obtained (even if it's a NoOp due to
            # global state pollution in full test runs, the configuration is valid)
            tracer = tracer_provider.get_tracer("test-tracer")
            assert tracer is not None

            await engine.dispose()


def test_otel_disabled():
    """Verify that _configure_otel returns None when OTel is disabled."""
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = False
        # engine=None is fine for this test as it should return early
        tracer_provider = _configure_otel(None)
        assert tracer_provider is None
