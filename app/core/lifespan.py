import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine, wait_db
from app.core.events import register_event_listeners
from app.core.observability import shutdown_observability
from app.deps.cache import shutdown_cache
from app.services import notification_queue, webpush
from app.services.cache_warmup import warm_cache
from app.services.partition_manager import (
    ensure_partitions_exist,
    start_partition_management_scheduler,
)
from app.tasks.cleanups import setup_periodic_cleanups
from app.workers.outbox import OutboxWorker

_logger = logging.getLogger(__name__)

# TD-3 (audit 2026-03-05): Module-level stop event so _shutdown_subsystems can
# interrupt the scheduler sleep instantly instead of waiting 3600 s to expire.
_SCHEDULER_STOP: asyncio.Event = asyncio.Event()


@dataclass
class RuntimeFeatureOverrides:
    """Typed container for post-startup feature flag overrides.

    TD-1 (audit 2026-03-05): Replaces the raw dict[str, bool] pattern which
    allowed arbitrary keys and provided no IDE auto-complete or type safety.
    Callers use resolve() to merge the override with the pydantic Settings default.

    Usage:
        enabled = runtime_flags.resolve(
            "semantic_search_enabled",
            default=settings.semantic_search_enabled,
        )
    """

    semantic_search_enabled: bool | None = field(default=None)

    def resolve(self, flag: str, *, default: bool) -> bool:
        """Return override value if set, otherwise the Settings default."""
        override = getattr(self, flag, None)
        return default if override is None else override

    def disable(self, flag: str) -> None:
        """Disable a feature flag at runtime (e.g. when a dependency is unavailable)."""
        if not hasattr(self, flag):
            raise AttributeError(f"Unknown runtime flag: {flag!r}")
        object.__setattr__(self, flag, False)


runtime_flags = RuntimeFeatureOverrides()
# Back-compat alias used inside this module only — external callers should import
# `runtime_flags` and use .resolve() / .disable().
_RUNTIME_FLAGS: dict[str, bool] = {}


async def _startup_database_and_di(app: FastAPI) -> None:
    """Stage 1: Core infrastructure bootstrapping."""

    # RZ-5 (audit 2026-03-05): Fail fast in production when SPOTIFY_TOKEN_SECRET
    # is not independently configured. Using SECRET_KEY as fallback couples Spotify
    # token encryption to JWT signing — a routine SECRET_KEY rotation silently
    # invalidates all stored Spotify OAuth tokens with no error surfaced to users.
    if not settings.spotify_token_secret:
        if settings.environment not in {"development", "local", "testing"}:
            raise RuntimeError(
                "SPOTIFY_TOKEN_SECRET must be set to an independent Fernet key. "
                "Falling back to SECRET_KEY couples Spotify token encryption to JWT "
                "signing — rotating SECRET_KEY will silently invalidate all stored "
                "Spotify OAuth tokens. Set SPOTIFY_TOKEN_SECRET in your .env file."
            )
        _logger.warning(
            "SPOTIFY_TOKEN_SECRET is not set — Spotify token encryption falls back to "
            "a key derived from SECRET_KEY. Rotating SECRET_KEY will invalidate all "
            "stored Spotify OAuth tokens. Set SPOTIFY_TOKEN_SECRET to an independent "
            "Fernet key to decouple the two secrets. (dev/local/testing mode only)"
        )


async def _startup_websocket_and_flags(app: FastAPI) -> None:
    """Stage 2: WebSocket management and feature flag recovery."""
    import app.api.websocket as _ws_module
    from app.api.websocket import ConnectionManager, start_presence_pubsub
    from app.core.feature_flags import feature_flags

    _cm = ConnectionManager()
    app.state.connection_manager = _cm
    _ws_module.manager = _cm

    await feature_flags.initialize()
    await start_presence_pubsub()


async def _verify_database_readiness() -> None:
    """Stage 3: Connectivity and migration alignment checks."""
    try:
        await asyncio.wait_for(wait_db(max_attempts=10, delay=0.5), timeout=5.0)
    except (TimeoutError, Exception) as exc:
        if settings.environment not in {"development", "local", "testing"}:
            raise
        _logger.warning("Database unavailable: %s. Continuing (degraded mode).", exc)

    if settings.environment not in {"testing", "test"}:
        try:
            from alembic.config import Config as AlembicConfig
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            _alembic_cfg = AlembicConfig("alembic.ini")
            _scripts = ScriptDirectory.from_config(_alembic_cfg)
            _head = _scripts.get_current_head()

            async with engine.connect() as _conn:
                if _conn.dialect.name == "postgresql":
                    _ctx = await _conn.run_sync(
                        lambda sync_conn: MigrationContext.configure(sync_conn)
                    )
                    _current = _ctx.get_current_revision()
                    if _current != _head:
                        raise RuntimeError(
                            f"DB schema mismatch — current={_current!r}, head={_head!r}."
                        )
        except Exception as exc:
            if settings.environment not in {"development", "local", "testing"}:
                raise
            _logger.warning("Migration head check skipped/failed: %s", exc)


async def _handle_schema_and_extensions() -> None:
    """Stage 4: Automated schema maintenance and extension patching."""
    if not settings.auto_create_schema:
        return

    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                except Exception as e:
                    _logger.warning("pgvector unavailable: %s", e)
                    _RUNTIME_FLAGS["semantic_search_enabled"] = False
            else:
                # Patch SQLite for tests
                for table in Base.metadata.tables.values():
                    for column in table.columns:
                        if column.computed is not None and "to_tsvector" in str(
                            column.computed.sqltext
                        ):
                            column.computed = None

            await conn.run_sync(
                lambda sc: Base.metadata.create_all(bind=sc, checkfirst=True)
            )
    except Exception as exc:
        if settings.environment not in {"development", "local", "testing"}:
            raise
        _logger.warning("Auto-schema failed: %s", exc)


async def _startup_background_workers(app: FastAPI) -> None:
    """Stage 5: Pub/Sub workers, Outbox, and NATS task processors."""
    from app.core.nats_broker import NatsTaskBroker

    await setup_periodic_cleanups()

    if not hasattr(app.state, "background_tasks"):
        app.state.background_tasks = set()

    # Orchestrate periodic background loop
    app.state.background_tasks.add(
        asyncio.create_task(_periodic_scheduler_loop(), name="periodic_scheduler")
    )

    # Boot components from DI container
    outbox_worker = await app.state.dishka_container.get(OutboxWorker)
    outbox_task = asyncio.create_task(outbox_worker.run_forever(), name="outbox_worker")
    app.state.background_tasks.add(outbox_task)

    nats_broker = await app.state.dishka_container.get(NatsTaskBroker)
    if nats_broker.is_connected:
        app.state.background_tasks.add(
            asyncio.create_task(nats_broker.run_worker(), name="nats_worker")
        )

    if settings.partition_management_enabled:
        try:
            await ensure_partitions_exist()
            app.state.partition_stopper = await start_partition_management_scheduler(
                settings.partition_management_interval_seconds
            )
        except Exception as exc:
            _logger.warning("Partition init failed: %s", exc)


async def _periodic_scheduler_loop() -> None:
    """Internal loop for fanned-out periodic cleanup tasks.

    Design notes (TD-3, audit 2026-03-05):
    - Jitter: sleeps a random 0–60 s before the first run to spread load
      across instances on rolling deploys (thundering herd mitigation).
    - Deduplication: tracks the last UTC hour in which tasks actually ran;
      if the event loop wakes within the same hour it skips immediately.
    - Graceful shutdown: waits on _SCHEDULER_STOP so _shutdown_subsystems
      can signal termination and the task exits in under 1 s instead of
      blocking for up to 3600 s.
    """
    from app.tasks.cleanups import (
        cleanup_dead_letter_jobs_task,
        cleanup_email_change_tokens_task,
        cleanup_mfa_challenges_task,
        cleanup_notifications_task,
        cleanup_password_reset_tokens_task,
        cleanup_privacy_artifacts_task,
        cleanup_sessions_task,
        cleanup_stories_task,
        manage_partitions_task,
    )

    async def _kick(task: Any) -> None:
        try:
            async with asyncio.timeout(300):
                await task.kick()
        except Exception:
            _logger.exception("Cleanup failed for %s", task.__class__.__name__)

    async def _sleep_or_stop(seconds: float) -> bool:
        """Sleep for *seconds* or return True immediately if stop is signalled."""
        try:
            await asyncio.wait_for(_SCHEDULER_STOP.wait(), timeout=seconds)
            return True  # stop requested
        except TimeoutError:
            return False  # normal timeout — continue

    # Jitter: spread first execution across 0–60 s
    jitter = random.uniform(0, 60)
    _logger.debug("Periodic scheduler: initial jitter %.1f s", jitter)
    if await _sleep_or_stop(jitter):
        return

    _last_hour_ran: int = -1

    while not _SCHEDULER_STOP.is_set():
        import datetime

        now_utc = datetime.datetime.now(datetime.UTC)
        cur_hour = now_utc.hour

        # Deduplication: skip if already ran this hour (clock drift / fast restart guard)
        if cur_hour != _last_hour_ran:
            tasks = [
                cleanup_stories_task,
                cleanup_password_reset_tokens_task,
                cleanup_email_change_tokens_task,
                cleanup_mfa_challenges_task,
            ]

            if cur_hour % 6 == 0:
                tasks.append(cleanup_sessions_task)
            if cur_hour == 2:
                tasks.extend(
                    [
                        cleanup_notifications_task,
                        cleanup_dead_letter_jobs_task,
                        cleanup_privacy_artifacts_task,
                        manage_partitions_task,
                    ]
                )

            await asyncio.gather(*(_kick(t) for t in tasks))
            _last_hour_ran = cur_hour

        if await _sleep_or_stop(3600):
            break


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Granular startup and shutdown orchestration (TD-004 decomposition)."""
    # 1. Bootstrapping
    await _startup_database_and_di(app)
    await _startup_websocket_and_flags(app)

    # 2. Validation
    await _verify_database_readiness()
    await _handle_schema_and_extensions()

    # 3. Business Logic Registration
    await register_event_listeners()
    from app.services.event_handlers import configure_event_handlers

    configure_event_handlers()

    # 4. Workers & Data Warming
    await _startup_background_workers(app)

    from app.core.rate_limit import start_memory_cleanup_task

    start_memory_cleanup_task()

    try:
        await warm_cache()
    except Exception as exc:
        _logger.warning("Warm cache failed: %s", exc)

    try:
        yield
    finally:
        await _shutdown_subsystems(app)


async def _shutdown_subsystems(app: FastAPI) -> None:
    """Graceful termination of all fanned-out components and pools."""
    from app.api.websocket import stop_presence_pubsub
    from app.auth.security import close_hibp_client
    from app.core.feature_flags import feature_flags
    from app.core.rate_limit import stop_memory_cleanup_task
    from app.services.geolocation import shutdown_geolocation_service

    # TD-3: Signal the periodic scheduler to stop before cancelling tasks,
    # so it exits its current sleep immediately via asyncio.Event.
    _SCHEDULER_STOP.set()

    # Cancel background noise first
    _bg_tasks = list(getattr(app.state, "background_tasks", set()))
    for t in _bg_tasks:
        t.cancel()
    if _bg_tasks:
        await asyncio.gather(*_bg_tasks, return_exceptions=True)

    # Orderly pool and client teardown
    await app.state.dishka_container.close()
    await stop_presence_pubsub()
    await notification_queue.shutdown_notification_queue()
    webpush.cleanup()
    await shutdown_cache()

    if hasattr(app.state, "partition_stopper") and app.state.partition_stopper:
        await app.state.partition_stopper()

    await feature_flags.shutdown()
    await stop_memory_cleanup_task()
    shutdown_observability()
    shutdown_geolocation_service()
    await close_hibp_client()
