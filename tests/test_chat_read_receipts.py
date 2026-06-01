"""Wave 210 G2 — per-recipient read receipts against a real DB session.

Exercises the ChatReadReceipt high-water-mark for GROUP chats + proves the DM
path stays byte-identical (Option A). The test suite runs on SQLite; the schema
is built from the models so chat_read_receipts is present.

Unread assertions are driven through ``get_chats_for_user`` — NOT
``get_unread_count`` — because the latter calls ``_set_rls_user`` (``SET LOCAL``,
PostgreSQL-only; SQLite rejects it). ``get_chats_for_user`` has no RLS, so the
group-unread CTE + the per-row CASE are exercised end-to-end on SQLite. Receipt
rows are read with column-level SELECTs (a Core INSERT/UPDATE does not refresh
the session identity map).

Determinism: "already-read" messages get an explicit past ``created_at`` so they
provably pre-date the mark; the "new message after read" case reads the receipt's
actual ``last_read_at`` back and stamps ``created_at = last_read_at + 1s`` so the
high-water-mark comparison is a guarantee, not a wall-clock race.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models.chat import ChatReadReceipt, Message, utc_now
from app.repositories.chat_repository import ChatRepository


async def _make_msg(db_session, chat_id, sender_id, *, created_at=None) -> Message:
    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content="m",
        **({"created_at": created_at} if created_at is not None else {}),
    )
    db_session.add(msg)
    await db_session.flush()
    return msg


async def _group_unread(repo, user_id, chat_id) -> int | None:
    """Unread count for (user, chat) as computed by the get_chats_for_user CTE."""
    rows, _has_more, _cursor = await repo.get_chats_for_user(user_id, None, 50)
    for dto, unread, _last in rows:
        if dto.id == chat_id:
            return unread
    return None


async def _receipt_count(db_session, chat_id, user_id=None) -> int:
    query = (
        select(func.count())
        .select_from(ChatReadReceipt)
        .where(ChatReadReceipt.chat_id == chat_id)
    )
    if user_id is not None:
        query = query.where(ChatReadReceipt.user_id == user_id)
    return (await db_session.execute(query)).scalar_one()


def _past(seconds: int):
    """A timestamp clearly in the past so it pre-dates any later mark-read."""
    return utc_now() - timedelta(hours=1) + timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_group_unread_counts_other_sender_messages(db_session, user_factory):
    creator = await user_factory()  # C
    a = await user_factory()
    b = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a, b])

    for i in range(3):
        await _make_msg(db_session, group.id, creator.id, created_at=_past(i))

    # A and B see C's 3 messages as unread; C sees 0 (own messages excluded).
    assert await _group_unread(repo, a.id, group.id) == 3
    assert await _group_unread(repo, b.id, group.id) == 3
    assert await _group_unread(repo, creator.id, group.id) == 0


@pytest.mark.asyncio
async def test_group_unread_is_per_user_not_global(db_session, user_factory):
    """The headline G2 bug fix: the first reader must NOT zero everyone."""
    creator = await user_factory()  # C
    a = await user_factory()
    b = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a, b])

    for i in range(2):
        await _make_msg(db_session, group.id, creator.id, created_at=_past(i))

    # A marks the group read.
    _read_at, affected = await repo.mark_messages_read(group.id, a.id, "group")
    assert affected == 2

    # A is now caught up — but B's unread is UNTOUCHED (per-recipient, not global).
    assert await _group_unread(repo, a.id, group.id) == 0
    assert await _group_unread(repo, b.id, group.id) == 2


@pytest.mark.asyncio
async def test_group_unread_advances_after_mark_then_new_message(
    db_session, user_factory
):
    creator = await user_factory()  # C
    a = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a])

    for i in range(2):
        await _make_msg(db_session, group.id, creator.id, created_at=_past(i))
    assert await _group_unread(repo, a.id, group.id) == 2

    await repo.mark_messages_read(group.id, a.id, "group")
    assert await _group_unread(repo, a.id, group.id) == 0

    # A new message strictly after A's high-water-mark is unread again.
    last_read_at = (
        await db_session.execute(
            select(ChatReadReceipt.last_read_at).where(
                ChatReadReceipt.chat_id == group.id,
                ChatReadReceipt.user_id == a.id,
            )
        )
    ).scalar_one()
    await _make_msg(
        db_session,
        group.id,
        creator.id,
        created_at=last_read_at + timedelta(seconds=1),
    )
    assert await _group_unread(repo, a.id, group.id) == 1


@pytest.mark.asyncio
async def test_mark_read_group_upsert_idempotent(db_session, user_factory):
    creator = await user_factory()  # C
    a = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a])
    for i in range(2):
        await _make_msg(db_session, group.id, creator.id, created_at=_past(i))

    await repo.mark_messages_read(group.id, a.id, "group")
    await repo.mark_messages_read(group.id, a.id, "group")

    # Exactly one receipt row for (group, A) — the second mark UPDATEs, not INSERTs.
    assert await _receipt_count(db_session, group.id, a.id) == 1


@pytest.mark.asyncio
async def test_mark_read_group_affected_gates_broadcast(db_session, user_factory):
    """affected==0 on a re-mark with nothing new → the caller skips the broadcast."""
    creator = await user_factory()  # C
    a = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a])
    for i in range(2):
        await _make_msg(db_session, group.id, creator.id, created_at=_past(i))

    _read_at, affected_first = await repo.mark_messages_read(group.id, a.id, "group")
    assert affected_first == 2

    # Immediate re-mark with no new messages → nothing newly read → no broadcast.
    _read_at2, affected_second = await repo.mark_messages_read(group.id, a.id, "group")
    assert affected_second == 0


@pytest.mark.asyncio
async def test_dm_unread_byte_identical(db_session, user_factory):
    """The DM regression guard: read_status path unchanged, NO receipt row written."""
    u1 = await user_factory()
    u2 = await user_factory()
    repo = ChatRepository(db_session)
    dm = await repo.create_chat([u1, u2])
    assert dm.chat_type == "dm"

    for i in range(3):
        await _make_msg(db_session, dm.id, u2.id, created_at=_past(i))
    assert await _group_unread(repo, u1.id, dm.id) == 3  # via read_status branch

    _read_at, affected = await repo.mark_messages_read(dm.id, u1.id, "dm")
    assert affected == 3
    assert await _group_unread(repo, u1.id, dm.id) == 0

    # DM mechanism untouched: read_status flipped on u2's messages…
    unread_flag_rows = (
        await db_session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.chat_id == dm.id,
                Message.sender_id == u2.id,
                Message.read_status.is_(True),
            )
        )
    ).scalar_one()
    assert unread_flag_rows == 3
    # …and NO ChatReadReceipt row exists for a DM.
    assert await _receipt_count(db_session, dm.id) == 0


@pytest.mark.asyncio
async def test_get_read_receipts_returns_rows_for_group_empty_for_dm(
    db_session, user_factory
):
    creator = await user_factory()  # C
    a = await user_factory()
    b = await user_factory()
    repo = ChatRepository(db_session)
    group = await repo.create_group(creator, "Team", [a, b])
    await _make_msg(db_session, group.id, creator.id, created_at=_past(0))

    await repo.mark_messages_read(group.id, a.id, "group")
    await repo.mark_messages_read(group.id, b.id, "group")

    receipts = await repo.get_read_receipts(group.id)
    assert {uid for uid, _ts in receipts} == {a.id, b.id}
    assert all(ts is not None for _uid, ts in receipts)

    # A DM has no receipt rows.
    dm = await repo.create_chat([creator, a])
    assert await repo.get_read_receipts(dm.id) == []


@pytest.mark.asyncio
async def test_mixed_dm_and_group_in_chat_list(db_session, user_factory):
    """The per-row CASE picks read_status for the DM and the receipt CTE for the group."""
    u = await user_factory()
    x = await user_factory()  # DM counterpart
    y = await user_factory()  # group creator
    z = await user_factory()  # group member
    repo = ChatRepository(db_session)

    dm = await repo.create_chat([u, x])
    for i in range(2):
        await _make_msg(db_session, dm.id, x.id, created_at=_past(i))

    group = await repo.create_group(y, "G", [u, z])
    for i in range(3):
        await _make_msg(db_session, group.id, y.id, created_at=_past(10 + i))

    # One get_chats_for_user pass returns BOTH chats with the right distinct count.
    assert await _group_unread(repo, u.id, dm.id) == 2  # read_status branch
    assert await _group_unread(repo, u.id, group.id) == 3  # receipt-CTE branch
