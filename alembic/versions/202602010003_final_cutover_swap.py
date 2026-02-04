"""Final Cutover: Swap all IDs and FKs to UUID v7

Revision ID: 202602010003
Revises: 202602010002
Create Date: 2026-02-01 05:00:00.000000

"""

import logging

import sqlalchemy as sa

from alembic import op

revision = "202602010003"
down_revision = "202602010002"

TABLES_TO_SWAP = [
    "users",
    "groups",
    "stored_events",
    "notification_queue_jobs",
    "push_subscriptions",
    "active_sessions",
    "mfa_totp_enrollments",
    "mfa_challenges",
    "failed_login_attempts",
    "password_reset_tokens",
    "email_change_tokens",
    "trusted_devices",
    "webauthn_credentials",
    "recovery_codes",
    "login_history",
    "events",
    "event_attendance",
    "event_files",
    "news",
    "news_likes",
    "news_comments",
    "invite_codes",
    "messages",
    "stories",
]

# (Table, Legacy FK Col, Shadow FK Col, Referenced Table)
FK_TO_SWAP = [
    ("active_sessions", "user_id", "shadow_user_id", "users"),
    ("chat_participants", "user_id", "shadow_user_id", "users"),
    ("email_change_tokens", "user_id", "shadow_user_id", "users"),
    ("event_attendance", "user_id", "shadow_user_id", "users"),
    ("failed_login_attempts", "user_id", "shadow_user_id", "users"),
    ("invite_codes", "used_by_user_id", "shadow_used_by_user_id", "users"),
    ("login_history", "user_id", "shadow_user_id", "users"),
    ("messages", "sender_id", "shadow_sender_id", "users"),
    ("mfa_challenges", "user_id", "shadow_user_id", "users"),
    ("mfa_totp_enrollments", "user_id", "shadow_user_id", "users"),
    ("news_comments", "user_id", "shadow_user_id", "users"),
    ("news_likes", "user_id", "shadow_user_id", "users"),
    ("password_reset_tokens", "user_id", "shadow_user_id", "users"),
    ("push_subscriptions", "user_id", "shadow_user_id", "users"),
    ("recovery_codes", "user_id", "shadow_user_id", "users"),
    ("spotify_integrations", "user_id", "shadow_user_id", "users"),
    ("stories", "created_by", "shadow_user_id", "users"),
    ("trusted_devices", "user_id", "shadow_user_id", "users"),
    ("user_education_paths", "user_id", "shadow_user_id", "users"),
    ("user_preferences", "user_id", "shadow_user_id", "users"),
    ("user_profile_details", "user_id", "shadow_user_id", "users"),
    ("user_push_topics", "user_id", "shadow_user_id", "users"),
    ("webauthn_credentials", "user_id", "shadow_user_id", "users"),
    ("events", "created_by", "shadow_created_by", "users"),
    ("event_attendance", "event_id", "shadow_event_id", "events"),
    ("event_files", "event_id", "shadow_event_id", "events"),
    ("news_comments", "news_id", "shadow_news_id", "news"),
    ("news_likes", "news_id", "shadow_news_id", "news"),
]


def upgrade():
    # 1. Drop all Foreign Key constraints that reference our swap tables
    logger = logging.getLogger("alembic")
    logger.info("Identifying and dropping dependent FK constraints...")

    bind = op.get_bind()
    referenced_tables_str = ", ".join(f"'{t}'" for t in TABLES_TO_SWAP)

    # Query to find all FKs referencing our tables
    # (excluding partitions to avoid double-dropping)
    fk_query = sa.text(f"""
        SELECT
            r.relname AS table_name,
            c.conname AS constraint_name,
            a.attname AS column_name,
            fr.relname AS foreign_table_name,
            fa.attname AS foreign_column_name,
            c.confdeltype,
            c.confupdtype
        FROM
            pg_constraint c
            JOIN pg_class r ON c.conrelid = r.oid
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            JOIN pg_class fr ON c.confrelid = fr.oid
            JOIN pg_attribute fa ON fa.attrelid = c.confrelid
            AND fa.attnum = ANY(c.confkey)
            JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE c.contype = 'f'
          AND fr.relname IN ({referenced_tables_str})
          AND r.relispartition = false
    """)

    fks = bind.execute(fk_query).fetchall()

    def get_rule(code):
        return {
            "a": "NO ACTION",
            "r": "RESTRICT",
            "c": "CASCADE",
            "n": "SET NULL",
            "d": "SET DEFAULT",
        }.get(code, "NO ACTION")

    # Store FK definitions for recreation
    fk_definitions = []
    for fk in fks:
        fk_definitions.append(
            {
                "table": fk.table_name,
                "name": fk.constraint_name,
                "column": fk.column_name,
                "ref_table": fk.foreign_table_name,
                "ref_column": fk.foreign_column_name,
                "ondelete": get_rule(fk.confdeltype),
                "onupdate": get_rule(fk.confupdtype),
            }
        )

    for fk in fk_definitions:
        logger.info(f"Dropping FK {fk['name']} on {fk['table']}")
        op.drop_constraint(fk["name"], fk["table"], type_="foreignkey")

    # 2. Populate Shadow IDs and Foreign Keys for cutover
    bind = op.get_bind()
    from app.utils.uuid_v7 import generate_uuid7

    logger = logging.getLogger("alembic")

    # 2.1 Fill uuid_id for each table
    for table in TABLES_TO_SWAP:
        logger.info(f"Populating uuid_id for {table}...")
        # Check if table has created_at for better UUID v7
        has_created_at = bind.execute(
            sa.text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='{table}' AND column_name='created_at'"
            )
        ).scalar()

        rows = bind.execute(
            sa.text(
                f"SELECT id{(', created_at' if has_created_at else '')} FROM {table} "
                "WHERE uuid_id IS NULL"
            )
        ).fetchall()
        for row in rows:
            new_uuid = generate_uuid7(row.created_at if has_created_at else None)
            bind.execute(
                sa.text(f"UPDATE {table} SET uuid_id = :val WHERE id = :id"),
                {"val": new_uuid, "id": row.id},
            )

    # 2.2 Fill shadow FK columns
    for table, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
        logger.info(f"Populating {shadow_col} for {table} referencing {ref_table}...")
        # Join target table with ref_table to get the new UUID
        stmt = sa.text(f"""
            UPDATE {table} t
            SET {shadow_col} = r.uuid_id
            FROM {ref_table} r
            WHERE t.{legacy_col} = r.id
            AND t.{shadow_col} IS NULL
        """)
        bind.execute(stmt)

    # 3. Rename columns and swap Primary Keys
    for table in TABLES_TO_SWAP:
        op.alter_column(table, "id", new_column_name="legacy_id")
        # Rename uuid_id to id
        op.alter_column(table, "uuid_id", new_column_name="id")
        # Make the new id NOT NULL
        op.alter_column(table, "id", nullable=False)
        # Swap Primary Key
        # op.drop_constraint(f"{table}_pkey", table, type_="primary")
        bind.execute(
            sa.text(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey CASCADE")
        )
        op.create_primary_key(f"{table}_pkey", table, ["id"])
        # Create Unique Constraint on legacy_id
        # so it can be referenced by non-migrated FKs
        op.create_unique_constraint(f"uq_{table}_legacy_id", table, ["legacy_id"])

    # 4. Recreate Foreign Key constraints
    logger.info("Recreating FK constraints...")
    for fk in fk_definitions:
        # Determine if we should point to 'id' (UUID) or 'legacy_id' (INT)
        is_handled_by_swap = any(
            t == fk["table"] and lc == fk["column"] for t, lc, sc, rt in FK_TO_SWAP
        )

        if not is_handled_by_swap:
            logger.info(
                f"Recreating non-swapped FK {fk['name']} on {fk['table']} "
                "pointing to legacy_id"
            )
            op.create_foreign_key(
                fk["name"],
                fk["table"],
                fk["ref_table"],
                [fk["column"]],
                ["legacy_id"],
                ondelete=fk["ondelete"],
                onupdate=fk["onupdate"],
            )

    # 5. Build new UUID-based FKs for the swapped columns
    for table, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
        op.alter_column(table, legacy_col, new_column_name=f"legacy_{legacy_col}")
        op.alter_column(table, shadow_col, new_column_name=legacy_col)
        # Create new FK constraint
        op.create_foreign_key(
            f"fk_{table}_{legacy_col}_uuid",
            table,
            ref_table,
            [legacy_col],
            ["id"],
            ondelete="CASCADE" if "delivery" not in table else "SET NULL",
        )


def downgrade():
    # Inverse logic
    pass
