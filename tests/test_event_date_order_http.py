"""Raw main-feed date ordering and direction-bound HTTP cursors."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import app.models as models
from app.auth.security import get_password_hash

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_audit017_http_order_case(async_client, db_session, user_factory):
    password = secrets.token_urlsafe(24) + "!Aa1"
    admin = await user_factory(role="admin")
    viewer = await user_factory(
        role="student",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    login = await async_client.post(
        "/auth/login",
        data={"username": viewer.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200
    token = login.cookies.get("access_token_v2")
    assert token
    headers = {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}
    event_type = f"audit017-{uuid.uuid4().hex}"
    base = datetime.now(UTC) + timedelta(days=120)
    id_seed = uuid.uuid4().int & ~0xFFFF
    ids = [uuid.UUID(int=id_seed + index) for index in range(1, 5)]
    starts = [
        base + timedelta(hours=1),
        base + timedelta(hours=2),
        base + timedelta(hours=2),
        base + timedelta(hours=3),
    ]
    # Insertion order is neither ASC nor DESC; two equal dates cross a page.
    for index in (3, 1, 0, 2):
        db_session.add(
            models.Event(
                id=ids[index],
                title=f"{event_type} {index}",
                description="AUD-017 HTTP ordering fixture",
                event_type=event_type,
                starts_at=starts[index],
                ends_at=starts[index] + timedelta(hours=1),
                created_by=admin.id,
                is_active=True,
            )
        )
    await db_session.commit()
    return headers, event_type, ids


async def test_events_http_date_order_has_stable_raw_pages_and_bound_cursors(
    async_client, db_session, user_factory
):
    headers, event_type, ids = await _seed_audit017_http_order_case(
        async_client, db_session, user_factory
    )
    base_params = {"type": event_type, "limit": 2}

    asc1 = await async_client.get("/events", params=base_params, headers=headers)
    assert asc1.status_code == 200
    asc1_data = asc1.json()
    assert [uuid.UUID(row["id"]) for row in asc1_data["items"]] == ids[:2]
    assert asc1_data["has_more"] is True
    assert asc1_data["next_cursor"]
    asc2 = await async_client.get(
        "/events",
        params={**base_params, "cursor": asc1_data["next_cursor"]},
        headers=headers,
    )
    assert asc2.status_code == 200
    asc2_data = asc2.json()
    assert [uuid.UUID(row["id"]) for row in asc2_data["items"]] == ids[2:]
    assert asc2_data["has_more"] is False
    assert asc2_data["next_cursor"] is None

    desc1 = await async_client.get(
        "/events",
        params={**base_params, "order": "starts_at_desc"},
        headers=headers,
    )
    assert desc1.status_code == 200
    desc1_data = desc1.json()
    assert [uuid.UUID(row["id"]) for row in desc1_data["items"]] == [ids[3], ids[2]]
    assert desc1_data["has_more"] is True
    assert desc1_data["next_cursor"]
    desc2 = await async_client.get(
        "/events",
        params={
            **base_params,
            "order": "starts_at_desc",
            "cursor": desc1_data["next_cursor"],
        },
        headers=headers,
    )
    assert desc2.status_code == 200
    desc2_data = desc2.json()
    assert [uuid.UUID(row["id"]) for row in desc2_data["items"]] == [ids[1], ids[0]]
    assert desc2_data["has_more"] is False
    assert desc2_data["next_cursor"] is None

    wrong_direction = await async_client.get(
        "/events",
        params={**base_params, "cursor": desc1_data["next_cursor"]},
        headers=headers,
    )
    assert wrong_direction.status_code == 400


async def test_events_http_legacy_cursor_cannot_be_reinterpreted_as_descending(
    async_client, db_session, user_factory
):
    headers, event_type, ids = await _seed_audit017_http_order_case(
        async_client, db_session, user_factory
    )
    base_params = {"type": event_type, "limit": 2}
    first = await async_client.get("/events", params=base_params, headers=headers)
    assert first.status_code == 200
    first_data = first.json()
    assert [uuid.UUID(row["id"]) for row in first_data["items"]] == ids[:2]
    assert first_data["next_cursor"]

    wrong_direction = await async_client.get(
        "/events",
        params={
            **base_params,
            "order": "starts_at_desc",
            "cursor": first_data["next_cursor"],
        },
        headers=headers,
    )
    assert wrong_direction.status_code == 400
