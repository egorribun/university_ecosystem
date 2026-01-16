import taskiq_fastapi
from taskiq import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisScheduleSource, RedisStreamBroker

from app.core.config import settings

if settings.environment.lower() in ("test", "testing"):
    from taskiq import InMemoryBroker

    broker = InMemoryBroker()
    scheduler = TaskiqScheduler(broker, sources=[])
else:
    result_backend = RedisAsyncResultBackend(
        redis_url=settings.taskiq_broker_url,
    )

    broker = RedisStreamBroker(
        url=settings.taskiq_broker_url,
    ).with_result_backend(result_backend)

    redis_source = RedisScheduleSource(url=settings.taskiq_broker_url)
    scheduler = TaskiqScheduler(broker, sources=[redis_source])

# This allows TaskIQ to use FastAPI dependencies
taskiq_fastapi.init(broker, "app.main:app")

# Import task modules AFTER broker is defined to avoid circular imports
import app.tasks.cleanups  # noqa: F401, E402
import app.tasks.email  # noqa: F401, E402
import app.tasks.notifications  # noqa: F401, E402
