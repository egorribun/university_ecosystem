from __future__ import annotations

import uuid
from typing import Annotated

from dishka import FromComponent, FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Request, status

from app.api.deps import (
    get_current_user_from_dishka,
    require_fresh_mfa,
)
from app.api.deps.auth import ensure_admin, get_permission_checker
from app.api.validation import raise_http_error
from app.auth.rbac import PermissionChecker
from app.auth.security import decode_token
from app.core.di.read_replica import READ_COMPONENT
from app.core.localization import resolve_locale
from app.core.protocols import AsyncDatabaseSession
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.schemas.dtos import UserDTO
from app.services.session_service import SessionService

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
    user_repo: UserRepository,
    current_user: User | UserDTO,
    requested_user_id: uuid.UUID | None,
    checker: PermissionChecker,
    request: Request,
    locale: str,
) -> tuple[uuid.UUID, User | UserDTO]:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user.id, current_user
    await ensure_admin(checker, current_user, request)
    target = await user_repo.get(requested_user_id)
    if target is None:
        raise_http_error(
            status.HTTP_404_NOT_FOUND, "errors.auth.user_not_found", locale
        )
    # MED-W19: ensure_exists removed — unreachable after raise_http_error above.
    return target.id, target


@router.get("", response_model=list[schemas.ActiveSessionOut])
@inject
async def list_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_from_dishka)],
    checker: Annotated[PermissionChecker, Depends(get_permission_checker)],
    db: Annotated[AsyncDatabaseSession, FromComponent(READ_COMPONENT)],
    session_service: FromDishka[SessionService],
    user_id: uuid.UUID | None = None,
) -> list[schemas.ActiveSessionOut]:
    locale = resolve_locale(request=request, user=current_user)
    user_repo = UserRepository(db)
    target_user_id, _ = await _resolve_target_user(
        user_repo=user_repo,
        current_user=current_user,
        requested_user_id=user_id,
        checker=checker,
        request=request,
        locale=locale,
    )
    sessions = await session_service.get_active_sessions_for_user(target_user_id)
    current_jti = _extract_jti(request)
    payload: list[schemas.ActiveSessionOut] = []
    for session in sessions:
        model = schemas.ActiveSessionOut.model_validate(session)
        model = model.model_copy(update={"is_current": session.jti == current_jti})
        payload.append(model)
    return payload


@router.delete("/{session_id}", response_model=schemas.ActiveSessionOut)
@inject
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    session_service: FromDishka[SessionService],
    mfa_check: None = Depends(require_fresh_mfa),
    current_user: User = Depends(get_current_user_from_dishka),
    checker: PermissionChecker = Depends(get_permission_checker),
) -> schemas.ActiveSessionOut:
    locale = resolve_locale(request=request, user=current_user)
    session = await session_service.get_session_by_id(session_id)
    if session is None:
        raise_http_error(
            status.HTTP_404_NOT_FOUND, "errors.auth.session_not_found", locale
        )
    # MED-W19: ensure_exists removed — unreachable after raise_http_error above.
    if session.user_id != current_user.id:
        await ensure_admin(checker, current_user, request)

    revoked_session = await session_service.revoke_session_by_id(session_id)
    # LOW-W19: removed dead `raise ValueError("Unreachable")` — revoke_session_by_id
    # always returns a session at this point (session existence is verified above).
    if revoked_session is None:
        raise_http_error(
            status.HTTP_404_NOT_FOUND, "errors.auth.session_not_found", locale
        )

    current_jti = _extract_jti(request)
    payload = schemas.ActiveSessionOut.model_validate(revoked_session).model_copy(
        update={"is_current": revoked_session.jti == current_jti}
    )
    return payload


@router.post("/revoke-others", response_model=schemas.SessionBulkRevokeOut)
@inject
async def revoke_other_sessions(
    request: Request,
    db: FromDishka[AsyncDatabaseSession],
    session_service: FromDishka[SessionService],
    mfa_check: None = Depends(require_fresh_mfa),
    current_user: User = Depends(get_current_user_from_dishka),
    checker: PermissionChecker = Depends(get_permission_checker),
    user_id: uuid.UUID | None = None,
) -> schemas.SessionBulkRevokeOut:
    locale = resolve_locale(request=request, user=current_user)
    user_repo = UserRepository(db)
    target_user_id, _ = await _resolve_target_user(
        user_repo=user_repo,
        current_user=current_user,
        requested_user_id=user_id,
        checker=checker,
        request=request,
        locale=locale,
    )
    current_jti = _extract_jti(request)
    revoked = await session_service.revoke_other_sessions(target_user_id, current_jti)
    return schemas.SessionBulkRevokeOut(revoked=revoked)
