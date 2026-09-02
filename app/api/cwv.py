"""Trusted staging RUM ingestion and OIDC-only immutable evidence export."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.ratelimit import sensitive_route_limit
from app.models.cwv import CwvObservation
from app.models.users import User
from app.schemas.cwv import (
    CwvEnvelopeRequest,
    CwvEnvelopeResponse,
    CwvObservationAccepted,
    CwvObservationRequest,
)
from app.services.cwv import (
    CwvConfigurationError,
    CwvEnvelopeError,
    CwvOriginError,
    CwvRumBinding,
    GithubActionsOidcVerifier,
    build_observation,
    issue_envelope,
    renew_envelope,
)

router = APIRouter(prefix="/cwv", tags=["field-performance"])


def _binding() -> CwvRumBinding:
    return CwvRumBinding(
        enabled=settings.cwv_rum_enabled,
        signing_secret=settings.cwv_rum_signing_secret.get_secret_value(),
        release_sha=settings.cwv_release_sha,
        frontend_image_digest=settings.cwv_frontend_image_digest,
        deployment_run_id=settings.cwv_deployment_run_id,
        deployment_run_attempt=settings.cwv_deployment_run_attempt,
        deployment_url=settings.cwv_deployment_url,
        allowed_origins=tuple(
            item.strip()
            for item in settings.cwv_allowed_origins.split(",")
            if item.strip()
        ),
        envelope_ttl_seconds=settings.cwv_envelope_ttl_seconds,
    )


def _manual_tester_principal(current_user: User) -> str:
    eligible = {
        item.strip()
        for item in settings.cwv_manual_tester_user_ids.get_secret_value().split(",")
        if item.strip()
    }
    principal = str(current_user.id)
    if principal not in eligible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CWV request rejected",
        )
    return principal


def _raise_contract_error(exc: ValueError) -> None:
    if isinstance(exc, CwvConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CWV collection unavailable",
        ) from exc
    if isinstance(exc, CwvOriginError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CWV request rejected"
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid CWV evidence"
    ) from exc


@router.post(
    "/envelope",
    response_model=CwvEnvelopeResponse,
    dependencies=[Depends(sensitive_route_limit(limit=5, window_sec=60))],
)
async def create_cwv_envelope(
    payload: CwvEnvelopeRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CwvEnvelopeResponse:
    collector_principal_id = _manual_tester_principal(current_user)
    try:
        if payload.renewal_envelope is None:
            envelope, expires_at = issue_envelope(
                _binding(),
                origin=request.headers.get("origin"),
                pathname=payload.pathname,
                device_class=payload.device_class,
                collector_principal_id=collector_principal_id,
                gateway_session_id=request.headers.get("x-session-id", ""),
            )
        else:
            envelope, expires_at = renew_envelope(
                _binding(),
                token=payload.renewal_envelope,
                origin=request.headers.get("origin"),
                pathname=payload.pathname,
                device_class=payload.device_class,
                collector_principal_id=collector_principal_id,
                gateway_session_id=request.headers.get("x-session-id", ""),
            )
    except (CwvConfigurationError, CwvOriginError, CwvEnvelopeError) as exc:
        _raise_contract_error(exc)
    return CwvEnvelopeResponse(envelope=envelope, expires_at=expires_at)


@router.post(
    "/observations",
    response_model=CwvObservationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(sensitive_route_limit(limit=15, window_sec=60))],
)
async def ingest_cwv_observation(
    payload: CwvObservationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CwvObservationAccepted:
    collector_principal_id = _manual_tester_principal(current_user)
    try:
        trusted = build_observation(
            _binding(),
            token=payload.envelope,
            origin=request.headers.get("origin"),
            collector_principal_id=collector_principal_id,
            gateway_session_id=request.headers.get("x-session-id", ""),
            metric=payload.metric,
            value=payload.value,
        )
    except (CwvConfigurationError, CwvOriginError, CwvEnvelopeError) as exc:
        _raise_contract_error(exc)
    stored = asdict(trusted)
    stored.pop("automated")
    stored.pop("final")
    stored["sampling_bucket"] = trusted.observed_at.replace(
        minute=0, second=0, microsecond=0
    )
    await db.execute(
        delete(CwvObservation).where(
            CwvObservation.created_at
            < datetime.now(UTC) - timedelta(days=settings.cwv_retention_days)
        )
    )
    db.add(CwvObservation(**stored))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CWV observation already accepted",
        ) from exc
    return CwvObservationAccepted(metric_id=trusted.metric_id)


def _bearer(authorization: str | None) -> str:
    if not authorization or len(authorization) > 8192:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Exporter authentication required",
        )
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Exporter authentication required",
        )
    return token


@router.get(
    "/export",
    include_in_schema=False,
    dependencies=[
        Depends(sensitive_route_limit(limit=10, window_sec=60, key_prefix="cwv-export"))
    ],
)
async def export_cwv_report(
    release_sha: str,
    frontend_image_digest: str,
    deployment_run_id: int,
    deployment_run_attempt: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    binding = _binding()
    if (
        release_sha != binding.release_sha
        or frontend_image_digest != binding.frontend_image_digest
        or deployment_run_id != binding.deployment_run_id
        or deployment_run_attempt != binding.deployment_run_attempt
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CWV evidence not found"
        )
    verifier = GithubActionsOidcVerifier(
        enabled=settings.cwv_export_oidc_enabled,
        repository=settings.cwv_export_oidc_repository,
        workflow_ref=settings.cwv_export_oidc_workflow_ref,
        subject=settings.cwv_export_oidc_subject,
    )
    try:
        await asyncio.to_thread(
            verifier.verify, _bearer(authorization), expected_sha=release_sha
        )
    except CwvConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CWV exporter unavailable",
        ) from exc
    except CwvEnvelopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid exporter identity"
        ) from exc
    deployed_at = settings.cwv_deployed_at
    if deployed_at is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CWV exporter unavailable",
        )
    generated_at = datetime.now(UTC)
    window_floor = max(
        deployed_at.astimezone(UTC),
        generated_at - timedelta(hours=72),
    )
    rows = (
        (
            await db.execute(
                select(CwvObservation)
                .where(
                    CwvObservation.release_sha == release_sha,
                    CwvObservation.frontend_image_digest == frontend_image_digest,
                    CwvObservation.deployment_run_id == deployment_run_id,
                    CwvObservation.deployment_run_attempt == deployment_run_attempt,
                    CwvObservation.observed_at >= window_floor,
                    CwvObservation.observed_at <= generated_at,
                )
                .order_by(CwvObservation.observed_at, CwvObservation.metric_id)
                .limit(100_001)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CWV evidence not found"
        )
    if len(rows) > 100_000:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CWV evidence exceeds bounded export capacity",
        )
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "release_sha": release_sha,
        "frontend_image_digest": frontend_image_digest,
        "environment": "staging",
        "deployment": {
            "workflow_run_id": deployment_run_id,
            "workflow_run_attempt": deployment_run_attempt,
            "deployed_at": deployed_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "deployment_url": binding.deployment_url,
        },
        "collector": {
            "kind": "web-vitals-rum",
            "library": "web-vitals",
            "library_version": "6.1.1",
            "exporter_version": "1",
            "eligibility": "operator-curated-manual-testers",
            "sampling": "one-final-metric-per-collector-route-hour",
            "maximum_collectors": 50,
        },
        "window": {
            "start": min(row.observed_at for row in rows)
            .isoformat()
            .replace("+00:00", "Z"),
            "end": max(row.observed_at for row in rows)
            .isoformat()
            .replace("+00:00", "Z"),
        },
        "observations": [
            {
                "metric": row.metric,
                "unit": row.unit,
                "value": row.value,
                "metric_id": row.metric_id,
                "collector_id": row.collector_id,
                "navigation_id": row.navigation_id,
                "session_id": row.session_id,
                "device_class": row.device_class,
                "route_group": row.route_group,
                "observed_at": row.observed_at.isoformat().replace("+00:00", "Z"),
                "release_sha": row.release_sha,
                "frontend_image_digest": row.frontend_image_digest,
                "automated": False,
                "final": True,
            }
            for row in rows
        ],
    }
