import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.core.lifespan import (
    RuntimeFeatureOverrides,
    _handle_schema_and_extensions,
    _periodic_scheduler_loop,
    _prewarm_jwt_public_key_cache,
    _shutdown_subsystems,
    _startup_background_workers,
    _startup_database_and_di,
    _startup_websocket_and_flags,
    _validate_di_container,
    _verify_database_readiness,
    lifespan,
)
from app.workers.outbox import OutboxWorker


class TestRuntimeFeatureOverrides:
    def test_resolve(self) -> None:
        overrides = RuntimeFeatureOverrides()
        # Default fallback: None in override, should return the default value passed
        assert overrides.resolve("semantic_search_enabled", default=True) is True
        assert overrides.resolve("semantic_search_enabled", default=False) is False

        # Set override
        overrides.semantic_search_enabled = True
        assert overrides.resolve("semantic_search_enabled", default=False) is True

        overrides.semantic_search_enabled = False
        assert overrides.resolve("semantic_search_enabled", default=True) is False

    def test_disable(self) -> None:
        overrides = RuntimeFeatureOverrides()
        overrides.disable("semantic_search_enabled")
        assert overrides.semantic_search_enabled is False

        with pytest.raises(AttributeError):
            overrides.disable("non_existent_flag")


@pytest.mark.asyncio
async def test_startup_database_and_di_warnings() -> None:
    app = FastAPI()
    # If environment is dev/local/testing, it should log a warning
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan._logger") as mock_logger,
        patch("app.core.lifespan.init_database") as mock_init_db,
    ):
        mock_settings.spotify_token_secret = None
        mock_settings.environment = "testing"

        await _startup_database_and_di(app)
        mock_init_db.assert_called_once()
        mock_logger.warning.assert_called_once()

    # If environment is production, it should raise RuntimeError
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.init_database") as mock_init_db,
    ):
        mock_settings.spotify_token_secret = None
        mock_settings.environment = "production"

        with pytest.raises(RuntimeError, match="SPOTIFY_TOKEN_SECRET must be set"):
            await _startup_database_and_di(app)

    # When spotify_token_secret is present, normal path
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.init_database") as mock_init_db,
    ):
        mock_settings.spotify_token_secret = "some-key"  # pragma: allowlist secret
        mock_settings.environment = "production"

        await _startup_database_and_di(app)
        mock_init_db.assert_called_once()


@pytest.mark.asyncio
async def test_startup_websocket_and_flags() -> None:
    app = FastAPI()
    with (
        patch("app.api.ws.connection_manager.ConnectionManager") as mock_cm_class,
        patch(
            "app.api.ws.presence.start_presence_pubsub", new_callable=AsyncMock
        ) as mock_pubsub,
        patch(
            "app.core.feature_flags.feature_flags.initialize", new_callable=AsyncMock
        ) as mock_flags,
    ):
        mock_cm = MagicMock()
        mock_cm_class.return_value = mock_cm

        await _startup_websocket_and_flags(app)
        assert app.state.connection_manager is mock_cm
        mock_pubsub.assert_awaited_once()
        mock_flags.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_database_readiness_testing() -> None:
    # Environment in testing/dev: should log a warning on DB failure but not raise
    with (
        patch("app.core.lifespan.wait_db", new_callable=AsyncMock) as mock_wait_db,
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan._logger") as mock_logger,
    ):
        mock_settings.environment = "testing"
        mock_wait_db.side_effect = TimeoutError("DB timeout")

        await _verify_database_readiness()
        mock_logger.warning.assert_called_once()

    # Environment in production: should raise on DB failure
    with (
        patch("app.core.lifespan.wait_db", new_callable=AsyncMock) as mock_wait_db,
        patch("app.core.lifespan.settings") as mock_settings,
    ):
        mock_settings.environment = "production"
        mock_wait_db.side_effect = TimeoutError("DB timeout")

        with pytest.raises(TimeoutError):
            await _verify_database_readiness()


@pytest.mark.asyncio
async def test_verify_database_readiness_alembic_head_check() -> None:
    # Head check is run when env is NOT in testing/test
    with (
        patch("app.core.lifespan.wait_db", new_callable=AsyncMock),
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
        patch("app.core.lifespan._logger") as mock_logger,
        patch("alembic.config.Config"),
        patch("alembic.script.ScriptDirectory.from_config") as mock_script_dir,
    ):
        mock_settings.environment = "production"

        # Setup Alembic mocks
        mock_scripts = MagicMock()
        mock_scripts.get_current_head.return_value = "head_rev"
        mock_script_dir.return_value = mock_scripts

        # Setup connection dialect/execution context mocks
        mock_ctx = MagicMock()
        mock_ctx.get_current_revision.return_value = "mismatched_rev"

        mock_conn = AsyncMock()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_conn.dialect = mock_dialect
        mock_conn.run_sync = AsyncMock(return_value=mock_ctx)

        mock_connect_context = MagicMock()
        mock_connect_context.__aenter__.return_value = mock_conn
        mock_engine.connect.return_value = mock_connect_context

        # DB schema mismatch should raise RuntimeError in production
        with pytest.raises(RuntimeError, match="DB schema mismatch"):
            await _verify_database_readiness()

        # In dev environment, it should warn instead of raising
        mock_settings.environment = "development"
        await _verify_database_readiness()
        mock_logger.warning.assert_called_once()

    # Success case: current == head
    with (
        patch("app.core.lifespan.wait_db", new_callable=AsyncMock),
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
        patch("alembic.config.Config"),
        patch("alembic.script.ScriptDirectory.from_config") as mock_script_dir,
    ):
        mock_settings.environment = "production"

        mock_scripts = MagicMock()
        mock_scripts.get_current_head.return_value = "head_rev"
        mock_script_dir.return_value = mock_scripts

        mock_ctx = MagicMock()
        mock_ctx.get_current_revision.return_value = "head_rev"

        mock_conn = AsyncMock()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_conn.dialect = mock_dialect
        mock_conn.run_sync = AsyncMock(return_value=mock_ctx)

        mock_connect_context = MagicMock()
        mock_connect_context.__aenter__.return_value = mock_conn
        mock_engine.connect.return_value = mock_connect_context

        # Should not raise any error
        await _verify_database_readiness()

    # If dialect is sqlite (non-postgresql), Alembic head check is skipped
    with (
        patch("app.core.lifespan.wait_db", new_callable=AsyncMock),
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
    ):
        mock_settings.environment = "production"

        mock_conn = AsyncMock()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        mock_conn.dialect = mock_dialect

        mock_connect_context = MagicMock()
        mock_connect_context.__aenter__.return_value = mock_conn
        mock_engine.connect.return_value = mock_connect_context

        await _verify_database_readiness()


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_disabled() -> None:
    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.auto_create_schema = False
        # If disabled, function should return early without doing anything
        await _handle_schema_and_extensions()


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_pgvector_fail() -> None:
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
        patch("app.core.lifespan.runtime_flags") as mock_flags,
    ):
        mock_settings.auto_create_schema = True
        mock_settings.environment = "testing"

        mock_conn = AsyncMock()
        mock_conn.dialect.name = "postgresql"
        # Executing extension creation raises OSError/ConnectionError
        mock_conn.execute.side_effect = ConnectionError("extension fail")

        mock_begin_context = MagicMock()
        mock_begin_context.__aenter__.return_value = mock_conn
        mock_engine.begin.return_value = mock_begin_context

        await _handle_schema_and_extensions()
        mock_flags.disable.assert_called_once_with("semantic_search_enabled")


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_sqlite_computed_patch() -> None:
    # SQLite dialect should remove computed tsvector columns
    mock_computed = MagicMock()
    mock_computed.sqltext = "to_tsvector('english')"

    mock_column = MagicMock()
    mock_column.computed = mock_computed

    mock_table = MagicMock()
    mock_table.columns = [mock_column]

    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
        patch("app.core.lifespan.Base") as mock_base,
    ):
        mock_settings.auto_create_schema = True
        mock_settings.environment = "testing"

        mock_conn = AsyncMock()
        mock_conn.dialect.name = "sqlite"

        mock_begin_context = MagicMock()
        mock_begin_context.__aenter__.return_value = mock_conn
        mock_engine.begin.return_value = mock_begin_context

        mock_base.metadata.tables.values.return_value = [mock_table]

        await _handle_schema_and_extensions()

        # Computed attribute should be cleared
        assert mock_column.computed is None
        mock_conn.run_sync.assert_called_once_with(mock_base.metadata.create_all)


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_auto_schema_fail() -> None:
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.engine") as mock_engine,
        patch("app.core.lifespan._logger") as mock_logger,
    ):
        mock_settings.auto_create_schema = True
        mock_settings.environment = "testing"

        mock_engine.begin.side_effect = SQLAlchemyError("DB error")

        # In testing environment: warning logged, no error raised
        await _handle_schema_and_extensions()
        mock_logger.warning.assert_called_once()

        # In production environment: error raised
        mock_settings.environment = "production"
        with pytest.raises(SQLAlchemyError):
            await _handle_schema_and_extensions()


@pytest.mark.asyncio
async def test_validate_di_container() -> None:
    app = FastAPI()
    mock_container = AsyncMock()
    app.state.dishka_container = mock_container

    # 1. Successful validation
    mock_container.get.side_effect = lambda svc_type: MagicMock()
    with patch("app.core.lifespan._logger") as mock_logger:
        await _validate_di_container(app)
        mock_logger.info.assert_called_once()

    # 2. Failed validation (raises in production, warns in testing)
    mock_container.get.side_effect = Exception("Resolution failed")

    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan._logger") as mock_logger,
    ):
        mock_settings.environment = "testing"
        await _validate_di_container(app)
        mock_logger.warning.assert_called_once()

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.environment = "production"
        with pytest.raises(RuntimeError, match="DI container smoke-test FAILED"):
            await _validate_di_container(app)


@pytest.mark.asyncio
async def test_prewarm_jwt_public_key_cache() -> None:
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock()

    # Ensure it iterates over keys and calls executor
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("asyncio.get_running_loop", return_value=mock_loop),
        patch("app.auth.security._auth_executor") as mock_executor,
        patch("app.auth.security._get_cached_public_key_pem") as mock_get_pem,
    ):
        mock_settings.jwt_signing_key_registry = {
            "kid1": "PRIVATE KEY data",
            "kid2": "some regular key data",  # won't trigger since it lacks "PRIVATE KEY"
        }

        await _prewarm_jwt_public_key_cache()
        mock_loop.run_in_executor.assert_called_once_with(
            mock_executor, mock_get_pem, "kid1", "PRIVATE KEY data"
        )

    # JWT pre-warm failure logs a warning
    mock_loop.run_in_executor.side_effect = Exception("executor crash")
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("asyncio.get_running_loop", return_value=mock_loop),
        patch("app.core.lifespan._logger") as mock_logger,
        patch("app.auth.security._auth_executor") as mock_executor,
        patch("app.auth.security._get_cached_public_key_pem") as mock_get_pem,
    ):
        mock_settings.jwt_signing_key_registry = {"kid1": "PRIVATE KEY data"}
        await _prewarm_jwt_public_key_cache()
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_periodic_scheduler_loop_crashes() -> None:
    # Test that a failing cleanup task logs exception and records metric
    mock_task = MagicMock()
    mock_task.kick = AsyncMock(side_effect=Exception("cleanup crash"))

    with (
        patch("app.core.lifespan._SCHEDULER_STOP") as mock_stop,
        patch("app.core.lifespan._logger") as mock_logger,
        patch("app.core.metrics.record_background_task_error") as mock_metric,
        patch("datetime.datetime") as mock_datetime,
        patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for,
    ):
        # Stop scheduler immediately on the first check to prevent endless loop
        mock_stop.is_set.side_effect = [False, True]

        # Mock datetime to always return the same hour (skip run-once check)
        mock_now = datetime.datetime(2026, 7, 4, 2, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = mock_now

        # Mock wait_for:
        # First call (jitter sleep) raises TimeoutError (normal delay done)
        # Second call (periodic sleep) returns True (signals stop)
        mock_wait_for.side_effect = [TimeoutError(), True]

        with (
            patch("app.tasks.cleanups.cleanup_stories_task", mock_task),
            patch("app.core.lifespan.random.uniform", return_value=0.0),
        ):  # avoid jitter delay
            await _periodic_scheduler_loop()

        mock_logger.exception.assert_called_once()
        mock_metric.assert_called_once_with(type(mock_task).__name__)


@pytest.mark.asyncio
async def test_periodic_scheduler_loop_jitter_stop() -> None:
    # Initial sleep_or_stop returns True (signals early stop)
    with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for:
        mock_wait_for.return_value = True  # stop requested
        with patch("app.core.lifespan.random.uniform", return_value=0.0):
            await _periodic_scheduler_loop()


@pytest.mark.asyncio
async def test_periodic_scheduler_loop_hours() -> None:
    # Test cleanup task branch additions for hour 6, hour 2, and normal hour 3
    mock_task = MagicMock()
    mock_task.kick = AsyncMock()

    # 1. Test hour 6
    with (
        patch("app.core.lifespan._SCHEDULER_STOP") as mock_stop,
        patch("datetime.datetime") as mock_datetime,
        patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for,
    ):
        mock_stop.is_set.side_effect = [False, True]
        mock_now = datetime.datetime(2026, 7, 4, 6, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = mock_now
        mock_wait_for.side_effect = [TimeoutError(), True]

        with (
            patch("app.tasks.cleanups.cleanup_stories_task", mock_task),
            patch("app.tasks.cleanups.cleanup_sessions_task", mock_task),
            patch("app.core.lifespan.random.uniform", return_value=0.0),
        ):
            await _periodic_scheduler_loop()

    # 2. Test already ran this hour (skip branch)
    with (
        patch("app.core.lifespan._SCHEDULER_STOP") as mock_stop,
        patch("datetime.datetime") as mock_datetime,
        patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for,
    ):
        # Run loop twice: first time it runs tasks, second time it skips because current_key == _last_ran
        mock_stop.is_set.side_effect = [False, False, True]
        mock_now = datetime.datetime(2026, 7, 4, 2, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = mock_now
        mock_wait_for.side_effect = [TimeoutError(), TimeoutError(), True]

        with (
            patch("app.tasks.cleanups.cleanup_stories_task", mock_task),
            patch("app.tasks.cleanups.cleanup_sessions_task", mock_task),
            patch("app.tasks.cleanups.cleanup_notifications_task", mock_task),
            patch("app.core.lifespan.random.uniform", return_value=0.0),
        ):
            await _periodic_scheduler_loop()

    # 3. Test normal hour 3 (neither % 6 == 0 nor == 2)
    with (
        patch("app.core.lifespan._SCHEDULER_STOP") as mock_stop,
        patch("datetime.datetime") as mock_datetime,
        patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for,
    ):
        mock_stop.is_set.side_effect = [False, True]
        mock_now = datetime.datetime(2026, 7, 4, 3, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = mock_now
        mock_wait_for.side_effect = [TimeoutError(), True]

        with (
            patch("app.tasks.cleanups.cleanup_stories_task", mock_task),
            patch("app.core.lifespan.random.uniform", return_value=0.0),
        ):
            await _periodic_scheduler_loop()


@pytest.mark.asyncio
async def test_startup_background_workers_production() -> None:
    app = FastAPI()
    # Do not set app.state.background_tasks to cover hasattr check and creation branch
    mock_container = AsyncMock()
    app.state.dishka_container = mock_container

    # Mock OutboxWorker and NatsTaskBroker as AsyncMocks
    mock_outbox = AsyncMock()
    mock_nats = AsyncMock()
    mock_nats.is_connected = True

    async def container_get_mock(svc_type):
        if svc_type == OutboxWorker:
            return mock_outbox
        from app.core.nats_broker import NatsTaskBroker

        if svc_type == NatsTaskBroker:
            return mock_nats
        return MagicMock()

    mock_container.get.side_effect = container_get_mock

    # 1. Success path (NATS connected)
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.setup_periodic_cleanups", new_callable=AsyncMock),
        patch("app.core.lifespan.ensure_partitions_exist", new_callable=AsyncMock),
        patch(
            "app.core.lifespan.start_partition_management_scheduler",
            new_callable=AsyncMock,
        ) as mock_sched,
    ):
        mock_settings.environment = "production"
        mock_settings.partition_management_enabled = True
        mock_settings.partition_management_interval_seconds = 3600
        mock_sched.return_value = AsyncMock()

        await _startup_background_workers(app)

        # Background tasks set should contain: periodic_scheduler, outbox_worker, nats_worker
        task_names = {t.get_name() for t in app.state.background_tasks}
        assert "periodic_scheduler" in task_names
        assert "outbox_worker" in task_names
        assert "nats_worker" in task_names
        assert hasattr(app.state, "partition_stopper")

        # Clean up tasks
        for t in app.state.background_tasks:
            t.cancel()
        await asyncio.gather(*app.state.background_tasks, return_exceptions=True)

    # 2. Success path (NATS not connected)
    app2 = FastAPI()
    app2.state.dishka_container = mock_container
    mock_nats.is_connected = False
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.setup_periodic_cleanups", new_callable=AsyncMock),
        patch("app.core.lifespan.ensure_partitions_exist", new_callable=AsyncMock),
        patch(
            "app.core.lifespan.start_partition_management_scheduler",
            new_callable=AsyncMock,
        ) as mock_sched,
    ):
        mock_settings.environment = "production"
        mock_settings.partition_management_enabled = True
        mock_sched.return_value = AsyncMock()

        await _startup_background_workers(app2)

        task_names = {t.get_name() for t in app2.state.background_tasks}
        assert "periodic_scheduler" in task_names
        assert "outbox_worker" in task_names
        assert "nats_worker" not in task_names

        # Clean up tasks
        for t in app2.state.background_tasks:
            t.cancel()
        await asyncio.gather(*app2.state.background_tasks, return_exceptions=True)

    # 3. Fail path in partition manager
    app3 = FastAPI()
    app3.state.background_tasks = set()
    app3.state.dishka_container = mock_container
    with (
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan.setup_periodic_cleanups", new_callable=AsyncMock),
        patch(
            "app.core.lifespan.ensure_partitions_exist",
            side_effect=Exception("partitions fail"),
        ),
        patch("app.core.lifespan._logger") as mock_logger,
    ):
        mock_settings.environment = "production"
        mock_settings.partition_management_enabled = True

        await _startup_background_workers(app3)
        mock_logger.warning.assert_called_once()

        for t in app3.state.background_tasks:
            t.cancel()
        await asyncio.gather(*app3.state.background_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_lifespan_context_manager() -> None:
    app = FastAPI()

    # Mock all the initialization stages to isolate lifespan context manager
    with (
        patch(
            "app.core.lifespan._startup_database_and_di", new_callable=AsyncMock
        ) as mock_db_di,
        patch(
            "app.core.lifespan._startup_websocket_and_flags", new_callable=AsyncMock
        ) as mock_ws_flags,
        patch(
            "app.core.lifespan._validate_di_container", new_callable=AsyncMock
        ) as mock_di_val,
        patch(
            "app.core.lifespan._verify_database_readiness", new_callable=AsyncMock
        ) as mock_db_ready,
        patch(
            "app.core.lifespan._handle_schema_and_extensions", new_callable=AsyncMock
        ) as mock_schema,
        patch(
            "app.core.lifespan._startup_background_workers", new_callable=AsyncMock
        ) as mock_workers,
        patch("app.core.ratelimit.start_memory_cleanup_task") as mock_ratelimit_start,
        patch(
            "app.core.lifespan.warm_cache", new_callable=AsyncMock
        ) as mock_warm_cache,
        patch(
            "app.core.lifespan._prewarm_jwt_public_key_cache", new_callable=AsyncMock
        ) as mock_prewarm,
        patch(
            "app.core.lifespan._shutdown_subsystems", new_callable=AsyncMock
        ) as mock_shutdown,
        patch("app.core.lifespan.settings") as mock_settings,
    ):
        mock_settings.environment = "production"

        async with lifespan(app):
            # Lifespan context entered
            mock_db_di.assert_awaited_once_with(app)
            mock_ws_flags.assert_awaited_once_with(app)
            mock_di_val.assert_awaited_once_with(app)
            mock_db_ready.assert_awaited_once()
            mock_schema.assert_awaited_once()
            mock_workers.assert_awaited_once_with(app)
            mock_ratelimit_start.assert_called_once()
            mock_warm_cache.assert_awaited_once()
            mock_prewarm.assert_awaited_once()
            mock_shutdown.assert_not_called()

        # Lifespan context exited
        mock_shutdown.assert_awaited_once_with(app)

    # Lifespan hot-reload registered check bypass, warm_cache fails, prewarm fails
    with (
        patch("app.core.lifespan._startup_database_and_di", new_callable=AsyncMock),
        patch("app.core.lifespan._startup_websocket_and_flags", new_callable=AsyncMock),
        patch("app.core.lifespan._validate_di_container", new_callable=AsyncMock),
        patch("app.core.lifespan._verify_database_readiness", new_callable=AsyncMock),
        patch(
            "app.core.lifespan._handle_schema_and_extensions", new_callable=AsyncMock
        ),
        patch("app.core.lifespan._startup_background_workers", new_callable=AsyncMock),
        patch("app.core.ratelimit.start_memory_cleanup_task"),
        patch("app.core.lifespan.warm_cache", side_effect=Exception("warm fail")),
        patch(
            "app.core.lifespan._prewarm_jwt_public_key_cache",
            side_effect=Exception("prewarm fail"),
        ),
        patch("app.core.lifespan._shutdown_subsystems", new_callable=AsyncMock),
        patch("app.core.lifespan.settings") as mock_settings,
        patch("app.core.lifespan._logger") as mock_logger,
    ):
        mock_settings.environment = "production"

        # Force registration flag to be True
        import app.core.lifespan

        app.core.lifespan._LISTENERS_REGISTERED = True

        async with lifespan(app):
            pass

        # Check logs warn on failures
        assert mock_logger.warning.call_count >= 2


@pytest.mark.asyncio
async def test_shutdown_subsystems() -> None:
    app = FastAPI()
    mock_container = AsyncMock()
    app.state.dishka_container = mock_container

    # Create actual background tasks to prevent gather TypeError
    async def dummy_coro():
        await asyncio.sleep(1)

    task1 = asyncio.create_task(dummy_coro())
    task2 = asyncio.create_task(dummy_coro())
    app.state.background_tasks = {task1, task2}

    # Mock partition stopper
    mock_stopper = AsyncMock()
    app.state.partition_stopper = mock_stopper

    try:
        with (
            patch("app.api.health.set_shutdown_flag") as mock_probe,
            patch("app.core.lifespan._SCHEDULER_STOP") as mock_stop_event,
            patch(
                "app.api.ws.presence.stop_presence_pubsub", new_callable=AsyncMock
            ) as mock_presence,
            patch(
                "app.services.notification_queue.shutdown_notification_queue",
                new_callable=AsyncMock,
            ) as mock_notif,
            patch("app.core.lifespan.webpush.cleanup") as mock_webpush,
            patch(
                "app.core.lifespan.shutdown_cache", new_callable=AsyncMock
            ) as mock_cache,
            patch(
                "app.core.feature_flags.feature_flags.close", new_callable=AsyncMock
            ) as mock_flags,
            patch(
                "app.core.ratelimit.stop_memory_cleanup_task", new_callable=AsyncMock
            ) as mock_ratelimit,
            patch(
                "app.core.spicedb.close_global_spicedb_channel", new_callable=AsyncMock
            ) as mock_spicedb,
            patch("app.core.lifespan.shutdown_observability") as mock_otel,
            patch("app.services.geolocation.shutdown_geolocation_service") as mock_geo,
            patch(
                "app.auth.security.close_hibp_client", new_callable=AsyncMock
            ) as mock_hibp,
        ):
            await _shutdown_subsystems(app)

            mock_probe.assert_called_once()
            mock_stop_event.set.assert_called_once()

            assert task1.cancelled()
            assert task2.cancelled()

            mock_container.close.assert_awaited_once()
            mock_presence.assert_awaited_once()
            mock_notif.assert_awaited_once()
            mock_webpush.assert_called_once()
            mock_cache.assert_awaited_once()
            mock_stopper.assert_awaited_once()
            mock_flags.assert_awaited_once()
            mock_ratelimit.assert_awaited_once()
            mock_spicedb.assert_awaited_once()
            mock_otel.assert_called_once()
            mock_geo.assert_called_once()
            mock_hibp.assert_awaited_once()
    finally:
        # Clean up tasks
        task1.cancel()
        task2.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)

    # Teardown branches: no background tasks, no partition stopper
    app_empty = FastAPI()
    app_empty.state.dishka_container = mock_container

    with (
        patch("app.api.health.set_shutdown_flag"),
        patch("app.core.lifespan._SCHEDULER_STOP"),
        patch("app.api.ws.presence.stop_presence_pubsub", new_callable=AsyncMock),
        patch(
            "app.services.notification_queue.shutdown_notification_queue",
            new_callable=AsyncMock,
        ),
        patch("app.core.lifespan.webpush.cleanup"),
        patch("app.core.lifespan.shutdown_cache", new_callable=AsyncMock),
        patch("app.core.feature_flags.feature_flags.close", new_callable=AsyncMock),
        patch("app.core.ratelimit.stop_memory_cleanup_task", new_callable=AsyncMock),
        patch("app.core.spicedb.close_global_spicedb_channel", new_callable=AsyncMock),
        patch("app.core.lifespan.shutdown_observability"),
        patch("app.services.geolocation.shutdown_geolocation_service"),
        patch("app.auth.security.close_hibp_client", new_callable=AsyncMock),
    ):
        await _shutdown_subsystems(app_empty)
        # Should complete without error when optional attrs are missing
