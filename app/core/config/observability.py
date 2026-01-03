from __future__ import annotations

from pydantic import AliasChoices, Field

from .base import BaseAppSettings


class ObservabilitySettings(BaseAppSettings):
    enable_otel: bool = True
    otel_service_name: str = "university-ecosystem"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_exporter_otlp_headers: str = ""
    otel_trace_sampler_ratio: float = 1.0
    enable_otel_metrics: bool = True
    enable_otel_logs: bool = True
    service_version: str = Field(
        default="",
        validation_alias=AliasChoices("service_version", "app_version"),
    )
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_profiles_sample_rate: float = 0.0
    sentry_environment: str = ""
    log_level: str = "INFO"
