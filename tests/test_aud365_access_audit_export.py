"""AUD-365: enforce a bounded window on the real access-audit export route."""

import csv
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_admin_user_from_dishka
from app.api.users import users_router
from app.models.logs import DataAccessLog
from tests.conftest import build_dishka_app


@pytest_asyncio.fixture
async def audit_client(db_session):
    audit = MagicMock()
    app = build_dishka_app(
        users_router, AsyncDatabaseSession=db_session, AuditService=audit
    )
    app.dependency_overrides[get_current_admin_user_from_dishka] = lambda: (
        SimpleNamespace(id=uuid4())
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client, audit
    await app.state.dishka_container.close()


async def _add_rows(db_session, rows):
    db_session.add_all(
        [
            DataAccessLog(
                resource_type="test",
                resource_id=label,
                action="read",
                created_at=when,
            )
            for label, when in rows
        ]
    )
    await db_session.flush()


def _exported_ids(response):
    return {row["resource_id"] for row in csv.DictReader(io.StringIO(response.text))}


@pytest.mark.parametrize("missing", ["both", "end", "start"])
@pytest.mark.asyncio
async def test_missing_bounds_still_limit_export_to_31_days(
    missing, audit_client, db_session
):
    client, audit = audit_client
    now = datetime.now(UTC).replace(microsecond=0)
    if missing == "both":
        params = {}
        rows = [
            ("too_old", now - timedelta(days=32)),
            ("near_start", now - timedelta(days=30)),
            ("recent", now - timedelta(days=2)),
            ("future", now + timedelta(days=2)),
        ]
        expected = {"near_start", "recent"}
    elif missing == "end":
        start = now - timedelta(days=40)
        params = {"start_at": start.isoformat()}
        rows = [
            ("before", start - timedelta(seconds=1)),
            ("at_start", start),
            ("inside", start + timedelta(days=15)),
            ("at_end", start + timedelta(days=31)),
            ("after", start + timedelta(days=31, seconds=1)),
        ]
        expected = {"at_start", "inside", "at_end"}
    else:
        end = now - timedelta(days=40)
        params = {"end_at": end.isoformat()}
        rows = [
            ("before", end - timedelta(days=31, seconds=1)),
            ("at_start", end - timedelta(days=31)),
            ("inside", end - timedelta(days=15)),
            ("at_end", end),
            ("after", end + timedelta(seconds=1)),
        ]
        expected = {"at_start", "inside", "at_end"}
    await _add_rows(db_session, rows)

    response = await client.get("/users/audit/export", params=params)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "access_audit.csv" in response.headers["content-disposition"]
    assert _exported_ids(response) == expected
    audit.log.assert_called_once()


@pytest.mark.asyncio
async def test_explicit_boundary_and_oversized_range(audit_client, db_session):
    client, audit = audit_client
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=31)
    await _add_rows(
        db_session,
        [("at_start", start), ("at_end", end), ("after", end + timedelta(seconds=1))],
    )

    accepted = await client.get(
        "/users/audit/export",
        params={"start_at": start.isoformat(), "end_at": end.isoformat()},
    )
    rejected = await client.get(
        "/users/audit/export",
        params={
            "start_at": start.isoformat(),
            "end_at": (end + timedelta(microseconds=1)).isoformat(),
        },
    )

    assert accepted.status_code == 200
    assert _exported_ids(accepted) == {"at_start", "at_end"}
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["error"] == "date_range_too_large"
    audit.log.assert_called_once()


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-01-01T00:00:00", "2026-01-03T03:00:00+03:00"),
        ("2026-01-01T03:00:00+03:00", "2026-01-03T00:00:00"),
    ],
)
@pytest.mark.asyncio
async def test_mixed_naive_and_offset_dates_use_utc(
    start, end, audit_client, db_session
):
    client, _ = audit_client
    await _add_rows(
        db_session,
        [
            ("inside", datetime(2026, 1, 2, tzinfo=UTC)),
            ("after", datetime(2026, 1, 4, tzinfo=UTC)),
        ],
    )

    response = await client.get(
        "/users/audit/export",
        params={"start_at": start, "end_at": end},
    )

    assert response.status_code == 200
    assert _exported_ids(response) == {"inside"}


@pytest.mark.parametrize(
    "params",
    [
        {"start_at": "9999-12-31T23:59:59.999999Z"},
        {"end_at": "0001-01-01T00:00:00Z"},
        {"start_at": "0001-01-01T00:00:00+14:00", "end_at": "2026-01-01T00:00:00Z"},
    ],
)
@pytest.mark.asyncio
async def test_unrepresentable_window_is_rejected_without_a_server_error(
    params, audit_client
):
    client, audit = audit_client

    response = await client.get("/users/audit/export", params=params)

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_date_range"
    audit.log.assert_not_called()


@pytest.mark.asyncio
async def test_reversed_explicit_range_remains_an_empty_export(
    audit_client, db_session
):
    client, audit = audit_client
    await _add_rows(db_session, [("row", datetime(2026, 1, 2, tzinfo=UTC))])

    response = await client.get(
        "/users/audit/export",
        params={"start_at": "2026-01-03T00:00:00Z", "end_at": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 200
    assert _exported_ids(response) == set()
    audit.log.assert_called_once()


@pytest.mark.asyncio
async def test_malformed_date_still_returns_validation_error(audit_client):
    client, audit = audit_client

    response = await client.get(
        "/users/audit/export", params={"start_at": "not-a-date"}
    )

    assert response.status_code == 422
    audit.log.assert_not_called()


@pytest.mark.asyncio
async def test_unauthenticated_export_still_requires_admin(db_session):
    audit = MagicMock()
    app = build_dishka_app(
        users_router, AsyncDatabaseSession=db_session, AuditService=audit
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/users/audit/export")
    await app.state.dishka_container.close()

    assert response.status_code == 401
    audit.log.assert_not_called()
