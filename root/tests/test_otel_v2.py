from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.observability import _configure_otel


@pytest.mark.anyio
async def test_otel_span_generation():
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
            from opentelemetry.sdk.trace import Tracer as SDKTracer
            from opentelemetry.context import Context
            
            # Re-verify it's an SDK provider
            assert isinstance(tracer_provider, SDKTracerProvider)
            
            # Ensure we have a recorder and it's not sampled out
            import uuid
            tracer = tracer_provider.get_tracer(f"test-tracer-{uuid.uuid4().hex}")
            assert isinstance(tracer, SDKTracer)
            
            # Use start_span with explicit empty context to avoid parent inheritance
            span = tracer.start_span("test-span", context=Context())
            try:
                if not span.is_recording():
                    # Diagnostic info if it still fails
                    print(f"\nFAIL DEBUG: Provider: {tracer_provider}")
                    print(f"FAIL DEBUG: Sampler: {tracer_provider.sampler}")
                    print(f"FAIL DEBUG: Tracer: {tracer}")
                    print(f"FAIL DEBUG: Span Context: {span.get_span_context()}")
                
                assert span.is_recording()
                span.set_attribute("test.attr", "value")
            finally:
                span.end()

            await engine.dispose()


def test_otel_disabled():
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = False
        # engine=None is fine for this test as it should return early
        tracer_provider = _configure_otel(None)
        assert tracer_provider is None
