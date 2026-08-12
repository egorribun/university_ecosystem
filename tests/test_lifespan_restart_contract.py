from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import app.core.lifespan as lifespan_module
from app.core.lifespan import (
    _reset_closed_dishka_container,
    _shutdown_subsystems,
    lifespan,
)


def test_reset_closed_dishka_container_keeps_open_containers_and_sets_boolean_marker() -> (
    None
):
    """First startup and an open restart must retain the live root container."""
    for initial_marker in (None, False):
        app = FastAPI()
        original = MagicMock()
        app.state.dishka_container = original
        if initial_marker is not None:
            app.state._dishka_container_closed = initial_marker

        with patch("app.core.di_provider.create_dishka_container") as factory:
            _reset_closed_dishka_container(app)

        assert app.state.dishka_container is original
        assert app.state._dishka_container_closed is False
        factory.assert_not_called()


def test_reset_closed_dishka_container_replaces_only_a_closed_container() -> None:
    """A closed root is replaced once and becomes explicitly open again."""
    app = FastAPI()
    replacement = MagicMock()
    app.state.dishka_container = MagicMock()
    app.state._dishka_container_closed = True

    with patch(
        "app.core.di_provider.create_dishka_container", return_value=replacement
    ) as factory:
        _reset_closed_dishka_container(app)

    assert app.state.dishka_container is replacement
    assert app.state._dishka_container_closed is False
    factory.assert_called_once_with()


@pytest.mark.asyncio
async def test_shutdown_marks_container_closed_before_close_failure() -> None:
    """A failed close must still make the next lifespan recreate the root."""
    app = FastAPI()
    replacement = MagicMock()

    async def close_and_assert_marker() -> None:
        assert app.state._dishka_container_closed is True
        raise RuntimeError("container close failed")

    container = MagicMock()
    container.close = AsyncMock(side_effect=close_and_assert_marker)
    app.state.dishka_container = container

    with (
        patch("app.api.health.set_shutdown_flag"),
        patch("app.core.lifespan._SCHEDULER_STOP"),
        pytest.raises(RuntimeError, match="container close failed"),
    ):
        await _shutdown_subsystems(app)

    assert app.state._dishka_container_closed is True
    with patch(
        "app.core.di_provider.create_dishka_container", return_value=replacement
    ) as factory:
        _reset_closed_dishka_container(app)

    assert app.state.dishka_container is replacement
    assert app.state._dishka_container_closed is False
    factory.assert_called_once_with()


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
