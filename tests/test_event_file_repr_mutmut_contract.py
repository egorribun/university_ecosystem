from __future__ import annotations

import uuid

from app.models.events import EventFile


def test_event_file_repr_includes_identity_and_truncated_url() -> None:
    """Keep the EventFile repr mapped in the mutmut population."""

    event_id = uuid.uuid4()
    file_id = uuid.uuid4()
    record = EventFile(
        id=file_id,
        event_id=event_id,
        file_url="https://cdn.example.test/uploads/event-handout.pdf",
    )

    assert repr(record) == (
        f"<EventFile(id={file_id}, eid={event_id}, url='https://cdn.example....')>"
    )
