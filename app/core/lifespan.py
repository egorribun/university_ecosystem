import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine, init_database, wait_db
from app.core.events import register_event_listeners
from app.core.nats_broker import broker as nats_broker
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

# TD-06 (audit 2026-03-04): pydantic-settings marks Settings immutable via
# model_config = ConfigDict(frozen=True). Using object.__setattr__ to bypass
# this constraint is undefined behaviour — it violates the class invariant and
# breaks type-safety. Runtime overrides are tracked here instead.
# Callers: replace `settings.semantic_search_enabled` reads with
# `_RUNTIME_FLAGS.get('semantic_search_enabled', settings.semantic_search_enabled)`
# where the value may change after startup.
_RUNTIME_FLAGS: dict[str, bool] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Configure database adapters (remove global side effects)
    from app.core.database import configure_database

    configure_database()
    init_database()

    # TD-5: Warn at startup when SPOTIFY_TOKEN_SECRET is not independently configured.
    # Falling back to SHA256(SECRET_KEY) couples Spotify token decryption to JWT signing;
    # rotating SECRET_KEY will silently invalidate all stored Spotify tokens.
    if not settings.spotify_token_secret:
        _logger.warning(
            "SPOTIFY_TOKEN_SECRET is not set — Spotify token encryption falls back to "
            "a key derived from SECRET_KEY.  Rotating SECRET_KEY will invalidate all "
            "stored Spotify OAuth tokens.  Set SPOTIFY_TOKEN_SECRET to an independent "
            "Fernet key to decouple the two secrets."
        )

    # (TD-4) Re-create a fresh Dishka container per lifespan start.
    # This ensures that Pytest test cycles (which run multiple lifespan contexts)
    # always have an open container, not a closed one from a previous test.
    from app.core.di_provider import create_dishka_container

    if hasattr(app.state, "dishka_container"):
        app.state.dishka_container = create_dishka_container()

    import app.api.websocket as _ws_module
    from app.api.websocket import (
        ConnectionManager,
        start_presence_pubsub,
        stop_presence_pubsub,
    )
    from app.core.feature_flags import feature_flags
    from app.core.rate_limit import (
        start_memory_cleanup_task,
        stop_memory_cleanup_task,
    )

    # Initialise the WebSocket ConnectionManager and expose it via app.state so
    # that route handlers can inject it through get_connection_manager() and
    # tests can swap it for a mock via app.state.connection_manager.
    _cm = ConnectionManager()
    app.state.connection_manager = _cm
    _ws_module.manager = _cm  # Keep module-level alias for pubsub / background tasks

    # MOD-3: NATS Task Broker initialization
    _nats_success = False
    try:
        # We use a 5-second timeout to ensure CI/deployments don't hang if NATS is down.
        await asyncio.wait_for(nats_broker.connect(), timeout=5.0)
        _nats_success = True
    except (TimeoutError, Exception) as exc:
        _logger.warning("NATS connection failed: %s. Continuing in degraded mode.", exc)

    worker_task = None
    if _nats_success:
        # In development or if explicitly allowed, we can run the worker in-process.
        # In production, a separate worker process would call broker.run_worker().
        worker_task = asyncio.create_task(nats_broker.run_worker(), name="nats_worker")

    await feature_flags.initialize()
    await start_presence_pubsub()
    try:
        # Limit total wait time for database to 5 seconds to pass CI health checks.
        await asyncio.wait_for(wait_db(max_attempts=10, delay=0.5), timeout=5.0)
    except (TimeoutError, Exception) as exc:
        if settings.environment not in {"development", "local", "testing"}:
            raise
        _logger.warning(
            "Database unavailable: %s. Continuing startup (be prepared for errors).",
            exc,
        )

    # MOD-4 (audit 2026-02-26): Fail fast if the DB schema is not at the
    # migration head.  Without this check a deployment that skips ``alembic
    # upgrade head`` silently serves requests against a mismatched schema,
    # causing cryptic SQLAlchemy errors hours later.
    #
    # Skipped for non-Postgres dialects (e.g. SQLite used in tests) because
    # the alembic_version table may not exist in ephemeral test databases.
    if settings.environment not in {"testing", "test"}:
        try:
            from alembic.config import Config as AlembicConfig
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            _alembic_cfg = AlembicConfig("alembic.ini")
            _scripts = ScriptDirectory.from_config(_alembic_cfg)
            _head = _scripts.get_current_head()

            async with engine.connect() as _conn:
                _dialect = _conn.dialect.name
                if _dialect == "postgresql":
                    _ctx = await _conn.run_sync(
                        lambda sync_conn: MigrationContext.configure(sync_conn)
                    )
                    _current = _ctx.get_current_revision()
                    if _current != _head:
                        raise RuntimeError(
                            f"DB schema mismatch — current={_current!r}, "
                            f"head={_head!r}. Run 'alembic upgrade head' before "
                            "starting the application."
                        )
                    _logger.info("DB schema check passed: revision=%s", _current)
        except ImportError:
            _logger.warning("alembic not importable — skipping migration head check")
        except Exception as exc:
            if settings.environment not in {"development", "local", "testing"}:
                raise
            _logger.warning("Migration check failed (likely DB unavailable): %s", exc)

    await register_event_listeners()

    # Configure domain event handlers
    from app.services.event_handlers import configure_event_handlers

    configure_event_handlers()

    if settings.auto_create_schema:
        from sqlalchemy import text

        try:
            async with engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    try:
                        await conn.execute(
                            text("CREATE EXTENSION IF NOT EXISTS vector")
                        )
                    except Exception as e:
                        _logger.warning(
                            f"Could not create 'vector' extension: {e}. "
                            "Semantic search will be disabled."
                        )
                        # Patch metadata to avoid using Vector type if extension is missing
                        from pgvector.sqlalchemy import Vector
                        from sqlalchemy import Text

                        for table in Base.metadata.tables.values():
                            for column in table.columns:
                                # Check for direct Vector or Variant containing Vector
                                is_vector = isinstance(column.type, Vector)
                                is_variant_vector = False

                                if hasattr(column.type, "_variant_mapping"):
                                    # If Variant, check if PG variant is Vector
                                    pg_utils = getattr(
                                        column.type, "_variant_mapping", {}
                                    )
                                    pg_variant = pg_utils.get("postgresql")
                                    if pg_variant and isinstance(pg_variant, Vector):
                                        is_variant_vector = True

                                if is_vector:
                                    column.type = Text()
                                elif is_variant_vector:
                                    # Use base type as fallback
                                    column.type = getattr(
                                        column.type, "base_type", Text()
                                    )

                        # TD-06 (audit 2026-03-04): do NOT use object.__setattr__
                        # on the pydantic-settings Settings instance — it is
                        # intentionally frozen. Store the runtime override here so
                        # callers that check semantic_search_enabled can use
                        # _RUNTIME_FLAGS.get('semantic_search_enabled', ...)
                        _RUNTIME_FLAGS["semantic_search_enabled"] = False
                        _logger.info(
                            "Runtime flag 'semantic_search_enabled' set to False "
                            "(pgvector extension unavailable)"
                        )
                else:
                    # Non-PostgreSQL dialect (likely SQLite for tests)
                    # Patch out search_vector Computed columns that use to_tsvector
                    for table in Base.metadata.tables.values():
                        for column in table.columns:
                            if column.computed is not None:
                                sql_text = str(column.computed.sqltext)
                                if "to_tsvector" in sql_text:
                                    _logger.info(
                                        "Patching out computed column %s.%s for dialect %s",
                                        table.name,
                                        column.name,
                                        conn.dialect.name,
                                    )
                                    column.computed = None

                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(
                        bind=sync_conn, checkfirst=True
                    )
                )
        except Exception as exc:
            if settings.environment not in {"development", "local", "testing"}:
                raise
            _logger.warning(
                "Auto-schema creation failed (likely DB unavailable): %s", exc
            )

    await setup_periodic_cleanups()

    async def _periodic_scheduler() -> None:
        """Lightweight background loop for periodic tasks. (MOD-3)"""
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

        # Initial delay to let the app warm up
        await asyncio.sleep(60)

        # TD-4: Each task is wrapped individually so a failure in one cleanup
        # never prevents subsequent cleanups from running.

        async def _kick(task: Any) -> None:
            try:
                await task.kick()
            except Exception:
                _logger.exception(
                    "Periodic cleanup failed", extra={"task": task.__class__.__name__}
                )

        while True:
            import datetime

            cur_hour = datetime.datetime.now(datetime.UTC).hour

            # Every 1 hour: most cleanups
            await _kick(cleanup_stories_task)
            await _kick(cleanup_password_reset_tokens_task)
            await _kick(cleanup_email_change_tokens_task)
            await _kick(cleanup_mfa_challenges_task)

            # Every 6 hours: sessions
            if cur_hour % 6 == 0:
                await _kick(cleanup_sessions_task)

            # Every 24 hours: heavy/daily tasks (at ~2 AM or similar)
            if cur_hour == 2:
                await _kick(cleanup_notifications_task)
                await _kick(cleanup_dead_letter_jobs_task)
                await _kick(cleanup_privacy_artifacts_task)
                await _kick(manage_partitions_task)

            # Sleep for 1 hour between checks
            await asyncio.sleep(3600)

    # Store a reference to prevent background tasks from being garbage collected
    if not hasattr(app.state, "background_tasks"):
        app.state.background_tasks = set()

    app.state.background_tasks.add(
        asyncio.create_task(_periodic_scheduler(), name="periodic_scheduler")
    )

    stop_partitions = None
    if settings.partition_management_enabled:
        try:
            _logger.info(
                "Synchronously warming up PostgreSQL partitions "
                "to prevent cold start failures..."
            )
            await ensure_partitions_exist()
            stop_partitions = await start_partition_management_scheduler(
                settings.partition_management_interval_seconds
            )
        except Exception as exc:
            if settings.environment not in {"development", "local", "testing"}:
                raise
            _logger.warning("Partition management initialization failed: %s", exc)

    # Start OutboxWorker
    outbox_worker = OutboxWorker()
    outbox_task = asyncio.create_task(outbox_worker.run_forever(), name="outbox_worker")

    def _on_outbox_done(task: asyncio.Task[Any]) -> None:
        """Log unexpected OutboxWorker exits so they are never silently swallowed."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _logger.error("OutboxWorker exited unexpectedly: %s", exc, exc_info=exc)

    outbox_task.add_done_callback(_on_outbox_done)

    # Start in-memory rate limit cleanup (for fallback mode)
    start_memory_cleanup_task()

    try:
        await warm_cache()
    except Exception as exc:
        if settings.environment not in {"development", "local", "testing"}:
            raise
        _logger.warning("Cache warmup failed: %s", exc)
    try:
        yield
    finally:
        # RZ-05 (audit 2026-03-04): Cancel all tracked background tasks before
        # tearing down the DI container. Without this, _periodic_scheduler and
        # other tasks survive across lifespan cycles in integration tests
        # (creating multiple concurrent schedulers), and are silently abandoned
        # on production SIGTERM → SIGKILL without running their finally blocks.
        _bg_tasks = list(getattr(app.state, "background_tasks", set()))
        for _bg_task in _bg_tasks:
            _bg_task.cancel()
        if _bg_tasks:
            await asyncio.gather(*_bg_tasks, return_exceptions=True)
        if hasattr(app.state, "background_tasks"):
            app.state.background_tasks.clear()

        await app.state.dishka_container.close()
        await stop_presence_pubsub()
        await notification_queue.shutdown_notification_queue()
        webpush.cleanup()
        await shutdown_cache()
        if settings.partition_management_enabled and stop_partitions:
            await stop_partitions()

        await outbox_worker.stop()
        await outbox_task

        # Shutdown NATS broker
        if worker_task:
            worker_task.cancel()
        await nats_broker.close()

        await feature_flags.shutdown()
        await stop_memory_cleanup_task()
        shutdown_observability()

        from app.services.geolocation import shutdown_geolocation_service

        shutdown_geolocation_service()

        # RZ-4: Close the shared HIBP HTTP client (connection pooling cleanup).
        from app.auth.security import close_hibp_client

        await close_hibp_client()
