import pytest
from pydantic import BaseModel, Field

from app.core.nats_registry import (
    register_task,
    get_task_schema,
    is_registered,
    list_registered_tasks,
    _TASK_SCHEMAS,
)
from app.core.nats_broker import set_app

@pytest.fixture(autouse=True)
def cleanup_registry():
    # Save the current state
    old_schemas = _TASK_SCHEMAS.copy()
    yield
    # Restore the state
    _TASK_SCHEMAS.clear()
    _TASK_SCHEMAS.update(old_schemas)

def test_nats_registry():
    @register_task
    class MyTestTask(BaseModel):
        field1: str
    
    assert is_registered("MyTestTask")
    assert get_task_schema("MyTestTask") is MyTestTask

    @register_task
    class MyCustomNameTask(BaseModel):
        __task_name__ = "custom.task.name"
        field2: int
    
    assert is_registered("custom.task.name")
    assert get_task_schema("custom.task.name") is MyCustomNameTask

    tasks = list_registered_tasks()
    assert "MyTestTask" in tasks
    assert "custom.task.name" in tasks

def test_nats_registry_duplicate_registration():
    @register_task
    class DuplicatedTask(BaseModel):
        __task_name__ = "duplicate.name"
    
    # Re-registering the same class is okay
    register_task(DuplicatedTask)
    
    # Registering a different class with the same name raises ValueError
    class AnotherTask(BaseModel):
        __task_name__ = "duplicate.name"
    
    with pytest.raises(ValueError, match="is already registered by"):
        register_task(AnotherTask)

def test_set_app():
    # Test setting the global app for nats broker
    mock_app = object()
    set_app(mock_app)
    
    from app.core.nats_broker import _app
    assert _app is mock_app
    set_app(None)  # cleanup
