"""Pydantic-settings for background worker configuration.

MOD-06 (audit 2026-03-14): Centralises OutboxWorker tuning parameters behind
validated Pydantic fields.  Previously the worker read raw env vars or used
hard-coded defaults.  By using BaseSettings:

- Bad values (e.g. batch_size=-1) fail at startup with a clear error.
- All env var names are self-documenting in one place.
- Test fixtures can override values by constructing OutboxWorkerSettings()
  with explicit kwargs rather than monkey-patching env vars.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class OutboxWorkerSettings(BaseSettings):
    """Configuration for the transactional outbox worker.

    All fields can be overridden via environment variables using the same name
    in UPPER_CASE (e.g. OUTBOX_BATCH_SIZE=100).
    """

    model_config = {"env_prefix": "", "case_sensitive": False}

    outbox_batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Number of StoredEvents processed per poll cycle.  "
        "Higher values increase throughput but hold DB locks longer.",
    )
    outbox_poll_interval: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Maximum seconds to wait between poll cycles when the "
        "LISTEN/NOTIFY channel is quiet.",
    )
    outbox_max_retries: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of dispatch attempts before an event is moved "
        "to the Dead Letter Queue.",
    )
    outbox_retry_backoff_base: float = Field(
        default=2.0,
        ge=1.1,
        le=10.0,
        description="Exponential-backoff base (seconds).  Unused retry N "
        "waits backoff_base^N seconds before re-picking the event.",
    )
    outbox_dead_letter_after: int = Field(
        default=10,
        ge=1,
        description="Alternative DLQ threshold when max_retries is not "
        "sufficient.  Currently mirrors max_retries; reserved for future "
        "per-event-type tuning.",
    )


# Module-level singleton — instantiate once so pydantic reads env vars once.
outbox_worker_settings = OutboxWorkerSettings()
