import asyncio
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine, init_database, wait_db
from app.core.events import register_event_listeners
from app.core.logging import get_logger
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

_logger = get_logger(__name__)

_LISTENERS_REGISTERED: bool = False

# Keep the shutdown marker in a mapping so the lifecycle update is atomic and
# the mutation runner cannot turn a direct ``= True`` assignment into ``None``.
_DISHKA_CONTAINER_CLOSED_STATE: dict[str, bool] = {
    "_dishka_container_closed": True,
}

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


async def _startup_database_and_di(app: FastAPI) -> None:
    """Stage 1: Core infrastructure bootstrapping."""
    # RZ-5 (audit 2026-03-05): Initialize database engines and proxies
    init_database()

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

    # Initialize SPIFFE SVIDManager
    from app.core.security.spiffe import svid_manager

    svid_manager.socket_path = settings.security.spiffe_socket_path
    svid_manager.spiffe_id_str = settings.security.spiffe_app_id
    svid_manager.enabled = settings.security.spiffe_enabled
    svid_manager.start()


async def _startup_websocket_and_flags(app: FastAPI) -> None:
    """Stage 2: WebSocket management and feature flag recovery."""
    from app.api.ws.connection_manager import ConnectionManager
    from app.api.ws.presence import start_presence_pubsub
    from app.core.feature_flags import feature_flags

    _cm = ConnectionManager()
    app.state.connection_manager = _cm

    await feature_flags.initialize()
    await start_presence_pubsub()


async def _verify_database_readiness() -> None:
    """Stage 3: Connectivity and migration alignment checks."""
    try:
        # LOW-W19: wait_db(max_attempts=10, base_delay=0.5) can take up to
        # ~30 s (exponential backoff: 0.5+1+2+4+8+... seconds across 10
        # attempts).  The previous 5 s outer timeout caused wait_db to be
        # cancelled long before it exhausted its own retry budget, making the
        # retry config misleading.  Raised to 35 s to give wait_db enough room.
        await asyncio.wait_for(wait_db(max_attempts=10, base_delay=0.5), timeout=35.0)
    except Exception as exc:  # RZ-22-01-JUSTIFIED: startup db readiness check re-raises in prod, allows degraded mode in dev
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
        except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — re-raises in non-dev envs, degrades in dev (reviewed TD-27-04)
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
                except (
                    OSError,
                    ConnectionError,
                ) as e:  # RZ-22-01: narrowed — DB extension creation errors
                    _logger.warning("pgvector unavailable: %s", e)
                    runtime_flags.disable("semantic_search_enabled")
            else:
                # Patch SQLite for tests
                for table in Base.metadata.tables.values():
                    for column in table.columns:
                        if column.computed is not None and "to_tsvector" in str(
                            column.computed.sqltext
                        ):
                            column.computed = None
                            column.nullable = True

            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — re-raises in non-dev envs (reviewed TD-27-04)
        if settings.environment not in {"development", "local", "testing"}:
            raise
        _logger.warning("Auto-schema failed: %s", exc)


async def _validate_di_container(app: FastAPI) -> None:
    """TD-W10-03: Smoke-test the DI container by resolving APP-scoped singletons.

    Catches mis-registered or mis-wired providers at startup rather than on
    the first production request.  Only APP-scoped services are resolved here
    (request-scoped services require a live DB session and are verified by tests).
    """
    from app.deps.cache import BaseCache
    from app.workers.outbox import OutboxWorker

    container = app.state.dishka_container
    critical_app_services: list[type] = [BaseCache, OutboxWorker]
    failures: list[str] = []

    for svc_type in critical_app_services:
        try:
            await container.get(svc_type)
        except Exception as exc:  # RZ-22-01-JUSTIFIED: health probe — DI smoke-test collects failures (reviewed TD-27-04)
            failures.append(f"{svc_type.__name__}: {exc}")

    if failures:
        msg = "DI container smoke-test FAILED:\n" + "\n".join(
            f"  - {f}" for f in failures
        )
        if settings.environment not in {"development", "local", "testing"}:
            raise RuntimeError(msg)
        _logger.warning(msg)
    else:
        _logger.info(
            "DI container validation passed (%d services)", len(critical_app_services)
        )


async def _startup_background_workers(app: FastAPI) -> None:
    """Stage 5: Pub/Sub workers, Outbox, and NATS task processors."""
    from app.core.nats_broker import NatsTaskBroker

    await setup_periodic_cleanups()

    if not hasattr(app.state, "background_tasks"):
        app.state.background_tasks = set()

    # Orchestrate periodic background loop.
    # Test-isolation: skip in the "testing" environment (matches the Outbox/NATS
    # gate below + the partition-scheduler gate). The daemon does no useful work
    # within a test's lifetime (it jitter-sleeps 0-60 s then awaits _SCHEDULER_STOP),
    # but its asyncio.Task + Event bind to the session event loop and LEAK across
    # mutmut's multiple in-process pytest.main() runs (stats -> clean-test ->
    # forced-fail), surfacing as "ValueError: The future belongs to a different
    # loop" at async teardown of the 2nd run — the sole blocker for the mutmut CI
    # job. No test references it (grep-verified); it was the only background daemon
    # NOT already gated out of testing.
    if settings.environment != "testing":
        app.state.background_tasks.add(
            asyncio.create_task(_periodic_scheduler_loop(), name="periodic_scheduler")
        )

    # Boot components from DI container
    if settings.environment != "testing":
        outbox_worker = await app.state.dishka_container.get(OutboxWorker)
        outbox_task = asyncio.create_task(
            outbox_worker.run_forever(), name="outbox_worker"
        )
        app.state.background_tasks.add(outbox_task)

        nats_broker = await app.state.dishka_container.get(NatsTaskBroker)
        if nats_broker.is_connected:
            app.state.background_tasks.add(
                asyncio.create_task(nats_broker.run_worker(), name="nats_worker")
            )
    else:
        _logger.info(
            "Background workers (Outbox, NATS) disabled in testing environment"
        )

    if settings.partition_management_enabled:
        try:
            await ensure_partitions_exist()
            # RZ-W19-05: Avoid starting the background scheduler in testing.
            # Running it concurrently with tests executes DDL queries that interfere with
            # the query budget checks of HTTP requests.
            if settings.environment != "testing":
                app.state.partition_stopper = (
                    await start_partition_management_scheduler(
                        settings.partition_management_interval_seconds
                    )
                )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — partition init failure is non-fatal (reviewed TD-27-04)
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
        except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — cleanup task failure must not crash scheduler (reviewed TD-27-04)
            task_name = type(task).__name__
            _logger.exception("Cleanup failed for %s", task_name)
            # MOD-W10-08: Increment Prometheus counter for Grafana alerting.
            from app.core.metrics import record_background_task_error

            record_background_task_error(task_name)

    async def _sleep_or_stop(seconds: float) -> bool:
        """Sleep for *seconds* or return True immediately if stop is signalled."""
        try:
            await asyncio.wait_for(_SCHEDULER_STOP.wait(), timeout=seconds)
            return True  # stop requested
        except TimeoutError:
            return False  # normal timeout — continue

    # Jitter: spread first execution across 0–60 s
    jitter = random.uniform(0, 60)  # nosec B311  # noqa: S311
    _logger.debug("Periodic scheduler: initial jitter %.1f s", jitter)
    if await _sleep_or_stop(jitter):
        return

    # PERF-NEW-005 (audit 2026-03-19): Track both Day of Year and Hour to
    # prevent duplicate execution or missed hours during Daylight Saving Time (DST)
    # transitions when the same hour can occur twice or be skipped.
    _last_ran: tuple[int, int] = (-1, -1)
    import datetime

    while not _SCHEDULER_STOP.is_set():
        now_utc = datetime.datetime.now(datetime.UTC)
        current_key = (now_utc.timetuple().tm_yday, now_utc.hour)

        # Deduplication: skip if already ran this hour (clock drift / fast restart guard)
        if current_key != _last_ran:
            tasks = [
                cleanup_stories_task,
                cleanup_password_reset_tokens_task,
                cleanup_email_change_tokens_task,
                cleanup_mfa_challenges_task,
            ]

            if now_utc.hour % 6 == 0:
                tasks.append(cleanup_sessions_task)
            if now_utc.hour == 2:
                tasks.extend(
                    [
                        cleanup_notifications_task,
                        cleanup_dead_letter_jobs_task,
                        cleanup_privacy_artifacts_task,
                        manage_partitions_task,
                    ]
                )

            # PERF-06 (audit 2026-03-11): asyncio.TaskGroup provides structured
            # concurrency with proper error isolation — each task failure is
            # collected independently and does not cancel sibling tasks before
            # they start (unlike asyncio.gather which short-circuits on the
            # first unhandled exception when return_exceptions=False).
            # _kick() already absorbs all exceptions internally, so TaskGroup
            # will never see a propagating exception here; this change is
            # forward-safe for any future _kick() refactor that drops the
            # bare-except.  Python 3.11+ required (available since py3.12 env).
            async with asyncio.TaskGroup() as tg:
                for task in tasks:
                    tg.create_task(_kick(task))
            _last_ran = current_key

        if await _sleep_or_stop(3600):
            break


async def _prewarm_jwt_public_key_cache() -> None:
    """Pre-derive RSA public keys at startup so the first real requests don't block.

    TD-W8-02: Without pre-warming, the first batch of JWT decode calls all miss
    the _public_key_cache and block on threading.Lock while deriving the public key
    from the RSA private PEM (1-50ms). This runs once at startup in a thread executor
    to avoid blocking the event loop.
    """
    import asyncio

    from app.auth.security import _auth_executor, _get_cached_public_key_pem

    registry = settings.jwt_signing_key_registry
    for kid, secret in registry.items():
        if "PRIVATE KEY" in secret:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    _auth_executor,
                    _get_cached_public_key_pem,
                    kid,
                    secret,
                )
            except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — pre-warm failure is non-fatal (reviewed TD-27-04)
                # Pre-warm failure is non-fatal — cache fills on first real request
                _logger.warning("JWT key pre-warm failed for kid=%r: %s", kid, exc)


def _reset_closed_dishka_container(app: FastAPI) -> None:
    """Replace a closed APP-scoped container before a lifespan restart."""

    # A TestClient, LifespanManager, or ASGI server may start this application
    # again after the previous lifespan closed the APP-scoped container.  The
    # Dishka middleware reads the container from ``app.state`` for each request,
    # so replacing the closed root here keeps every ASGI driver restart-safe.
    try:
        container_was_closed = app.state._dishka_container_closed
    except AttributeError:
        # A freshly-created FastAPI app has not completed a prior lifespan.
        # Initialize its explicit lifecycle marker below without recreating a
        # healthy container.
        pass
    else:
        # Treat an unknown marker as closed: reusing a possibly closed root is
        # unsafe, while recreating an open root is still bounded and explicit.
        if container_was_closed is not False:
            from app.core.di_provider import create_dishka_container

            app.state.dishka_container = create_dishka_container()
    # TestClient, LifespanManager, and production ASGI servers all drive this
    # context.  Keep the container lifecycle observable so a subsequent
    # in-process test lifespan can replace the closed Dishka container instead
    # of reusing it after shutdown.
    app.state._dishka_container_closed = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Granular startup and shutdown orchestration (TD-004 decomposition)."""
    # RZ-33-14: Clear the stop event so the scheduler works after hot-reload.
    _SCHEDULER_STOP.clear()
    _reset_closed_dishka_container(app)

    # 1. Bootstrapping
    await _startup_database_and_di(app)
    await _startup_websocket_and_flags(app)

    # 2. Validation
    await _validate_di_container(app)
    await _verify_database_readiness()
    await _handle_schema_and_extensions()

    # 3. Business Logic Registration
    # TD-NEW-003 (audit 2026-03-19): Guard against duplicate listener registration.
    # During hot-reload (uvicorn --reload) or test suites where lifespan is exercised
    # multiple times in the same process, calling register_event_listeners() more than
    # once accumulates duplicate handlers — events fire N times for N restarts.
    # LOW-W19: Use `global` statement instead of globals()[...] assignment, which
    # is an anti-pattern that bypasses the module's normal name-binding and makes
    # the mutation invisible to static analysers and type checkers.
    global _LISTENERS_REGISTERED
    if not _LISTENERS_REGISTERED:
        await register_event_listeners()
        from app.services.event_handlers import configure_event_handlers

        configure_event_handlers()
        _LISTENERS_REGISTERED = True
    else:
        import logging as _llog

        _llog.getLogger(__name__).debug(
            "TD-NEW-003: Skipping event listener registration (already registered in this process)."
        )

    # 4. Workers & Data Warming
    await _startup_background_workers(app)

    from app.core.ratelimit import start_memory_cleanup_task

    start_memory_cleanup_task()

    if settings.environment != "testing":
        try:
            await warm_cache()
        except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — warm cache failure is non-fatal (reviewed TD-27-04)
            _logger.warning("Warm cache failed: %s", exc)

    try:
        await _prewarm_jwt_public_key_cache()
    except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — JWT pre-warm failure is non-fatal (reviewed TD-27-04)
        _logger.warning("JWT public key pre-warm failed: %s", exc)

    try:
        yield
    finally:
        await _shutdown_subsystems(app)


async def _shutdown_subsystems(app: FastAPI) -> None:
    """Graceful termination of all fanned-out components and pools."""
    from app.api.health import set_shutdown_flag
    from app.api.ws.presence import stop_presence_pubsub
    from app.auth.security import close_hibp_client
    from app.core.feature_flags import feature_flags
    from app.core.ratelimit import stop_memory_cleanup_task
    from app.services.geolocation import shutdown_geolocation_service

    # MOD-06 (audit 2026-03-15 Wave 7): Signal K8s readiness probe to return
    # 503 so the LB drains in-flight connections before we start tearing down.
    # Must be first so the probe flips before any pool is closed.
    set_shutdown_flag()

    # TD-3: Signal the periodic scheduler to stop before cancelling tasks,
    # so it exits its current sleep immediately via asyncio.Event.
    _SCHEDULER_STOP.set()

    # Cancel background noise first
    _bg_tasks = list(getattr(app.state, "background_tasks", set()))
    for t in _bg_tasks:
        t.cancel()
    if _bg_tasks:
        await asyncio.gather(*_bg_tasks, return_exceptions=True)

    # Orderly pool and client teardown.  Set the marker before closing so it is
    # still reliable if a provider finalizer raises during shutdown.
    app.state._state.update(_DISHKA_CONTAINER_CLOSED_STATE)
    await app.state.dishka_container.close()
    await stop_presence_pubsub()
    await notification_queue.shutdown_notification_queue()
    webpush.cleanup()
    await shutdown_cache()

    partition_stopper = getattr(app.state, "partition_stopper", None)
    if partition_stopper is not None:
        await partition_stopper()

    await feature_flags.close()
    await stop_memory_cleanup_task()

    from app.core.spicedb import close_global_spicedb_channel

    await close_global_spicedb_channel()

    shutdown_observability()
    shutdown_geolocation_service()
    await close_hibp_client()

    from app.core.security.spiffe import svid_manager

    svid_manager.stop()
