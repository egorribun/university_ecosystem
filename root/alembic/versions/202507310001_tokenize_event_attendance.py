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


def upgrade() -> None:
    op.add_column("event_attendance", sa.Column("qr_secret", sa.String(), nullable=True))
    op.add_column("event_attendance", sa.Column("qr_hmac", sa.String(), nullable=True))

    attendance = sa.table(
        "event_attendance",
        sa.column("id", sa.Integer()),
        sa.column("qr_code", sa.String()),
        sa.column("qr_secret", sa.String()),
        sa.column("qr_hmac", sa.String()),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.select(attendance.c.id, attendance.c.qr_code)).fetchall()
    for row in rows:
        secret = row.qr_code or secrets.token_urlsafe(32)
        connection.execute(
            attendance.update()
            .where(attendance.c.id == row.id)
            .values(qr_secret=secret, qr_hmac=_encode_digest(secret))
        )

    op.drop_column("event_attendance", "qr_code")
    op.alter_column("event_attendance", "qr_secret", nullable=False)
    op.alter_column("event_attendance", "qr_hmac", nullable=False)


def downgrade() -> None:
    op.add_column("event_attendance", sa.Column("qr_code", sa.String(), nullable=True))

    attendance = sa.table(
        "event_attendance",
        sa.column("id", sa.Integer()),
        sa.column("qr_secret", sa.String()),
        sa.column("qr_code", sa.String()),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.select(attendance.c.id, attendance.c.qr_secret)).fetchall()
    for row in rows:
        connection.execute(
            attendance.update()
            .where(attendance.c.id == row.id)
            .values(qr_code=row.qr_secret)
        )

    op.drop_column("event_attendance", "qr_hmac")
    op.drop_column("event_attendance", "qr_secret")
