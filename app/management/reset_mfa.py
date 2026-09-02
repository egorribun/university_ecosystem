"""Management command to reset MFA factors for a specific user."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth import mfa
from app.core.database import async_session
from app.core.localization import resolve_locale, translate
from app.services.notifications import create_notifications_for_users

audit_logger = logging.getLogger("app.users.audit")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset all MFA methods for a specific user",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--user-id",
        type=int,
        help="Reset MFA for the user with the given numeric ID",
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
                await create_notifications_for_users(
                    session,
                    title=title,
                    body=body,
                    type="security",
                    user_ids=[user.id],
                )
            await session.commit()
        except Exception:  # RZ-28-01-JUSTIFIED: transaction-boundary rollback
            await session.rollback()
            raise
        await mfa.publish_mfa_session_revocations(stats.session_revocations)
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
    logging.basicConfig(level=logging.INFO)
    parser = _build_arg_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_async_main(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
