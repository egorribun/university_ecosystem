"""Branch closure tests for AuthFingerprintService orchestration."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.fingerprint import SessionFingerprint
from app.services.auth.fingerprint_service import AuthFingerprintService


def _context(fingerprint_hash: str):
    request = MagicMock()
    user = SimpleNamespace(id="user-id")
    session = SimpleNamespace(
        id="session-id",
        jti="jti",
        fingerprint_hash=fingerprint_hash,
        user_agent="UA",
        accept_language="en",
        ip_address="127.0.0.1",
        revoked_at=None,
    )
    db = MagicMock()
    db.commit = AsyncMock()
    return AuthFingerprintService(request, "en"), user, session, db


def _fingerprint(value: str) -> SessionFingerprint:
    return SessionFingerprint(
        user_agent="UA",
        accept_language="en",
        ip_address="127.0.0.1",
        fingerprint_hash=value,
    )


@pytest.mark.asyncio
async def test_validate_fingerprint_returns_when_session_has_no_hash():
    service, user, session, db = _context("")

    await service.validate_fingerprint(user, session, db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_fingerprint_ignores_matching_hash():
    service, user, session, db = _context("same")
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("same"),
        ) as extract,
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector"
        ) as detector,
    ):
        await service.validate_fingerprint(user, session, db)

    extract.assert_called_once_with(service.request)
    detector.assert_not_called()


@pytest.mark.asyncio
async def test_validate_fingerprint_ignores_mismatch_without_detector_event():
    service, user, session, db = _context("stored")
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = None
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
    ):
        await service.validate_fingerprint(user, session, db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_fingerprint_skips_revocation_in_development():
    service, user, session, db = _context("stored")
    event = SimpleNamespace(to_log_record=lambda: {})
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = event
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "development"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden") as forbidden,
    ):
        await service.validate_fingerprint(user, session, db)

    db.commit.assert_not_awaited()
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_validate_fingerprint_revokes_in_production_without_redis():
    service, user, session, db = _context("stored")
    event = SimpleNamespace(to_log_record=lambda: {})
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = event
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden") as forbidden,
    ):
        await service.validate_fingerprint(user, session, db)

    assert session.revoked_at is not None
    db.commit.assert_awaited_once()
    forbidden.assert_called_once()


@pytest.mark.asyncio
async def test_validate_fingerprint_revokes_and_notifies_redis():
    service, user, session, db = _context("stored")
    event = SimpleNamespace(to_log_record=lambda: {})
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = event
    redis = MagicMock()
    redis.revoke_session = AsyncMock()
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden"),
    ):
        await service.validate_fingerprint(user, session, db, redis)

    redis.revoke_session.assert_awaited_once_with("jti")


@pytest.mark.asyncio
async def test_validate_fingerprint_tolerates_redis_failure():
    service, user, session, db = _context("stored")
    event = SimpleNamespace(to_log_record=lambda: {})
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = event
    redis = MagicMock()
    redis.revoke_session = AsyncMock(side_effect=ConnectionError("offline"))
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden"),
    ):
        await service.validate_fingerprint(user, session, db, redis)

    db.commit.assert_awaited_once()
