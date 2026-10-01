"""Single source of truth for "is this stored session still valid?".

REST (``app/api/deps/auth.py``), GraphQL
(``app/services/auth/graphql_token_validator.py``) and the Python WebSocket
fallback (``app/api/ws/auth.py``) each load the session through their own
transport-specific path, but they must all agree on the *policy* applied to it.
Before this module only REST enforced the MFA epoch, so a session minted before
an MFA change stayed valid on ``/graphql`` and ``/ws/chat``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class _SessionLike(Protocol):
    @property
    def user_id(self) -> object: ...
    @property
    def expires_at(self) -> datetime: ...
    @property
    def revoked_at(self) -> datetime | None: ...
    @property
    def mfa_epoch(self) -> int | None: ...


class _UserLike(Protocol):
    @property
    def id(self) -> object: ...
    @property
    def mfa_epoch(self) -> int | None: ...


def session_epoch_is_current(session: _SessionLike, user: _UserLike) -> bool:
    """A session minted before the user's last MFA change is no longer valid."""
    return int(session.mfa_epoch or 0) == int(user.mfa_epoch or 0)


def session_is_expired(session: _SessionLike, now: datetime | None = None) -> bool:
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= (now or datetime.now(UTC))


def session_is_usable(session: _SessionLike, user: _UserLike) -> bool:
    """Ownership, revocation, expiry and MFA-epoch checks in one place."""
    return (
        session.user_id == user.id
        and session.revoked_at is None
        and not session_is_expired(session)
        and session_epoch_is_current(session, user)
    )
