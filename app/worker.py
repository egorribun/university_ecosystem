# This is a dedicated entrypoint for the NATS JetStream task worker.
# In production, run:
#   python -m app.worker

import asyncio
import logging

import app.tasks.cleanups

# Import tasks to ensure they are registered with the broker
import app.tasks.email
import app.tasks.notifications  # noqa: F401
from app.core.nats_broker import broker

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
