import taskiq_fastapi
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

import app.tasks.email  # noqa: F401
import app.tasks.notifications  # noqa: F401
from app.core.config import settings

result_backend = RedisAsyncResultBackend(
    redis_url=settings.taskiq_broker_url,
)

broker = RedisStreamBroker(
    url=settings.taskiq_broker_url,
).with_result_backend(result_backend)

# This allows TaskIQ to use FastAPI dependencies
taskiq_fastapi.init(broker, "app.main:app")
