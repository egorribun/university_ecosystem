"""Schedule text newlines remain TEXT, never physical iCalendar delimiters."""

from datetime import UTC, datetime

import pytest

from app import models
from app.repositories.unit_of_work import uow_from_session
from app.schemas.schedule import ScheduleCreate
from app.services.ical import _escape
from app.services.schedule_optimizer import ScheduleOptimizerService
from app.services.schedule_service import ScheduleService
from tests.conftest import install_dishka_override


@pytest.mark.parametrize(
    "value,expected",
    [
        ("First\r\nSecond", r"First\nSecond"),
        ("First\rSecond", r"First\nSecond"),
        ("First\nSecond", r"First\nSecond"),
        ("a\r\nb\rc\nd", r"a\nb\nc\nd"),
        ("\r\n\r\n", r"\n\n"),
        ("First\r\n Second\r\n\tThird", "First\\n Second\\n\tThird"),
        ("Математика\r\n日本語 😀", r"Математика\n日本語 😀"),
        ("A; B, C\\D\r\nNext", r"A\; B\, C\\D\nNext"),
        (r"C:\Users\teacher\notes.txt", r"C:\\Users\\teacher\\notes.txt"),
        (r"Literal \n", r"Literal \\n"),
        ("Plain text", "Plain text"),
        ("", ""),
        (None, ""),
    ],
)
def test_escape_normalizes_text_line_endings_without_changing_literals(value, expected):
    assert _escape(value) == expected


@pytest.mark.parametrize("field", ["subject", "teacher", "room"])
@pytest.mark.parametrize("newline", ["\r\n", "\r", "\n"], ids=["crlf", "cr", "lf"])
async def test_schedule_export_preserves_unicode_text_without_raw_line_breaks(
    app, async_client, db_session, field, newline
):
    group = models.Group(name="Synthetic calendar", course=1, faculty="Synthetic")
    db_session.add(group)
    await db_session.flush()
    # Long multibyte text and leading continuation whitespace must stay data.
    # This covers unfolding-like input, not a new 75-octet folding mechanism.
    first = "Математика 日本語 😀 " * 5
    data = {
        "group_id": group.id,
        "subject": "Synthetic seminar",
        "teacher": "Synthetic Teacher",
        "room": "Room 1",
        "weekday": "monday",
        "start_time": datetime(2035, 1, 1, 9, tzinfo=UTC),
        "end_time": datetime(2035, 1, 1, 10, tzinfo=UTC),
        "parity": "both",
    }
    data[field] = first + newline + " Second" + newline + "\tThird"
    accepted = ScheduleCreate.model_validate(data)
    assert getattr(accepted, field) == data[field]
    db_session.add(models.Schedule(**accepted.model_dump()))
    await db_session.commit()
    service = ScheduleService(uow_from_session(db_session), ScheduleOptimizerService())
    install_dishka_override(app, ScheduleService=service)

    response = await async_client.get(f"/schedule/ics?group={group.id}")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.headers["content-language"] == "en"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-disposition"] == (
        'attachment; filename="schedule-synthetic-calendar.ics"'
    )
    physical_lines = response.content.split(b"\r\n")
    assert all(b"\r" not in line and b"\n" not in line for line in physical_lines)
    assert physical_lines.count(b"BEGIN:VEVENT") == 16
    assert physical_lines.count(b"END:VEVENT") == 16
    expected = first + "\\n Second\\n\tThird"
    # Read logical content lines without forbidding a future line-folding writer.
    unfolded = response.content.replace(b"\r\n ", b"").replace(b"\r\n\t", b"")
    assert expected.encode() in unfolded
    logical_lines = unfolded.split(b"\r\n")
    assert sum(line.startswith(b"SUMMARY:") for line in logical_lines) == 16
    assert sum(line.startswith(b"LOCATION:") for line in logical_lines) == 16
    assert sum(line.startswith(b"DESCRIPTION:") for line in logical_lines) == 16
