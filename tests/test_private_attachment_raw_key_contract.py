"""Raw private keys must not inherit absolute-URL suffix semantics."""

from uuid import uuid4

import pytest

from app.schemas.events import EventFileOut


@pytest.mark.parametrize(
    "suffix", ["#fragment", ";version=1"], ids=["fragment", "params"]
)
def test_event_file_output_rejects_malformed_raw_keys_but_parses_absolute_urls(
    suffix: str,
) -> None:
    event_id = uuid4()
    raw_key = f"event_files/event_{event_id}/agenda.pdf{suffix}"

    raw_output = EventFileOut(id=uuid4(), event_id=event_id, file_url=raw_key)

    assert raw_output.model_dump()["file_url"] == ""

    absolute_output = EventFileOut(
        id=uuid4(),
        event_id=event_id,
        file_url=f"https://cdn.example.test/{raw_key}",
    )

    assert absolute_output.model_dump()["file_url"] == (
        f"/api/v1/events/{event_id}/files/agenda.pdf"
    )
