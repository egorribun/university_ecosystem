"""NATS task schema registry.

MOD-W5-03 (audit 2026-03-13): Centralised typed-payload registry for all NATS
background tasks.  The ``@register_task`` decorator binds a Pydantic model class
to a task name, giving:

  1. **Parse-time validation** — the worker calls ``get_task_schema(name)`` and
     validates the raw payload against the model before dispatching.  Unknown
     names are rejected before any handler is invoked (complements P1-W5-09).
  2. **Self-documenting contracts** — every async task has an explicit,
     discoverable schema.  ``list_registered_tasks()`` returns the full catalogue
     for tooling and documentation.
  3. **Type safety** — task publishers can import the model and use
     ``model.model_validate(payload).model_dump()`` to guarantee a valid payload.

Usage
-----
Publishing side::

    from app.core.nats_registry import register_task
    from pydantic import BaseModel
    from uuid import UUID

    @register_task
    class SendNotificationTask(BaseModel):
        user_id: UUID
        title: str = Field(max_length=100)
        body: str = Field(max_length=500)

Worker side::

    from app.core.nats_registry import get_task_schema

    schema_cls = get_task_schema(task_name)
    if schema_cls is None:
        logger.error("Unknown task: %s", task_name)
        await msg.ack()
        return
    validated = schema_cls.model_validate(raw_payload)
"""

from __future__ import annotations

from pydantic import BaseModel

# Module-level registry: task_name → Pydantic model class.
# Populated exclusively by @register_task at import time.
_TASK_SCHEMAS: dict[str, type[BaseModel]] = {}


def register_task[T: type[BaseModel]](model_cls: T) -> T:
    """Class decorator that registers a Pydantic model as a NATS task schema.

    The task name defaults to the class name (e.g. ``SendNotificationTask``).
    To use a custom name, subclass and override ``__task_name__``::

        @register_task
        class MyTask(BaseModel):
            __task_name__ = "my.custom.task.name"
            ...

    Raises:
        ValueError: if the name is already registered by a *different* class.
    """
    task_name: str = getattr(model_cls, "__task_name__", model_cls.__name__)
    existing = _TASK_SCHEMAS.get(task_name)
    if existing is not None and existing is not model_cls:
        raise ValueError(
            f"NATS task name {task_name!r} is already registered by {existing!r}. "
            "Use __task_name__ to disambiguate."
        )
    _TASK_SCHEMAS[task_name] = model_cls
    return model_cls


def get_task_schema(task_name: str) -> type[BaseModel] | None:
    """Return the Pydantic model class for *task_name*, or ``None`` if unknown."""
    return _TASK_SCHEMAS.get(task_name)


def is_registered(task_name: str) -> bool:
    """Return True if *task_name* is in the registry."""
    return task_name in _TASK_SCHEMAS


def list_registered_tasks() -> list[str]:
    """Return a sorted list of all registered task names (for docs/tooling)."""
    return sorted(_TASK_SCHEMAS)
