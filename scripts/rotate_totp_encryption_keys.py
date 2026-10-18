#!/usr/bin/env python3
"""Rotate stored MFA TOTP enrollment ciphertext to the active TOTP key.

The default mode is read-only. Use ``--apply`` only after the new key is
provisioned in the explicit TOTP key ring and legacy decrypt keys are retained.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.utils.encryption import (
    TotpEncryptionError,
    reset_cached_cipher,
    rotate_totp_encrypted_string,
)

_BATCH_SIZE_LIMIT = 500
_FIRST_BATCH_SQL = text(
    "SELECT id, secret FROM mfa_totp_enrollments ORDER BY id LIMIT :batch_size"
)
_NEXT_BATCH_SQL = text(
    "SELECT id, secret FROM mfa_totp_enrollments WHERE id > :last_id "
    "ORDER BY id LIMIT :batch_size"
)
_FIRST_BATCH_FOR_UPDATE_SQL = text(
    "SELECT id, secret FROM mfa_totp_enrollments ORDER BY id "
    "LIMIT :batch_size FOR UPDATE"
)
_NEXT_BATCH_FOR_UPDATE_SQL = text(
    "SELECT id, secret FROM mfa_totp_enrollments WHERE id > :last_id "
    "ORDER BY id LIMIT :batch_size FOR UPDATE"
)
_UPDATE_SQL = text(
    "UPDATE mfa_totp_enrollments SET secret = :new_secret "
    "WHERE id = :row_id AND secret = :old_secret RETURNING id"
)


class TotpRotationConflict(RuntimeError):
    """Raised when a row changes before its compare-and-swap update."""


@dataclass(frozen=True, slots=True)
class RotationSummary:
    scanned: int = 0
    would_rotate: int = 0
    rotated: int = 0
    already_active: int = 0


async def rotate_totp_enrollments(
    session_factory: Callable[[], AsyncSession],
    *,
    dry_run: bool = True,
    batch_size: int = 100,
) -> RotationSummary:
    """Inspect or rotate rows in bounded batches with per-batch transactions."""
    if type(batch_size) is not int or not 1 <= batch_size <= _BATCH_SIZE_LIMIT:
        raise ValueError(f"batch_size must be between 1 and {_BATCH_SIZE_LIMIT}")
    if (
        not settings.mfa_totp_encryption_keys.strip()
        or not settings.mfa_totp_active_encryption_key_id.strip()
    ):
        raise TotpEncryptionError(
            "Explicit MFA_TOTP_ENCRYPTION_KEYS and active key ID are required"
        )

    reset_cached_cipher()
    cursor_id: Any = None
    scanned = 0
    would_rotate = 0
    rotated_count = 0
    already_active = 0

    while True:
        async with session_factory() as session:
            async with session.begin():
                is_postgres = session.get_bind().dialect.name == "postgresql"
                if cursor_id is None:
                    statement = (
                        _FIRST_BATCH_FOR_UPDATE_SQL
                        if is_postgres and not dry_run
                        else _FIRST_BATCH_SQL
                    )
                    parameters = {"batch_size": batch_size}
                else:
                    statement = (
                        _NEXT_BATCH_FOR_UPDATE_SQL
                        if is_postgres and not dry_run
                        else _NEXT_BATCH_SQL
                    )
                    parameters = {"last_id": cursor_id, "batch_size": batch_size}
                result = await session.execute(statement, parameters)
                rows = result.mappings().all()
                if not rows:
                    break

                for row in rows:
                    scanned += 1
                    old_secret = row["secret"]
                    try:
                        new_secret = rotate_totp_encrypted_string(old_secret)
                    except TotpEncryptionError:
                        raise TotpEncryptionError(
                            "An enrollment cannot be decrypted with the configured "
                            "TOTP key ring"
                        ) from None
                    if new_secret == old_secret:
                        already_active += 1
                        continue
                    if dry_run:
                        would_rotate += 1
                        continue
                    updated_row_id = await session.scalar(
                        _UPDATE_SQL,
                        {
                            "row_id": row["id"],
                            "old_secret": old_secret,
                            "new_secret": new_secret,
                        },
                    )
                    if updated_row_id is None:
                        raise TotpRotationConflict(
                            "An enrollment changed during rotation; the current "
                            "batch was rolled back"
                        )
                    rotated_count += 1
                cursor_id = rows[-1]["id"]

        if len(rows) < batch_size:
            break

    return RotationSummary(
        scanned=scanned,
        would_rotate=would_rotate,
        rotated=rotated_count,
        already_active=already_active,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="persist re-encrypted enrollment rows (default: read-only dry run)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help=f"rows per transaction, from 1 to {_BATCH_SIZE_LIMIT} (default: 100)",
    )
    return parser


async def _run_cli(args: argparse.Namespace) -> int:
    try:
        summary = await rotate_totp_enrollments(
            async_session,
            dry_run=not args.apply,
            batch_size=args.batch_size,
        )
    except TotpEncryptionError:
        print(
            "TOTP rotation stopped: configured keys cannot safely read every "
            "enrollment.",
            file=sys.stderr,
        )
        return 1
    except (SQLAlchemyError, TotpRotationConflict, ValueError):
        print(
            "TOTP rotation failed; the current batch was rolled back.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "TOTP rotation failed; no secret values were included in the error output.",
            file=sys.stderr,
        )
        return 1

    if args.apply:
        print(
            "TOTP rotation complete: "
            f"scanned={summary.scanned}, rotated={summary.rotated}, "
            f"already_active={summary.already_active}."
        )
    else:
        print(
            "TOTP dry run complete; no rows were modified: "
            f"scanned={summary.scanned}, would_rotate={summary.would_rotate}, "
            f"already_active={summary.already_active}."
        )
    return 0


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if not 1 <= args.batch_size <= _BATCH_SIZE_LIMIT:
        parser.error(f"--batch-size must be between 1 and {_BATCH_SIZE_LIMIT}")
    try:
        return asyncio.run(_run_cli(args))
    except KeyboardInterrupt:
        print(
            "TOTP rotation interrupted; the current batch transaction was rolled back.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
