"""Manual entrypoint for running story cleanup."""

from __future__ import annotations

import asyncio

from app.services.story_cleanup import cleanup_expired_stories


def main() -> None:
    removed = asyncio.run(cleanup_expired_stories())
    print(f"Removed {removed} expired stories")


if __name__ == "__main__":
    main()
