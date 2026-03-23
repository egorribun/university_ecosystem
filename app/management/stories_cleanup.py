"""Manual entrypoint for running story cleanup."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.services.story_cleanup import cleanup_expired_stories

logger = get_logger(__name__)


def main() -> None:
    removed = asyncio.run(cleanup_expired_stories())
    logger.info("Removed %s expired stories", removed)  # LOW-W19: lazy logging


if __name__ == "__main__":
    main()
