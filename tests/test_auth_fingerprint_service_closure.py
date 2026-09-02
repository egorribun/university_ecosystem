"""Branch closure tests for AuthFingerprintService orchestration."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.fingerprint import SessionFingerprint, _compute_fingerprint_hash
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
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db = MagicMock()
    db.commit = AsyncMock()
    return AuthFingerprintService(request, "en"), user, session, db


def _fingerprint(value: str, *, user_agent: str = "UA") -> SessionFingerprint:
    return SessionFingerprint(
        user_agent=user_agent,
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
async def test_validate_fingerprint_accepts_matching_hash_without_stored_user_agent():
    service, user, session, db = _context("same")
    session.user_agent = ""
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("same", user_agent="new-agent"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector"
        ) as detector,
    ):
        await service.validate_fingerprint(user, session, db)

    detector.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_fingerprint_accepts_legacy_language_variant_hash():
    legacy_hash = _compute_fingerprint_hash("UA", "en-US,en;q=0.9", "127.0.0.1")
    normalized_hash = _compute_fingerprint_hash("UA", "en", "127.0.0.1")
    service, user, session, db = _context(legacy_hash)
    session.accept_language = "en-US,en;q=0.9"
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint(normalized_hash),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector"
        ) as detector,
    ):
        await service.validate_fingerprint(user, session, db)

    detector.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_fingerprint_does_not_revoke_for_language_only_change():
    service, user, session, db = _context(
        _compute_fingerprint_hash("UA", "", "127.0.0.1")
    )
    session.accept_language = ""
    current_hash = _compute_fingerprint_hash("UA", "ru", "127.0.0.1")
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=SessionFingerprint(
                user_agent="UA",
                accept_language="ru",
                ip_address="127.0.0.1",
                fingerprint_hash=current_hash,
            ),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector"
        ) as detector,
    ):
        await service.validate_fingerprint(user, session, db)

    detector.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_fingerprint_ignores_mismatch_without_detector_event():
    service, user, session, db = _context("stored")
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = None
    with (
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current", user_agent="UA2"),
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
            return_value=_fingerprint("current", user_agent="UA2"),
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
            return_value=_fingerprint("current", user_agent="UA2"),
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
    order: list[str] = []

    async def _commit() -> None:
        order.append("database")

    async def _revoke(*_args, **_kwargs) -> None:
        order.append("redis")

    db.commit.side_effect = _commit
    redis = MagicMock()
    redis.revoke_session = AsyncMock(side_effect=_revoke)
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current", user_agent="UA2"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden"),
    ):
        await service.validate_fingerprint(user, session, db, redis)

    redis.revoke_session.assert_awaited_once_with("jti", expires_at=session.expires_at)
    assert order == ["redis", "database"]


@pytest.mark.asyncio
async def test_validate_fingerprint_propagates_redis_failure():
    service, user, session, db = _context("stored")
    event = SimpleNamespace(to_log_record=lambda: {})
    detector = MagicMock()
    detector.check_fingerprint_mismatch.return_value = event
    redis = MagicMock()
    redis.revoke_session = AsyncMock(side_effect=ConnectionError("offline"))
    db.rollback = AsyncMock()
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=_fingerprint("current", user_agent="UA2"),
        ),
        patch(
            "app.services.auth.fingerprint_service.get_suspicious_activity_detector",
            return_value=detector,
        ),
        patch("app.services.auth.fingerprint_service.raise_forbidden"),
    ):
        with pytest.raises(ConnectionError, match="offline"):
            await service.validate_fingerprint(user, session, db, redis)

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
