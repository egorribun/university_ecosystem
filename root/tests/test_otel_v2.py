from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.observability import _configure_otel


@pytest.mark.anyio
async def test_otel_span_generation():
    # Mock settings to enable OTel
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        mock_settings.otel_service_name = "test-service"
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_settings.otel_trace_sampler_ratio = 1.0
        mock_settings.enable_otel_metrics = False
        mock_settings.enable_otel_logs = False

        # Mock exporters to avoid network calls
        with (
            patch("app.core.observability.OTLPSpanExporter"),
            patch("app.core.observability.BatchSpanProcessor"),
            patch("app.core.observability.FastAPIInstrumentor"),
            patch("app.core.observability.SQLAlchemyInstrumentor"),
        ):
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            tracer_provider = _configure_otel(engine)

            assert tracer_provider is not None

            # Get a tracer and start a span
            tracer = tracer_provider.get_tracer(__name__)
            with tracer.start_as_current_span("test-span") as span:
                assert span.is_recording()
                span.set_attribute("test.attr", "value")

            await engine.dispose()


def test_otel_disabled():
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = False
        # engine=None is fine for this test as it should return early
        tracer_provider = _configure_otel(None)
        assert tracer_provider is None
