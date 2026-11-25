from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.localization.dictionary import TRANSLATIONS
from app.models.chat import Chat, chat_participants
from tests.test_chat_api import _login_user


async def _snapshot(db_session, chat_id):
    chat_uuid = UUID(chat_id)
    name = (
        await db_session.execute(select(Chat.name).where(Chat.id == chat_uuid))
    ).scalar_one()
    participant_rows = await db_session.execute(
        select(chat_participants.c.user_id).where(
            chat_participants.c.chat_id == chat_uuid
        )
    )
    return name, set(participant_rows.scalars().all())


async def _operation(client, operation, chat_id, headers, target_id):
    if operation == "add":
        return await client.post(
            f"/chats/{chat_id}/participants",
            json={"user_id": str(target_id)},
            headers=headers,
        )
    if operation == "remove":
        return await client.delete(
            f"/chats/{chat_id}/participants/{target_id}", headers=headers
        )
    return await client.patch(
        f"/chats/{chat_id}", json={"name": "New group title"}, headers=headers
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "member"])
async def test_group_participants_add_and_rename_persist(
    async_client, user_factory, db_session, actor
):
    owner, owner_headers = await _login_user(async_client, user_factory)
    member, member_headers = await _login_user(async_client, user_factory)
    other = await user_factory()
    newcomer = await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Original", "participant_ids": [str(member.id), str(other.id)]},
        headers=owner_headers,
    )
    assert created.status_code == 200
    assert created.json()["created_by"] == str(owner.id)
    chat_id = created.json()["id"]
    headers = owner_headers if actor == "owner" else member_headers

    added = await _operation(async_client, "add", chat_id, headers, newcomer.id)
    renamed = await _operation(async_client, "rename", chat_id, headers, newcomer.id)
    assert added.status_code == 200
    assert renamed.status_code == 200
    name, participants = await _snapshot(db_session, chat_id)
    assert name == "New group title"
    assert participants == {owner.id, member.id, other.id, newcomer.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "rename", "remove"])
async def test_outsider_is_rejected_before_group_or_dm_type(
    async_client, user_factory, db_session, operation
):
    owner, owner_headers = await _login_user(async_client, user_factory)
    outsider, outsider_headers = await _login_user(async_client, user_factory)
    member, other, newcomer = (
        await user_factory(),
        await user_factory(),
        await user_factory(),
    )
    group = await async_client.post(
        "/chats/groups",
        json={"name": "Original", "participant_ids": [str(member.id), str(other.id)]},
        headers=owner_headers,
    )
    dm = await async_client.post(
        "/chats", json={"participant_id": str(member.id)}, headers=owner_headers
    )
    assert group.status_code == dm.status_code == 200
    group_id, dm_id = group.json()["id"], dm.json()["id"]
    before = [await _snapshot(db_session, chat_id) for chat_id in (group_id, dm_id)]
    assert outsider.id not in before[0][1] and outsider.id not in before[1][1]

    target = newcomer.id if operation == "add" else owner.id
    responses = [
        await _operation(async_client, operation, chat_id, outsider_headers, target)
        for chat_id in (group_id, dm_id)
    ]
    assert [response.status_code for response in responses] == [403, 403]
    details = [response.json()["detail"] for response in responses]
    assert details[0] == details[1]
    assert details[0] in TRANSLATIONS["errors.chat.not_participant"].values()
    assert [
        await _snapshot(db_session, chat_id) for chat_id in (group_id, dm_id)
    ] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "rename", "remove"])
async def test_dm_participant_cannot_use_group_operations(
    async_client, user_factory, db_session, operation
):
    owner, headers = await _login_user(async_client, user_factory)
    member, newcomer = await user_factory(), await user_factory()
    dm = await async_client.post(
        "/chats", json={"participant_id": str(member.id)}, headers=headers
    )
    assert dm.status_code == 200
    dm_id = dm.json()["id"]
    before = await _snapshot(db_session, dm_id)
    target = newcomer.id if operation == "add" else owner.id
    response = await _operation(async_client, operation, dm_id, headers, target)
    assert response.status_code == 400
    assert response.json()["detail"] in TRANSLATIONS["errors.chat.not_a_group"].values()
    assert await _snapshot(db_session, dm_id) == before


@pytest.mark.asyncio
async def test_member_cannot_remove_other_but_self_leave_persists(
    async_client, user_factory, db_session
):
    owner, owner_headers = await _login_user(async_client, user_factory)
    member, member_headers = await _login_user(async_client, user_factory)
    other = await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Original", "participant_ids": [str(member.id), str(other.id)]},
        headers=owner_headers,
    )
    assert created.status_code == 200
    assert created.json()["created_by"] == str(owner.id)
    chat_id = created.json()["id"]
    before = await _snapshot(db_session, chat_id)
    denied = await _operation(async_client, "remove", chat_id, member_headers, other.id)
    assert denied.status_code == 403
    assert await _snapshot(db_session, chat_id) == before
    leave = await _operation(async_client, "remove", chat_id, member_headers, member.id)
    assert leave.status_code == 200
    assert await _snapshot(db_session, chat_id) == (before[0], {owner.id, other.id})


@pytest.mark.asyncio
async def test_owner_removal_persists(async_client, user_factory, db_session):
    owner, headers = await _login_user(async_client, user_factory)
    member, other = await user_factory(), await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Original", "participant_ids": [str(member.id), str(other.id)]},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["created_by"] == str(owner.id)
    chat_id = created.json()["id"]
    removed = await _operation(async_client, "remove", chat_id, headers, member.id)
    assert removed.status_code == 200
    assert await _snapshot(db_session, chat_id) == ("Original", {owner.id, other.id})
