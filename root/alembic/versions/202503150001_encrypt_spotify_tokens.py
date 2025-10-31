"""Encrypt Spotify tokens using Fernet."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op
from app.utils.encryption import decrypt_string, encrypt_string

# revision identifiers, used by Alembic.
revision: str = "202503150001"
down_revision: str | None = "202503010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _encrypt_existing_tokens(session: Session) -> None:
    bind = session.get_bind()
    if not (
        _column_exists(bind, "users", "spotify_access_token")
        and _column_exists(bind, "users", "spotify_refresh_token")
    ):
        return

    rows = session.execute(
        sa.text("SELECT id, spotify_access_token, spotify_refresh_token FROM users")
    ).all()
    for row in rows:
        access = encrypt_string(row.spotify_access_token)
        refresh = encrypt_string(row.spotify_refresh_token)
        session.execute(
            sa.text(
                "UPDATE users SET "
                "spotify_access_token_encrypted = :access, "
                "spotify_refresh_token_encrypted = :refresh "
                "WHERE id = :user_id"
            ),
            {
                "access": access,
                "refresh": refresh,
                "user_id": row.id,
            },
        )
    session.commit()


def _decrypt_existing_tokens(session: Session) -> None:
    bind = session.get_bind()
    if not (
        _column_exists(bind, "users", "spotify_access_token")
        and _column_exists(bind, "users", "spotify_refresh_token")
    ):
        return

    rows = session.execute(
        sa.text("SELECT id, spotify_access_token, spotify_refresh_token FROM users")
    ).all()
    for row in rows:
        access = decrypt_string(row.spotify_access_token)
        refresh = decrypt_string(row.spotify_refresh_token)
        session.execute(
            sa.text(
                "UPDATE users SET "
                "spotify_access_token_plain = :access, "
                "spotify_refresh_token_plain = :refresh "
                "WHERE id = :user_id"
            ),
            {
                "access": access,
                "refresh": refresh,
                "user_id": row.id,
            },
        )
    session.commit()


def upgrade() -> None:
    """Apply Encrypt Spotify tokens using Fernet."""

    op.add_column(
        "users",
        sa.Column("spotify_access_token_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("spotify_refresh_token_encrypted", sa.Text(), nullable=True),
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        _encrypt_existing_tokens(session)
    finally:
        session.close()

    if _column_exists(bind, "users", "spotify_access_token"):
        op.drop_column("users", "spotify_access_token")
    if _column_exists(bind, "users", "spotify_refresh_token"):
        op.drop_column("users", "spotify_refresh_token")

    if _column_exists(bind, "users", "spotify_access_token_encrypted"):
        op.alter_column(
            "users",
            "spotify_access_token_encrypted",
            new_column_name="spotify_access_token",
        )
    if _column_exists(bind, "users", "spotify_refresh_token_encrypted"):
        op.alter_column(
            "users",
            "spotify_refresh_token_encrypted",
            new_column_name="spotify_refresh_token",
        )


def downgrade() -> None:
    """Revert Encrypt Spotify tokens using Fernet."""

    op.add_column(
        "users",
        sa.Column("spotify_access_token_plain", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("spotify_refresh_token_plain", sa.String(), nullable=True),
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        _decrypt_existing_tokens(session)
    finally:
        session.close()

    if _column_exists(bind, "users", "spotify_access_token"):
        op.drop_column("users", "spotify_access_token")
    if _column_exists(bind, "users", "spotify_refresh_token"):
        op.drop_column("users", "spotify_refresh_token")

    if _column_exists(bind, "users", "spotify_access_token_plain"):
        op.alter_column(
            "users",
            "spotify_access_token_plain",
            new_column_name="spotify_access_token",
        )
    if _column_exists(bind, "users", "spotify_refresh_token_plain"):
        op.alter_column(
            "users",
            "spotify_refresh_token_plain",
            new_column_name="spotify_refresh_token",
        )
