from unittest.mock import patch

import pytest
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.observability import (
    _build_otel_resource_attributes,
    _configure_otel,
    _create_otel_resource,
)


@pytest.fixture(autouse=True)
def _reset_otel():
    import app.core.observability as obs

    obs.shutdown_observability()
    original_configured = obs._otel_configured
    original_instrumented = obs._sqlalchemy_instrumented
    original_shutdown = obs._otel_shutdown
    obs._otel_shutdown = False
    obs._otel_configured = False
    obs._sqlalchemy_instrumented = False
    with (
        patch("app.core.observability.trace.set_tracer_provider"),
        patch("app.core.observability.metrics.set_meter_provider"),
    ):
        yield
        obs.shutdown_observability()
    obs._otel_shutdown = original_shutdown
    obs._otel_configured = original_configured
    obs._sqlalchemy_instrumented = original_instrumented


@pytest.mark.asyncio
async def test_otel_span_generation():
    """Verify that _configure_otel returns a valid SDK TracerProvider when enabled."""
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

        with (
            patch("app.core.observability.OTLPSpanExporter"),
            patch("app.core.observability.FastAPIInstrumentor"),
            patch(
                "app.core.observability.SQLAlchemyInstrumentor"
            ) as sqlalchemy_instrumentor,
        ):
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            tracer_provider = _configure_otel(engine)

            assert tracer_provider is not None
            assert isinstance(tracer_provider, SDKTracerProvider)

            tracer = tracer_provider.get_tracer("test-tracer")
            assert tracer is not None
            instrument_call = sqlalchemy_instrumentor.return_value.instrument.call_args
            assert instrument_call is not None
            assert instrument_call.kwargs["enable_metrics"] is False
            assert instrument_call.kwargs["meter_provider"] is None

            await engine.dispose()


def test_otel_disabled():
    """Verify that _configure_otel returns None when OTel is disabled."""
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = False
        tracer_provider = _configure_otel(None)
        assert tracer_provider is None


def test_otel_resource_attributes():
    """Verify built OTel resource attributes capture metadata."""
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.otel_service_name = "my-service"
        mock_settings.environment = "staging"
        mock_settings.service_version = "2.4.6"

        attrs = _build_otel_resource_attributes()
        assert attrs["service.name"] == "my-service"
        assert attrs["deployment.environment"] == "staging"
        assert attrs["service.version"] == "2.4.6"


def test_otel_resource_creation():
    """Verify Resource.create includes required service name."""
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.otel_service_name = "test-resource-service"
        mock_settings.environment = "testing"
        mock_settings.service_version = "0.0.1"

        res = _create_otel_resource()
        assert isinstance(res, Resource)
        assert res.attributes["service.name"] == "test-resource-service"


@pytest.mark.asyncio
async def test_otel_sampler_configuration():
    """Verify trace sampler gets correctly configured based on settings."""
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        mock_settings.otel_trace_sampler_ratio = 0.5
        mock_settings.otel_service_name = "test-sampler"
        mock_settings.otel_exporter_otlp_endpoint = None
        mock_settings.enable_otel_metrics = False
        mock_settings.enable_otel_logs = False
        mock_settings.otel_exporter_otlp_headers = {}

        with patch("app.core.observability.OTLPSpanExporter"):
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            tracer_provider = _configure_otel(engine)
            assert tracer_provider is not None

            # Assert sampler is ParentBased wrap around TraceIdRatioBased sampler
            sampler = tracer_provider.sampler
            assert isinstance(sampler, ParentBased)
            # The root sampler should be TraceIdRatioBased(0.5)
            assert isinstance(sampler._root, TraceIdRatioBased)
            rate = getattr(sampler._root, "rate", getattr(sampler._root, "_rate", None))
            assert rate == 0.5

            await engine.dispose()


@pytest.mark.asyncio
async def test_otel_composite_propagator():
    """Verify that global composite propagator is set correctly."""
    from opentelemetry.propagate import get_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator

    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = True
        mock_settings.otel_service_name = "test-propagator"
        mock_settings.otel_exporter_otlp_endpoint = None
        mock_settings.otel_trace_sampler_ratio = 1.0
        mock_settings.enable_otel_metrics = False
        mock_settings.enable_otel_logs = False
        mock_settings.otel_exporter_otlp_headers = {}

        with patch("app.core.observability.OTLPSpanExporter"):
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            _configure_otel(engine)

            global_propagator = get_global_textmap()
            assert isinstance(global_propagator, CompositePropagator)

            # Assert it includes both TraceContextTextMapPropagator and W3CBaggagePropagator
            propagators = global_propagator._propagators
            assert any(
                isinstance(p, TraceContextTextMapPropagator) for p in propagators
            )
            assert any(isinstance(p, W3CBaggagePropagator) for p in propagators)

            await engine.dispose()
