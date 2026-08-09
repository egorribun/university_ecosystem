from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import app.core.lifespan as lifespan_module
from app.core.lifespan import lifespan


@pytest.mark.asyncio
async def test_lifespan_recreates_closed_dishka_container() -> None:
    """A second ASGI lifespan must never reuse a closed application container."""
    app = FastAPI()
    old_container = MagicMock()
    replacement = MagicMock()
    app.state.dishka_container = old_container
    app.state._dishka_container_closed = True

    with (
        patch(
            "app.core.di_provider.create_dishka_container",
            return_value=replacement,
        ) as create_container,
        patch("app.core.lifespan._startup_database_and_di", new_callable=AsyncMock),
        patch("app.core.lifespan._startup_websocket_and_flags", new_callable=AsyncMock),
        patch("app.core.lifespan._validate_di_container", new_callable=AsyncMock),
        patch("app.core.lifespan._verify_database_readiness", new_callable=AsyncMock),
        patch(
            "app.core.lifespan._handle_schema_and_extensions", new_callable=AsyncMock
        ),
        patch("app.core.lifespan._startup_background_workers", new_callable=AsyncMock),
        patch("app.core.ratelimit.start_memory_cleanup_task"),
        patch(
            "app.core.lifespan._prewarm_jwt_public_key_cache", new_callable=AsyncMock
        ),
        patch("app.core.lifespan._shutdown_subsystems", new_callable=AsyncMock),
        patch.object(lifespan_module, "_LISTENERS_REGISTERED", True),
    ):
        async with lifespan(app):
            assert app.state.dishka_container is replacement

    create_container.assert_called_once_with()
    assert app.state.dishka_container is replacement
