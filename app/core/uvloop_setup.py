"""Configure uvloop as the default event loop when available.

uvloop is a fast, drop-in replacement for the default asyncio event loop.
It is built on top of libuv (the same library used by Node.js) and provides
significant performance improvements (30-50%) for async operations.

Note: uvloop only works on Linux and macOS. On Windows, this module
gracefully falls back to the standard asyncio event loop.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def configure_uvloop() -> bool:
    """Install uvloop as the default event loop policy if available.

    Returns True if uvloop was successfully configured, False otherwise.
    Works silently on Windows where uvloop is not supported.
    """
    if sys.platform == "win32":
        logger.debug("uvloop not available on Windows, using default asyncio loop")
        return False

    try:
        import asyncio

        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop installed as default event loop")
        return True
    except ImportError:
        logger.debug("uvloop not installed, using default asyncio loop")
        return False
    except Exception as exc:
        logger.warning("Failed to configure uvloop: %s", exc)
        return False


def get_loop_implementation() -> str:
    """Return the name of the current event loop implementation.

    Useful for logging and debugging purposes.
    """
    try:
        import asyncio

        loop = asyncio.get_event_loop_policy()
        return type(loop).__name__
    except Exception:
        return "unknown"
