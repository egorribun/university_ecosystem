from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from app.cli.infra import app
from app.deps.cache import RedisCache

runner = CliRunner()


def test_infra_check_all_success():
    # We need to patch the async runner inside the command
    # However, the command runs asyncio.run(_run())
    # So we need to patch the internal components that _run calls.

    with (
        patch("app.cli.infra.engine") as mock_engine,
        patch("app.cli.infra.get_cache") as mock_get_cache,
        patch("app.cli.infra.get_nats_service") as mock_get_nats,
        patch("app.cli.infra.get_storage_service"),
        patch("app.cli.infra.settings") as mock_settings,
    ):
        # Postgres
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = None
        mock_engine.connect.return_value.__aenter__.return_value = mock_conn

        # Redis
        mock_cache = MagicMock(spec=RedisCache)
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_cache._get_client.return_value = mock_client
        mock_get_cache.return_value = mock_cache

        # NATS
        mock_nats = MagicMock()
        mock_nats.connect = AsyncMock()
        mock_nats.close = AsyncMock()
        mock_get_nats.return_value = mock_nats

        # Storage
        mock_settings.storage_backend = "minio"

        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0


def test_infra_check_all_failures():
    with (
        patch("app.cli.infra.engine") as mock_engine,
        patch("app.cli.infra.get_cache") as mock_get_cache,
        patch("app.cli.infra.get_nats_service") as mock_get_nats,
        patch("app.cli.infra.settings") as mock_settings,
    ):
        # Postgres fail
        mock_engine.connect.side_effect = Exception("DB Fail")

        # Redis fail
        mock_cache = MagicMock(spec=RedisCache)
        mock_cache._get_client.side_effect = Exception("Redis Fail")
        mock_get_cache.return_value = mock_cache

        # NATS fail
        mock_nats = MagicMock()
        mock_nats.connect.side_effect = Exception("NATS Fail")
        mock_get_nats.return_value = mock_nats

        # Storage skipped
        mock_settings.storage_backend = "local"

        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0  # Command itself doesn't crash


def test_infra_check_redis_skipped():
    with (
        patch("app.cli.infra.engine") as mock_engine,
        patch("app.cli.infra.get_cache") as mock_get_cache,
        patch("app.cli.infra.get_nats_service") as mock_nats,
    ):
        # Mock other services to pass or fail, doesn't matter
        mock_engine.connect.return_value.__aenter__.return_value.execute = AsyncMock()
        mock_nats.return_value.connect = AsyncMock()

        # Redis not RedisCache
        mock_get_cache.return_value = MagicMock()  # Not RedisCache instance

        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0


def test_infra_check_nats_timeout():
    with (
        patch("app.cli.infra.engine") as mock_engine,
        patch("app.cli.infra.get_cache") as mock_cache,
        patch("app.cli.infra.get_nats_service") as mock_get_nats,
    ):
        mock_engine.connect.return_value.__aenter__.return_value.execute = AsyncMock()
        mock_cache.return_value = MagicMock()

        mock_nats = MagicMock()
        mock_nats.connect = AsyncMock(side_effect=TimeoutError)
        mock_get_nats.return_value = mock_nats

        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
