"""Manual entrypoint for running story cleanup."""

from __future__ import annotations

import asyncio
import logging

from app.services.story_cleanup import cleanup_expired_stories

logger = logging.getLogger(__name__)


def main() -> None:
    removed = asyncio.run(cleanup_expired_stories())
    logger.info(f"Removed {removed} expired stories")


if __name__ == "__main__":
    main()
