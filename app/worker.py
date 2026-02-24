# This is a dedicated entrypoint for the NATS JetStream task worker.
# In production, run:
#   python -m app.worker

import asyncio
import logging
from app.core.nats_broker import broker

# Import tasks to ensure they are registered with the broker
import app.tasks.email  # noqa: F401
import app.tasks.notifications  # noqa: F401
import app.tasks.cleanups  # noqa: F401

logger = logging.getLogger(__name__)


async def main():
    """Main entrypoint for starting the NATS JetStream task worker. (MOD-3)"""
    logger.info("NATS Task Worker entrypoint initialized.")
    await broker.run_worker()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
