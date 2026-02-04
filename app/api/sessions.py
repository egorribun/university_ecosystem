from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fresh_mfa
from app.api.validation import ensure_exists, require_admin, require_owner_or_admin
from app.auth.security import decode_token
from app.core.database import get_db, get_read_db
from app.core.localization import resolve_locale
from app.models.models import ActiveSession, User
from app.schemas import schemas
from app.services.session_cleanup import revoke_sessions_matching

router = APIRouter(prefix="/auth/sessions", tags=["auth"])


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header:
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
            if token:
                return token
    cookie_token = request.cookies.get("access_token_v2")
    if cookie_token:
        return cookie_token
    return None


def _extract_jti(request: Request) -> str | None:
    raw_token = _extract_token(request)
    if not raw_token:
        return None
    payload = decode_token(raw_token)
    if not payload:
        return None
    jti = payload.get("jti")
    if isinstance(jti, str) and jti:
        return jti
    return None


async def _resolve_target_user(
    *,
    db: AsyncSession,
    current_user: User,
    requested_user_id: uuid.UUID | None,
    locale: str,
) -> tuple[uuid.UUID, User]:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user.id, current_user
    require_admin(current_user, locale)
    target = await db.get(User, requested_user_id)
    ensure_exists(target, "users", locale)
    return target.id, target


@router.get("", response_model=list[schemas.ActiveSessionOut])
async def list_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_read_db)],
    user_id: uuid.UUID | None = None,
) -> list[schemas.ActiveSessionOut]:
    locale = resolve_locale(request=request, user=current_user)
    target_user_id, _ = await _resolve_target_user(
        db=db,
        current_user=current_user,
        requested_user_id=user_id,
        locale=locale,
    )
    result = await db.execute(
        select(ActiveSession)
        .where(ActiveSession.user_id == target_user_id)
        .where(ActiveSession.revoked_at.is_(None))
        .order_by(ActiveSession.created_at.desc())
    )
    sessions = result.scalars().all()
    current_jti = _extract_jti(request)
    payload: list[schemas.ActiveSessionOut] = []
    for session in sessions:
        model = schemas.ActiveSessionOut.model_validate(session)
        model = model.model_copy(update={"is_current": session.jti == current_jti})
        payload.append(model)
    return payload


@router.delete("/{session_id}", response_model=schemas.ActiveSessionOut)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    _: Annotated[None, Depends(require_fresh_mfa)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> schemas.ActiveSessionOut:
    locale = resolve_locale(request=request, user=current_user)
    session = await db.get(ActiveSession, session_id)
    ensure_exists(session, "sessions", locale)
    require_owner_or_admin(current_user, locale, owner_id=session.user_id)
    now = datetime.now(UTC)
    revoked_at = session.revoked_at or now
    session.revoked_at = revoked_at
    session.signing_key = secrets.token_urlsafe(32)
    current_jti = _extract_jti(request)
    payload = schemas.ActiveSessionOut.model_validate(session).model_copy(
        update={"is_current": session.jti == current_jti, "revoked_at": revoked_at}
    )
    await db.commit()
    await db.refresh(session)
    return payload


@router.post("/revoke-others", response_model=schemas.SessionBulkRevokeOut)
async def revoke_other_sessions(
    request: Request,
    _: Annotated[None, Depends(require_fresh_mfa)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID | None = None,
) -> schemas.SessionBulkRevokeOut:
    locale = resolve_locale(request=request, user=current_user)
    target_user_id, _ = await _resolve_target_user(
        db=db,
        current_user=current_user,
        requested_user_id=user_id,
        locale=locale,
    )
    current_jti = _extract_jti(request)
    where_parts = [
        ActiveSession.user_id == target_user_id,
        ActiveSession.revoked_at.is_(None),
    ]
    if current_jti:
        where_parts.append(ActiveSession.jti != current_jti)
    revoked = await revoke_sessions_matching(db=db, whereclause=and_(*where_parts))
    await db.commit()
    return schemas.SessionBulkRevokeOut(revoked=revoked)
