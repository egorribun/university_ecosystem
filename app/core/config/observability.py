from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, Field, SecretStr

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
    # Trusted field-CWV collection is opt-in and validated fail-closed at startup.
    cwv_rum_enabled: bool = False
    cwv_rum_signing_secret: SecretStr = SecretStr("")
    cwv_release_sha: str = ""
    cwv_frontend_image_digest: str = ""
    cwv_deployment_run_id: int = 0
    cwv_deployment_run_attempt: int = 0
    cwv_deployment_url: str = ""
    cwv_deployed_at: datetime | None = None
    cwv_allowed_origins: str = ""
    cwv_envelope_ttl_seconds: int = 300
    # Operator-curated manual staging testers. Kept in the application Secret;
    # raw UUIDs never enter observations or exported evidence.
    cwv_manual_tester_user_ids: SecretStr = SecretStr("")
    cwv_retention_days: int = 30
    cwv_export_oidc_enabled: bool = False
    cwv_export_oidc_repository: str = ""
    cwv_export_oidc_workflow_ref: str = ""
    cwv_export_oidc_subject: str = ""
