"""AUD-447 residuals: retained error text on the dedup path and escaped link markers.

Error text is written to ``dead_letter_jobs.error_message``.  A reset or
e-mail-change link can reach that column through an upstream error message, in
plain or percent-encoded or HTML-entity-escaped form.  These tests pin that the
scrub covers every such encoding, and that a duplicate failure does not keep a
link that an earlier row already stored.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import (
    _QUARANTINED_AUTH_PAYLOAD,
    DeadLetterQueue,
    compute_job_hash,
)
from tests.test_aud447_quarantine_persistence import _RecordingSession

_OTHER_TASK = "app.tasks.other"
_LINK_MARKER = "synthetic-" + uuid.uuid4().hex
_BASE = "https://portal.example.test/reset-password"


def _retained_error_row(error_message: str, payload: dict[str, Any]) -> DeadLetterJob:
    return DeadLetterJob(
        id=7,
        job_type=_OTHER_TASK,
        job_hash=compute_job_hash(_OTHER_TASK, payload),
        payload="{}",
        error_message=error_message,
        status="pending",
        retry_count=1,
        max_retries=4,
    )


@pytest.mark.asyncio
async def test_aud447_duplicate_failure_scrubs_error_text_retained_by_the_earlier_row() -> (
    None
):
    payload: dict[str, Any] = {"args": []}
    session = _RecordingSession(accept_adds=True)
    session.row = _retained_error_row(
        f"earlier upstream echoed {_BASE}#token={_LINK_MARKER}", payload
    )

    result = await DeadLetterQueue(session).add_failed_job(
        job_type=_OTHER_TASK,
        payload=payload,
        error_message="a fresh failure with no link",
    )

    assert result is None
    assert session.row.error_message == _QUARANTINED_AUTH_PAYLOAD
    assert _LINK_MARKER not in repr(session.row.__dict__)


@pytest.mark.asyncio
async def test_aud447_duplicate_failure_keeps_ordinary_retained_error_text() -> None:
    payload: dict[str, Any] = {"args": []}
    session = _RecordingSession(accept_adds=True)
    session.row = _retained_error_row("SMTP timeout after 30s", payload)

    result = await DeadLetterQueue(session).add_failed_job(
        job_type=_OTHER_TASK,
        payload=payload,
        error_message="another failure",
    )

    assert result is None
    assert session.row.error_message == "SMTP timeout after 30s"


@pytest.mark.parametrize(
    "error_text",
    [
        f"{_BASE}#token={_LINK_MARKER}",
        f"{_BASE}?token={_LINK_MARKER}",
        f"{_BASE}&token={_LINK_MARKER}",
        f"{_BASE}#Token={_LINK_MARKER}",
        f"{_BASE}%23token%3D{_LINK_MARKER}",
        f"{_BASE}%3Ftoken%3D{_LINK_MARKER}",
        f"{_BASE}%26token%3D{_LINK_MARKER}",
        f"{_BASE}?a=1&amp;token={_LINK_MARKER}",
        f"{_BASE}?a=1&#38;token={_LINK_MARKER}",
        f"{_BASE}?a=1&#x26;token={_LINK_MARKER}",
    ],
    ids=[
        "fragment",
        "query",
        "ampersand",
        "mixed-case",
        "percent-fragment",
        "percent-query",
        "percent-ampersand",
        "html-amp-entity",
        "html-decimal-entity",
        "html-hex-entity",
    ],
)
@pytest.mark.asyncio
async def test_aud447_every_encoding_of_a_token_link_is_scrubbed(
    error_text: str,
) -> None:
    session = _RecordingSession(accept_adds=True)

    job = await DeadLetterQueue(session).add_failed_job(
        job_type=_OTHER_TASK,
        payload={"args": []},
        error_message=f"upstream: {error_text}",
    )

    assert job is not None
    assert job.error_message == _QUARANTINED_AUTH_PAYLOAD
    assert _LINK_MARKER not in repr(job.__dict__)


@pytest.mark.parametrize(
    "error_text",
    [
        "token expired at 12:00",
        "invalid token format",
        "https://portal.example.test/reset-password#section=token",
        "refresh_token=abc is not a reset link",
    ],
)
@pytest.mark.asyncio
async def test_aud447_ordinary_text_mentioning_tokens_is_kept(error_text: str) -> None:
    session = _RecordingSession(accept_adds=True)

    job = await DeadLetterQueue(session).add_failed_job(
        job_type=_OTHER_TASK,
        payload={"args": []},
        error_message=error_text,
    )

    assert job is not None
    assert job.error_message == error_text
