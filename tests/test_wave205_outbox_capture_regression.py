"""Wave 205 SW-A regression — the central outbox-capture fix (the producer side).

The W205 SW-A fix (`app/core/events.py`) closed a systemic gap that broke the
ENTIRE domain-event/outbox subsystem (new_message, notifications, embeddings,
attachment-cleanup) — `stored_events` was empty for ALL aggregate types in W204.

Root cause: an aggregate flushed BEFORE its ``record_event`` call (the real
trigger: ``repository.create_message()`` flushes the Message, THEN
``command_service`` records ``MessageSent``) is *persistent* — it sits in none of
``session.new | session.dirty | session.deleted`` at the next flush — so the
``after_flush`` listener (``capture_domain_events``) never saw it. For a
content-only commit, no further flush ever fired, so the StoredEvent (outbox row)
was silently dropped.

The fix added three things:
  1. ``_event_emitters`` tracking in ``record_event`` (registers the emitter on
     ``session.info`` so capture can scan it even when it is not in new/dirty/deleted),
  2. a scan of that tracked set inside ``capture_domain_events``,
  3. a ``before_commit`` catch-all (``capture_on_commit``) — ``before_commit`` fires
     on EVERY commit regardless of pending flushes, so it reliably captures events
     recorded after their emitter's last flush.

These tests guard all three so a future refactor cannot silently re-break the
outbox. The downstream consumer (``handle_message_sent``) is guarded separately by
``tests/services/test_chat_helpers.py``; THIS file guards the PRODUCER (the capture
mechanism that writes the StoredEvent in the first place).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.events import (
    MessageSent,
    _persist_captured_events,
    capture_domain_events,
    capture_on_commit,
    register_event_listeners,
)
from app.models.domain_events import StoredEvent
from app.models.news import News


@pytest.mark.asyncio
async def test_event_recorded_after_flush_is_captured_at_commit(db_session) -> None:
    """THE regression: record an event AFTER the emitter's last flush → the
    ``before_commit`` catch-all persists exactly one StoredEvent at commit.

    Reproduces the exact production trigger end-to-end (flush, then
    ``record_event``, then commit with NO further flush) through the real
    ``record_event`` ``_event_emitters`` tracking + the ``before_commit``
    listener + real StoredEvent persistence. Without ALL THREE of the SW-A
    additions, NO StoredEvent is produced — the W204 systemic gap.

    ``News`` is the minimal constructable ``EventEmitterMixin`` aggregate; the
    capture listener is model-agnostic, so it stands in for the ``Message`` that
    triggered the real bug. The recorded ``MessageSent`` is the exact event whose
    ``chat.message_sent`` outbox row was being dropped (closing the W204 §Honesty
    new_message-live gap).
    """
    await register_event_listeners()  # idempotent — ensures the 3 listeners are wired

    news = News(title="W205 capture regression", content="record-after-flush")
    db_session.add(news)
    await db_session.flush()  # news is now PERSISTENT — absent from new|dirty|deleted

    # Record the event AFTER the flush — the scenario after_flush alone never sees.
    news.record_event(MessageSent(message_id=uuid.uuid4(), content_preview="x"))

    await db_session.commit()  # before_commit → capture_on_commit → StoredEvent

    count = await db_session.scalar(
        select(func.count())
        .select_from(StoredEvent)
        .where(
            StoredEvent.aggregate_type == "News",
            StoredEvent.aggregate_id == str(news.id),
            StoredEvent.event_type == "chat.message_sent",
        )
    )
    assert count == 1  # exactly one — and idempotent even under double-listener init


@pytest.mark.asyncio
async def test_register_event_listeners_wires_all_three_capture_listeners() -> None:
    """Wiring guard: dropping the ``before_commit`` registration (or either
    ``after_flush`` listener) would silently re-break the outbox — this fails if
    any of the three SW-A capture listeners is unwired on the base ``Session``.
    """
    await register_event_listeners()

    assert sa_event.contains(Session, "after_flush", capture_domain_events)
    assert sa_event.contains(Session, "after_flush_postexec", _persist_captured_events)
    # The W205 SW-A catch-all — the one that closed the systemic gap.
    assert sa_event.contains(Session, "before_commit", capture_on_commit)


def test_capture_on_commit_idempotent_with_prior_after_flush() -> None:
    """``capture_on_commit`` reuses collect+persist; ``clear_events()`` empties the
    emitter after the first pass, so an ``after_flush`` capture followed by the
    ``before_commit`` catch-all produces exactly ONE StoredEvent — no duplicate
    (safe even with the x2 listener init the SW-A commit message calls out).
    """

    class _FakeEmitter:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self._pending_domain_events = [
                MessageSent(message_id=uuid.uuid4(), content_preview="y")
            ]

        def clear_events(self) -> None:
            self._pending_domain_events = []

    class _FakeSession:
        """Minimal Session stand-in: an emitter tracked in ``_event_emitters`` but
        absent from new|dirty|deleted — the exact post-flush-record state."""

        def __init__(self, emitter: _FakeEmitter) -> None:
            self.new: set = set()
            self.dirty: set = set()
            self.deleted: set = set()
            self.info: dict = {"_event_emitters": {emitter}}
            self.added: list = []

        def add_all(self, objs) -> None:
            self.added.extend(objs)

    emitter = _FakeEmitter()
    session = _FakeSession(emitter)

    # after_flush pass (collect) + after_flush_postexec (persist).
    capture_domain_events(session, None)
    _persist_captured_events(session, None)
    assert len(session.added) == 1  # captured once
    assert isinstance(session.added[0], StoredEvent)
    assert session.added[0].event_type == "chat.message_sent"
    assert emitter._pending_domain_events == []  # cleared
    assert session.info["_event_emitters"] == set()  # tracked set drained

    # before_commit catch-all — emitter already cleared → collects nothing → no duplicate.
    capture_on_commit(session)
    assert len(session.added) == 1  # STILL exactly one, not two
