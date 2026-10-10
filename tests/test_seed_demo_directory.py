from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.database import async_session
from app.core.di_provider import create_dishka_container
from app.models import DataAccessLog, Group
from scripts import seed_demo_data


@pytest.mark.asyncio
async def test_seeded_peers_are_readable_by_admin_directory_with_fresh_sessions(
    root_client, app, user_factory, db_session
):
    password = (
        "DirectoryProbe123!"  # pragma: allowlist secret -- synthetic login fixture
    )
    admin = await user_factory(
        role="admin",
        email="directory-admin@example.com",
        email_verified_at=datetime.now(UTC),
        hashed_password=await get_password_hash(password),
    )
    group = await seed_demo_data.seed_group(db_session)
    peer = await seed_demo_data.seed_demo_peer_user(db_session, group)
    second_peer = await seed_demo_data.seed_demo_second_peer_user(db_session, group)
    await db_session.commit()
    expected_peer_ids = {str(peer.id), str(second_peer.id)}
    previous_container = app.state.dishka_container
    production_container = create_dishka_container()
    app.state.dishka_container = production_container
    try:
        login = await root_client.post(
            "/api/v1/auth/login",
            data={"username": admin.email, "password": password},
        )
        assert login.status_code == 200
        response = await root_client.get(
            "/api/v1/users", headers={"X-Query-Budget": "40"}
        )
        assert response.status_code == 200
        peer_records = [
            item for item in response.json() if item["id"] in expected_peer_ids
        ]
        assert {item["email"] for item in peer_records} == {
            "demo.peer@example.com",
            "demo.peer.two@example.com",
        }
        async with async_session() as verification:
            audit_rows = (
                await verification.scalars(
                    select(DataAccessLog).where(
                        DataAccessLog.actor_user_id == admin.id,
                        DataAccessLog.subject_user_id.in_([peer.id, second_peer.id]),
                    )
                )
            ).all()
            assert len(audit_rows) == 2
            assert all(
                re.fullmatch(r"v2:[0-9a-f]{64}", row.signature or "")
                for row in audit_rows
            )
    finally:
        app.state.dishka_container = previous_container
        await production_container.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("seed_function", "seed_key", "legacy_email", "expected_email"),
    [
        (
            "seed_demo_peer_user",
            seed_demo_data.DEMO_PEER_USER_SEED_KEY,
            "demo.peer@example.test",
            "demo.peer@example.com",
        ),
        (
            "seed_demo_second_peer_user",
            seed_demo_data.DEMO_SECOND_PEER_USER_SEED_KEY,
            "demo.peer.two@example.test",
            "demo.peer.two@example.com",
        ),
    ],
)
async def test_legacy_owned_peer_email_is_reconciled_without_changing_identity(
    db_session, user_factory, seed_function, seed_key, legacy_email, expected_email
):
    custom_group = Group(name="User-selected cohort")
    db_session.add(custom_group)
    await db_session.flush()
    peer = await user_factory(
        email=legacy_email,
        demo_seed_key=seed_key,
        about="Keep edited profile",
        group_id=custom_group.id,
    )
    peer_id, original_hash = peer.id, peer.hashed_password
    group = await seed_demo_data.seed_group(db_session)
    seed_peer = getattr(seed_demo_data, seed_function)

    repaired = await seed_peer(db_session, group)
    await db_session.commit()
    repeated = await seed_peer(db_session, group)

    assert repaired.id == repeated.id == peer_id
    assert repaired.email == expected_email
    assert repaired.hashed_password == original_hash
    assert repaired.profile.about == "Keep edited profile"
    assert repaired.group_id == custom_group.id != group.id
    assert repaired.demo_seed_key == seed_key


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["canonical_email", "legacy_role", "legacy_email"])
async def test_legacy_peer_reconciliation_refuses_unproven_ownership(
    db_session, user_factory, conflict
):
    peer = await user_factory(
        email=(
            "unrelated@example.test"
            if conflict == "legacy_email"
            else "demo.peer@example.test"
        ),
        role="teacher" if conflict == "legacy_role" else "student",
        demo_seed_key=seed_demo_data.DEMO_PEER_USER_SEED_KEY,
    )
    if conflict == "canonical_email":
        await user_factory(email="demo.peer@example.com")
    original_email, original_hash = peer.email, peer.hashed_password
    group = await seed_demo_data.seed_group(db_session)

    with pytest.raises(RuntimeError, match=r"reserved demo peer .* is occupied"):
        await seed_demo_data.seed_demo_peer_user(db_session, group)

    assert peer.email == original_email
    assert peer.hashed_password == original_hash


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email", ["demo.peer@example.test", "peer@university.dev", "peer@example.com.evil"]
)
async def test_synthetic_peer_rejects_other_domains_before_database_access(email):
    with pytest.raises(RuntimeError, match=r"must use the example\.com domain"):
        await seed_demo_data._seed_demo_peer_user(
            None,
            None,
            email=email,
            seed_key=seed_demo_data.DEMO_PEER_USER_SEED_KEY,
            legacy_email="demo.peer@example.test",
            full_name="Synthetic peer",
        )
