import asyncio
import logging
import time
from typing import Any

import taskiq_fastapi
from taskiq import TaskiqScheduler
from taskiq.abc.middleware import TaskiqMiddleware
from taskiq.message import TaskiqMessage
from taskiq_redis import RedisAsyncResultBackend, RedisScheduleSource, RedisStreamBroker

from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskiqTrackingMiddleware(TaskiqMiddleware):
    """Middleware to track active tasks for synchronization in tests."""

    def __init__(self) -> None:
        super().__init__()
        self.active_tasks: set[str] = set()
        self._all_tasks_done = asyncio.Event()
        self._all_tasks_done.set()

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        self.active_tasks.add(message.task_id)
        self._all_tasks_done.clear()
        return message

    def post_execute(self, message: TaskiqMessage, result: Any) -> None:
        self.active_tasks.discard(message.task_id)
        if not self.active_tasks:
            self._all_tasks_done.set()

    def on_error(
        self, message: TaskiqMessage, result: Any, exception: Exception
    ) -> None:
        self.active_tasks.discard(message.task_id)
        if not self.active_tasks:
            self._all_tasks_done.set()

    async def wait_for_tasks(self, timeout: float = 10.0) -> None:
        """Wait for all active tasks to complete."""
        if not self.active_tasks:
            return
        try:
            await asyncio.wait_for(self._all_tasks_done.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                f"Warning: Timed out waiting for taskiq tasks: {self.active_tasks}"
            )


class TaskiqObservabilityMiddleware(TaskiqMiddleware):
    """Middleware for task logging and performance tracking."""

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        message.labels["_start_time"] = time.perf_counter()
        logger.info(
            "Task started: %s (id: %s)",
            message.task_name,
            message.task_id,
        )
        return message

    def post_execute(self, message: TaskiqMessage, result: Any) -> None:
        start_time = message.labels.get("_start_time")
        duration = 0.0
        if start_time:
            duration = (time.perf_counter() - start_time) * 1000.0

        logger.info(
            "Task completed: %s (id: %s) in %.2fms",
            message.task_name,
            message.task_id,
            duration,
        )

    def on_error(
        self,
        message: TaskiqMessage,
        result: Any,
        exception: Exception,
    ) -> None:
        start_time = message.labels.get("_start_time")
        duration = 0.0
        if start_time:
            duration = (time.perf_counter() - start_time) * 1000.0

        logger.error(
            "Task failed: %s (id: %s) after %.2fms - %s: %s",
            message.task_name,
            message.task_id,
            duration,
            type(exception).__name__,
            str(exception),
            exc_info=True,
        )


tracking_middleware = TaskiqTrackingMiddleware()
observability_middleware = TaskiqObservabilityMiddleware()

if settings.environment.lower() in ("test", "testing"):
    from taskiq import InMemoryBroker

    broker = InMemoryBroker()
    broker.add_middlewares(tracking_middleware, observability_middleware)
    schedule_source = None
    scheduler = TaskiqScheduler(broker, sources=[])
else:
    result_backend = RedisAsyncResultBackend(
        redis_url=settings.taskiq_broker_url,
    )

    broker = RedisStreamBroker(
        url=settings.taskiq_broker_url,
        # Optimize Redis Stream parameters for better performance
        # heartbeat is not directly a param of RedisStreamBroker, but we can tune others
    ).with_result_backend(result_backend)

    # Global middlewares
    broker.add_middlewares(observability_middleware)

    schedule_source = RedisScheduleSource(url=settings.taskiq_broker_url)
    scheduler = TaskiqScheduler(broker, sources=[schedule_source])

# This allows TaskIQ to use FastAPI dependencies
taskiq_fastapi.init(broker, "app.main:app")

# Import task modules AFTER broker is defined to avoid circular imports
import app.tasks.cleanups  # noqa: E402
import app.tasks.email  # noqa: E402
import app.tasks.notifications  # noqa: F401, E402
