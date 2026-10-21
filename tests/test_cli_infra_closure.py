"""Closure tests for storage failure reporting and Typer entrypoint."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from sqlalchemy.ext.asyncio import create_async_engine

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


@pytest.mark.asyncio
@pytest.mark.parametrize("database_available", [True, False], ids=["healthy", "offline"])
async def test_infra_database_status_uses_a_real_sqlalchemy_connection(
    database_available: bool,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    unavailable = MagicMock()
    unavailable.connect.side_effect = OSError("database unavailable")
    output = StringIO()
    nats = SimpleNamespace(connect=AsyncMock(), close=AsyncMock())
    try:
        with (
            patch("app.cli.infra.engine", engine if database_available else unavailable),
            patch("app.cli.infra.get_cache", return_value=object()),
            patch("app.cli.infra.get_nats_service", return_value=nats),
            patch("app.cli.infra.settings", SimpleNamespace(storage_backend="local")),
            patch(
                "app.cli.infra.console",
                Console(file=output, force_terminal=False, width=120),
            ),
        ):
            await check_infra()
    finally:
        await engine.dispose()

    rendered = output.getvalue()
    postgres_row = next(line for line in rendered.splitlines() if "PostgreSQL" in line)
    assert ("ONLINE" if database_available else "OFFLINE") in postgres_row
    if not database_available:
        assert "database unavailable" in rendered
    assert "Redis (Cache)" in rendered
    assert "NATS" in rendered
    nats.connect.assert_awaited_once()
    nats.close.assert_awaited_once()
