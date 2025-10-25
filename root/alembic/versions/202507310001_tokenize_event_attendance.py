"""tokenize event attendance qr codes

Revision ID: 202507310001
Revises: 202507300002
Create Date: 2025-07-31 00:01:00.000000
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import NoSuchTableError

from alembic import op

# revision identifiers, used by Alembic.
revision = "202507310001"
down_revision = "202507300002"
branch_labels = None
depends_on = None


def _server_secret() -> bytes:
    secret = os.getenv("ATTENDANCE_TOKEN_SECRET") or os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "ATTENDANCE_TOKEN_SECRET or SECRET_KEY must be set during migration"
        )
    return secret.strip().encode("utf-8")


def _encode_digest(secret: str) -> str:
    digest = hmac.new(_server_secret(), secret.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _table_columns(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except NoSuchTableError:
        return set()
    return {column["name"] for column in columns}


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = _table_columns(bind, "event_attendance")

    if "qr_secret" not in existing_columns:
        op.add_column(
            "event_attendance", sa.Column("qr_secret", sa.String(), nullable=True)
        )
    if "qr_hmac" not in existing_columns:
        op.add_column(
            "event_attendance", sa.Column("qr_hmac", sa.String(), nullable=True)
        )

    attendance = sa.table(
        "event_attendance",
        sa.column("id", sa.Integer()),
        sa.column("qr_code", sa.String()),
        sa.column("qr_secret", sa.String()),
        sa.column("qr_hmac", sa.String()),
    )

    connection = op.get_bind()
    current_columns = _table_columns(connection, "event_attendance")
    selectable = [attendance.c.id, attendance.c.qr_secret, attendance.c.qr_hmac]
    include_qr_code = "qr_code" in current_columns
    if include_qr_code:
        selectable.insert(1, attendance.c.qr_code)
    rows = connection.execute(sa.select(*selectable)).fetchall()
    for row in rows:
        mapping = row._mapping
        existing_secret = mapping.get("qr_secret")
        legacy_code = mapping.get("qr_code") if include_qr_code else None
        secret = existing_secret or legacy_code or secrets.token_urlsafe(32)
        digest = _encode_digest(secret)
        updates: dict[str, str] = {}
        if existing_secret != secret:
            updates["qr_secret"] = secret
        if mapping.get("qr_hmac") != digest:
            updates["qr_hmac"] = digest
        if updates:
            connection.execute(
                attendance.update()
                .where(attendance.c.id == mapping["id"])
                .values(**updates)
            )

    if include_qr_code:
        op.drop_column("event_attendance", "qr_code")
    if bind.dialect.name != "sqlite":
        if "qr_secret" in current_columns:
            op.alter_column("event_attendance", "qr_secret", nullable=False)
        if "qr_hmac" in current_columns:
            op.alter_column("event_attendance", "qr_hmac", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = _table_columns(bind, "event_attendance")

    if "qr_code" not in existing_columns:
        op.add_column(
            "event_attendance", sa.Column("qr_code", sa.String(), nullable=True)
        )

    attendance = sa.table(
        "event_attendance",
        sa.column("id", sa.Integer()),
        sa.column("qr_secret", sa.String()),
        sa.column("qr_code", sa.String()),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.select(attendance.c.id, attendance.c.qr_secret)
    ).fetchall()
    for row in rows:
        connection.execute(
            attendance.update()
            .where(attendance.c.id == row.id)
            .values(qr_code=row.qr_secret)
        )

    if "qr_hmac" in existing_columns or "qr_hmac" in _table_columns(connection, "event_attendance"):
        op.drop_column("event_attendance", "qr_hmac")
    if "qr_secret" in existing_columns or "qr_secret" in _table_columns(connection, "event_attendance"):
        op.drop_column("event_attendance", "qr_secret")
