"""Closure tests for storage failure reporting and Typer entrypoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cli.infra import check_infra, main


@pytest.mark.asyncio
async def test_infra_check_reports_storage_backend_failure():
    with (
        patch("app.cli.infra.engine") as engine,
        patch("app.cli.infra.get_cache", return_value=MagicMock()),
        patch("app.cli.infra.get_nats_service") as get_nats,
        patch("app.cli.infra.settings") as settings,
        patch(
            "app.services.storage.get_storage_backend",
            side_effect=OSError("storage offline"),
        ),
        patch("app.cli.infra.console.print"),
    ):
        engine.connect.return_value.__aenter__.return_value.execute = AsyncMock()
        nats = MagicMock()
        nats.connect = AsyncMock()
        nats.close = AsyncMock()
        get_nats.return_value = nats
        settings.storage_backend = "s3"

        await check_infra()


def test_infra_typer_entrypoint_runs_async_check():
    def close_coroutine(coro):
        coro.close()

    with patch("app.cli.infra.asyncio.run", side_effect=close_coroutine) as run:
        main()

    run.assert_called_once()
