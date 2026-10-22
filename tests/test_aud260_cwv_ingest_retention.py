from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.sql.dml import Delete

from app.api import cwv as cwv_api
from app.models.cwv import CwvObservation
from app.schemas.cwv import CwvObservationRequest
from app.services.cwv import CwvEnvelopeError, CwvTrustedObservation
from tests.conftest import call_injected


def _observation(*, created_at: datetime, observed_at: datetime) -> CwvObservation:
    return CwvObservation(
        metric="LCP",
        unit="ms",
        value=100.0,
        metric_id=uuid.uuid4().hex,
        collector_id=uuid.uuid4().hex,
        navigation_id=f"navigation-{uuid.uuid4().hex}",
        session_id=uuid.uuid4().hex,
        device_class="desktop",
        route_group="/home",
        observed_at=observed_at,
        sampling_bucket=observed_at.replace(minute=0, second=0, microsecond=0),
        release_sha="a" * 40,
        frontend_image_digest="sha256:" + "b" * 64,
        deployment_run_id=1,
        deployment_run_attempt=1,
        envelope_nonce=uuid.uuid4().hex,
        created_at=created_at,
    )


def _trusted_observation(now: datetime) -> CwvTrustedObservation:
    return CwvTrustedObservation(
        metric="LCP",
        unit="ms",
        value=120.0,
        metric_id=uuid.uuid4().hex,
        collector_id=uuid.uuid4().hex,
        navigation_id=f"navigation-{uuid.uuid4().hex}",
        session_id=uuid.uuid4().hex,
        device_class="desktop",
        route_group="/home",
        observed_at=now,
        release_sha="c" * 40,
        frontend_image_digest="sha256:" + "d" * 64,
        deployment_run_id=4,
        deployment_run_attempt=1,
        envelope_nonce=uuid.uuid4().hex,
    )


@pytest.mark.asyncio
async def test_ingest_prunes_one_ordered_batch_and_keeps_retention_boundary(
    db_session, monkeypatch
) -> None:
    now = datetime.now(UTC)
    retention_days = 3
    cutoff = now - timedelta(days=retention_days)
    expired_rows = [
        _observation(
            created_at=cutoff - timedelta(seconds=503 - index),
            observed_at=cutoff - timedelta(days=1),
        )
        for index in range(503)
    ]
    boundary_row = _observation(created_at=cutoff, observed_at=cutoff)
    db_session.add_all([*expired_rows, boundary_row])
    await db_session.flush()
    expired_ids = [row.id for row in expired_rows]
    boundary_id = boundary_row.id
    await db_session.commit()

    trusted = _trusted_observation(now)

    class _Clock:
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return now

    monkeypatch.setattr(cwv_api, "datetime", _Clock)
    monkeypatch.setattr(
        cwv_api, "settings", SimpleNamespace(cwv_retention_days=retention_days)
    )
    monkeypatch.setattr(cwv_api, "_manual_tester_principal", lambda _user: "tester")
    monkeypatch.setattr(cwv_api, "_binding", lambda: object())
    monkeypatch.setattr(cwv_api, "build_observation", lambda *args, **kwargs: trusted)

    delete_statements: list[Delete] = []
    execute = db_session.execute

    async def _record_execute(statement, *args, **kwargs):
        if isinstance(statement, Delete):
            delete_statements.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", _record_execute)
    request = SimpleNamespace(headers={"origin": "https://staging.example"})
    payload = CwvObservationRequest(envelope="e" * 32, metric="LCP", value=120.0)
    response = await call_injected(
        cwv_api.ingest_cwv_observation,
        payload,
        request,
        current_user=SimpleNamespace(id=uuid.uuid4()),
        provides={"AsyncDatabaseSession": db_session},
    )

    assert response.metric_id == trusted.metric_id
    assert len(delete_statements) == 1
    compiled = delete_statements[0].compile(dialect=db_session.get_bind().dialect)
    assert "LIMIT" in compiled.string.upper()
    assert 500 in compiled.params.values()

    remaining = (
        (
            await execute(
                select(CwvObservation).where(CwvObservation.id.in_(expired_ids))
            )
        )
        .scalars()
        .all()
    )
    remaining_ids = {row.id for row in remaining}
    # The oldest 500 rows are removed; the newest three expired rows remain for
    # the daily cleanup. A row exactly at the strict cutoff remains untouched.
    assert remaining_ids == set(expired_ids[-3:])
    boundary_result = await execute(
        select(CwvObservation.id).where(CwvObservation.id == boundary_id)
    )
    assert boundary_result.scalar_one_or_none() == boundary_id
    inserted_result = await execute(
        select(CwvObservation.id).where(CwvObservation.metric_id == trusted.metric_id)
    )
    assert inserted_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_rejected_observation_does_not_start_retention_cleanup(
    monkeypatch,
) -> None:
    db = AsyncMock()
    monkeypatch.setattr(cwv_api, "_manual_tester_principal", lambda _user: "tester")
    monkeypatch.setattr(cwv_api, "_binding", lambda: object())
    monkeypatch.setattr(
        cwv_api,
        "build_observation",
        lambda *args, **kwargs: (_ for _ in ()).throw(CwvEnvelopeError("invalid")),
    )
    with pytest.raises(HTTPException) as rejected:
        await call_injected(
            cwv_api.ingest_cwv_observation,
            CwvObservationRequest(envelope="e" * 32, metric="LCP", value=120.0),
            SimpleNamespace(headers={"origin": "https://staging.example"}),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            provides={"AsyncDatabaseSession": db},
        )

    assert rejected.value.status_code == 422
    db.execute.assert_not_awaited()
    db.add.assert_not_called()
