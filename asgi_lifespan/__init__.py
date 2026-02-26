"""Test-only fallback for :mod:`asgi_lifespan`.

The real dependency is only required for integration tests.  To keep the
production requirements lean we provide a very small compatible shim that knows
how to drive FastAPI/Starlette lifespan hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class LifespanManager:
    """Async context manager that runs application lifespan hooks."""

    def __init__(self, app: Callable[..., Awaitable[Any]] | Any) -> None:
        self._app = app
        self._context = None

    async def __aenter__(self) -> Any:
        context_factory = getattr(self._app, "lifespan_context", None)
        if context_factory is None and hasattr(self._app, "router"):
            context_factory = getattr(self._app.router, "lifespan_context", None)
        if context_factory is None:
            return self._app
        if callable(context_factory):
            try:
                self._context = context_factory(self._app)
            except TypeError:
                self._context = context_factory()
        # The original `else` branch with `type: ignore[unreachable]` was removed
        # as per the instruction to remove unreachable statements.
        # If context_factory is not None and not callable, this path would be taken.
        # However, the instruction implies it's unreachable or should be removed.
        # If context_factory is not callable, and not None, then _context remains None.
        if self._context is not None:
            await self._context.__aenter__()  # type: ignore[unreachable]

        return self._app

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._context is not None:
            await self._context.__aexit__(exc_type, exc, tb)  # type: ignore[unreachable]
            self._context = None
        return False


__all__ = ["LifespanManager"]
