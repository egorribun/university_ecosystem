"""R81 (ТЗ Search): the event analytics path is removed from EventRepository.

The removed ``EventRepository.get_analytics_data`` queried ``max_attendees``.
These checks pin that the method does not return and that the repository
module does not select ``max_attendees`` again.
"""

from __future__ import annotations

import inspect

from app.repositories import event_repository as event_repository_module
from app.repositories.event_repository import EventRepository


def test_event_repository_has_no_get_analytics_data() -> None:
    assert not hasattr(EventRepository, "get_analytics_data")


def test_event_repository_instances_expose_no_get_analytics_data() -> None:
    assert not any(
        name == "get_analytics_data" for name, _ in inspect.getmembers(EventRepository)
    )


def test_event_repository_module_does_not_select_max_attendees() -> None:
    source = inspect.getsource(event_repository_module)
    assert "max_attendees" not in source
