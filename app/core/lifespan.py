import asyncio
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure database adapters (remove global side effects)
    from app.core.database import configure_database

    configure_database()

    from dishka.integrations.fastapi import setup_dishka

    from app.core.di_provider import create_dishka_container

    # (TD-4) Guard: setup_dishka adds middleware, which can only be done once.
    # In tests, lifespan may be called multiple times on the same app instance.
    if not hasattr(app.state, "dishka_container"):
        setup_dishka(create_dishka_container(), app)

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
    await nats_broker.connect()
    # In development or if explicitly allowed, we can run the worker in-process.
    # In production, a separate worker process would call broker.run_worker().
    worker_task = asyncio.create_task(nats_broker.run_worker(), name="nats_worker")

    await feature_flags.initialize()
    await start_presence_pubsub()
    await wait_db(max_attempts=10, delay=0.5)

    # Register domain event persistence listeners
    register_event_listeners()

    # Configure domain event handlers
    from app.services.event_handlers import configure_event_handlers

    configure_event_handlers()

    if settings.auto_create_schema:
        import logging

        from sqlalchemy import text

        logger = logging.getLogger(__name__)

        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                except Exception as e:
                    logger.warning(
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
                                pg_utils = column.type._variant_mapping
                                pg_variant = pg_utils.get("postgresql")
                                if pg_variant and isinstance(pg_variant, Vector):
                                    is_variant_vector = True

                            if is_vector:
                                column.type = Text()
                            elif is_variant_vector:
                                # Use base type as fallback
                                column.type = getattr(column.type, "base_type", Text())

                    # Disable semantic search in settings
                    try:
                        # Attempt to disable semantic search since extension is missing
                        object.__setattr__(settings, "semantic_search_enabled", False)
                    except Exception:
                        logger.error(
                            "Failed to disable semantic_search_enabled setting"
                        )
            else:
                # Non-PostgreSQL dialect (likely SQLite for tests)
                # Patch out search_vector Computed columns that use to_tsvector
                for table in Base.metadata.tables.values():
                    for column in table.columns:
                        if column.computed is not None:
                            sql_text = str(column.computed.sqltext)
                            if "to_tsvector" in sql_text:
                                logger.info(
                                    f"Patching out computed column {table.name}.{column.name} "
                                    f"for dialect {conn.dialect.name}"
                                )
                                column.computed = None

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    bind=sync_conn, checkfirst=True
                )
            )

    await setup_periodic_cleanups()

    async def _periodic_scheduler():
        """Lightweight background loop for periodic tasks. (MOD-3)"""
        from app.tasks.cleanups import (
            cleanup_notifications_task,
            cleanup_dead_letter_jobs_task,
            cleanup_sessions_task,
            cleanup_stories_task,
            cleanup_password_reset_tokens_task,
            cleanup_email_change_tokens_task,
            cleanup_mfa_challenges_task,
            cleanup_privacy_artifacts_task,
            manage_partitions_task,
        )

        # Initial delay to let the app warm up
        await asyncio.sleep(60)

        while True:
            try:
                # Every 1 hour: most cleanups
                await cleanup_stories_task.kick()
                await cleanup_password_reset_tokens_task.kick()
                await cleanup_email_change_tokens_task.kick()
                await cleanup_mfa_challenges_task.kick()

                # Every 6 hours: sessions
                cur_hour = datetime.now(UTC).hour
                if cur_hour % 6 == 0:
                    await cleanup_sessions_task.kick()

                # Every 24 hours: heavy/daily tasks (at ~2 AM or similar)
                if cur_hour == 2:
                    await cleanup_notifications_task.kick()
                    await cleanup_dead_letter_jobs_task.kick()
                    await cleanup_privacy_artifacts_task.kick()
                    await manage_partitions_task.kick()

            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Periodic scheduler error: {e}")

            # Sleep for 1 hour between checks
            await asyncio.sleep(3600)

    scheduler_task = asyncio.create_task(_periodic_scheduler(), name="periodic_scheduler")

    if settings.partition_management_enabled:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "Synchronously warming up PostgreSQL partitions to prevent cold start failures..."
        )
        await ensure_partitions_exist()
        stop_partitions = await start_partition_management_scheduler(
            settings.partition_management_interval_seconds
        )

    # Start OutboxWorker
    outbox_worker = OutboxWorker()
    outbox_task = asyncio.create_task(outbox_worker.run_forever(), name="outbox_worker")

    def _on_outbox_done(task: asyncio.Task) -> None:  # type: ignore[type-arg]
        """Log unexpected OutboxWorker exits so they are never silently swallowed."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            import logging as _logging

            _logging.getLogger(__name__).error(
                "OutboxWorker exited unexpectedly: %s", exc, exc_info=exc
            )

    outbox_task.add_done_callback(_on_outbox_done)

    # Start in-memory rate limit cleanup (for fallback mode)
    start_memory_cleanup_task()

    await warm_cache()
    try:
        yield
    finally:
        await app.state.dishka_container.close()
        await stop_presence_pubsub()
        await notification_queue.shutdown_notification_queue()
        webpush.cleanup()
        await shutdown_cache()
        if settings.partition_management_enabled:
            await stop_partitions()

        await outbox_worker.stop()
        await outbox_task

        # Shutdown NATS broker
        worker_task.cancel()
        await nats_broker.close()

        await feature_flags.shutdown()
        await stop_memory_cleanup_task()
        shutdown_observability()
