import taskiq_fastapi
from taskiq_redis import RedisAsyncResultBackend, TaskiqRedisBroker

from app.core.config import settings
import app.tasks.email # noqa: F401
import app.tasks.notifications # noqa: F401

result_backend = RedisAsyncResultBackend(
    redis_url=settings.taskiq_broker_url,
)

broker = TaskiqRedisBroker(
    url=settings.taskiq_broker_url,
).with_result_backend(result_backend)

# This allows TaskIQ to use FastAPI dependencies
taskiq_fastapi.init(broker, "app.main:app")
