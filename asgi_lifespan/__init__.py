"""Test-only fallback for :mod:`asgi_lifespan`.

The real dependency is only required for integration tests.  To keep the
production requirements lean we provide a very small compatible shim that knows
how to drive FastAPI/Starlette lifespan hooks.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable


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
        else:
            self._context = None
        if self._context is None:
            return self._app
        await self._context.__aenter__()
        return self._app

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._context is not None:
            await self._context.__aexit__(exc_type, exc, tb)
            self._context = None
        return False


__all__ = ["LifespanManager"]
