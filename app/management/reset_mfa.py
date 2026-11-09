"""Management command to reset MFA factors for a specific user."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth import mfa
from app.core.database import async_session
from app.core.localization import resolve_locale, translate
from app.core.logging import configure_logging, get_stdlib_logger
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.services.notifications import create_notifications_for_users

audit_logger = get_stdlib_logger("app.users.audit")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset all MFA methods for a specific user",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--user-id",
        type=UUID,
        help="Reset MFA for the user with the given UUID",
    )
    group.add_argument(
        "--email",
        type=str,
        help="Reset MFA for the user with the given email address",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip sending a notification to the affected user",
    )
    return parser


def _audit_cli(
    event: str, *, user_id: Any, reason: str, extra: dict[str, Any] | None = None
) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "user_id": str(user_id),
        "reason": reason,
        "source": "management",
    }
    if extra:
        payload.update(extra)
    audit_logger.info(json.dumps(payload, ensure_ascii=False))


async def _load_user(
    session: AsyncSession, *, user_id: Any | None, email: str | None
) -> models.User | None:
    if user_id is not None:
        return await session.get(models.User, user_id)
    if email is None:
        return None
    normalized_email = email.strip().lower()
    result = await session.execute(
        select(models.User).where(func.lower(models.User.email) == normalized_email)
    )
    return result.scalar_one_or_none()


@asynccontextmanager
async def _notification_tenant_scope(
    session: AsyncSession, tenant_id: UUID | None
) -> AsyncIterator[None]:
    """Bind notification ownership to its persisted recipient, not CLI ambient scope."""
    if not isinstance(tenant_id, UUID):
        raise ValueError("MFA notification requires a persisted tenant identity")
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError("Unsupported MFA notification database dialect")
    previous_database_tenant = ""
    if dialect == "postgresql":
        result = await session.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        )
        previous_database_tenant = result.scalar_one_or_none() or ""
    tenant_token = tenant_id_ctx.set(str(tenant_id))
    bypass_token = bypass_rls_ctx.set(False)
    try:
        try:
            if dialect == "postgresql":
                await session.execute(
                    text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                    {"tenant_id": str(tenant_id)},
                )
            yield
        finally:
            if dialect == "postgresql":
                pending_error = sys.exception()
                try:
                    await session.execute(
                        text(
                            "SELECT set_config('app.current_tenant', :tenant_id, true)"
                        ),
                        {"tenant_id": previous_database_tenant},
                    )
                except (SQLAlchemyError, OSError):
                    if pending_error is None:
                        raise
                    pending_error.add_note(
                        "Tenant context restoration failed; roll back the transaction"
                    )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


async def _reset_user_mfa(
    *,
    user_id: Any | None,
    email: str | None,
    notify: bool,
) -> tuple[models.User, mfa.MfaResetStats]:
    async with async_session() as session:
        user = await _load_user(session, user_id=user_id, email=email)
        if user is None:
            raise ValueError("User not found")
        try:
            stats = await mfa.reset_user_mfa(session, user=user)
            if notify and stats.changed:
                locale = resolve_locale(user=user)
                title = translate("notifications.mfa.reset.title", locale=locale)
                body = translate("notifications.mfa.reset.body", locale=locale)
                async with _notification_tenant_scope(session, user.tenant_id):
                    await create_notifications_for_users(
                        session,
                        title=title,
                        body=body,
                        type="security",
                        user_ids=[user.id],
                    )
            await mfa.publish_mfa_session_revocations(stats.session_revocations)
            await session.commit()
        except Exception:  # RZ-22-01-JUSTIFIED: transaction-boundary rollback
            await session.rollback()
            raise
        reason = "admin_reset" if stats.changed else "admin_reset_noop"
        _audit_cli(
            "users.mfa.reset",
            user_id=user.id,
            reason=reason,
            extra={
                "notify": "false" if not notify else "true",
                "totp_deleted": str(stats.totp_deleted),
                "challenges_revoked": str(stats.challenges_revoked),
            },
        )
        return user, stats


async def _async_main(args: argparse.Namespace) -> None:
    user, stats = await _reset_user_mfa(
        user_id=getattr(args, "user_id", None),
        email=getattr(args, "email", None),
        notify=not getattr(args, "no_notify", False),
    )
    print(
        "MFA reset completed for user",
        user.id,
        {
            "totp_deleted": stats.totp_deleted,
            "challenges_revoked": stats.challenges_revoked,
            "fields_cleared": stats.fields_cleared,
        },
    )


def main() -> None:
    # Management commands bypass the ASGI bootstrap.  Use the central bridge
    # so audit payloads receive the same PII redaction and structured renderer.
    configure_logging()
    parser = _build_arg_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_async_main(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
