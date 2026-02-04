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
    "spotify_integrations",
    "user_education_paths",
    "user_preferences",
    "user_profile_details",
    "user_push_topics",
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
    ("users", "group_id", "shadow_group_id", "groups"),
    ("schedule", "group_id", "shadow_group_id", "groups"),
    ("news", "author_id", "shadow_author_id", "users"),
]


def upgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    from app.utils.uuid_v7 import generate_uuid7

    # 1. Identify all affected tables and their FKs
    fks_to_drop = {}  # {table_name: [fk_definitions]}
    referenced_elsewhere = {}  # {ref_table: [fk_definitions]}

    for table_name in inspector.get_table_names():
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            if fk["referred_table"] in TABLES_TO_SWAP:
                fk_def = {
                    "table": table_name,
                    "name": fk["name"],
                    "column": fk["constrained_columns"][0],
                    "ref_table": fk["referred_table"],
                    "ref_column": fk["referred_columns"][0],
                    "ondelete": fk.get("options", {}).get("ondelete", "NO ACTION"),
                    "onupdate": fk.get("options", {}).get("onupdate", "NO ACTION"),
                }
                fks_to_drop.setdefault(table_name, []).append(fk_def)
                referenced_elsewhere.setdefault(fk["referred_table"], []).append(fk_def)

    # 2. Data Migration: Populate uuid_id and shadow FKs (Raw SQL)
    # 2.1 uuid_id
    for table in TABLES_TO_SWAP:
        columns = [c["name"] for c in inspector.get_columns(table)]
        if "id" not in columns:
            continue

        logger.info(f"Populating uuid_id for {table}...")
        has_created_at = "created_at" in columns
        rows = bind.execute(
            sa.text(
                f"SELECT id{(', created_at' if has_created_at else '')} "
                f"FROM {table} WHERE uuid_id IS NULL"
            )
        ).fetchall()
        for row in rows:
            new_uuid = str(generate_uuid7(row.created_at if has_created_at else None))
            bind.execute(
                sa.text(f"UPDATE {table} SET uuid_id = :val WHERE id = :id"),
                {"val": new_uuid, "id": row.id},
            )

    # 2.2 Shadow FKs
    for table, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
        columns = [c["name"] for c in inspector.get_columns(table)]
        if legacy_col not in columns or shadow_col not in columns:
            logger.info(
                f"Skipping population for {shadow_col} in {table} (column missing)..."
            )
            continue

        logger.info(f"Populating {shadow_col} for {table}...")
        stmt = sa.text(f"""
            UPDATE {table}
            SET {shadow_col} = (
                SELECT r.uuid_id FROM {ref_table} r WHERE r.id = {table}.{legacy_col}
            )
            WHERE EXISTS (
                SELECT 1 FROM {ref_table} r WHERE r.id = {table}.{legacy_col}
            ) AND {shadow_col} IS NULL
        """)
        bind.execute(stmt)

    # 3. Multi-Pass Structural Swap (to avoid type mismatches during FK creation)
    # Collect all tables that need any change
    all_affected_tables_set = (
        set(TABLES_TO_SWAP) | set(fks_to_drop.keys()) | {t for t, _, _, _ in FK_TO_SWAP}
    )

    # Pass 0: Detect partitions to avoid direct manipulation (must be done on parent)
    partitions = set()
    if bind.dialect.name == "postgresql":
        partitions = {
            r[0]
            for r in bind.execute(
                sa.text(
                    """
                SELECT child.relname
                FROM pg_inherits
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
            """
                )
            ).fetchall()
        }

    # Filter out partitions from structural changes
    all_affected_tables = [t for t in all_affected_tables_set if t not in partitions]

    # 3.1 Drop Phase: Drop all involved foreign keys first
    for table_name in all_affected_tables:
        fks = fks_to_drop.get(table_name, [])
        if fks:
            logger.info(f"Dropping FKs for {table_name}...")
            with op.batch_alter_table(table_name) as batch_op:
                for fk in fks:
                    if fk["name"]:
                        batch_op.drop_constraint(fk["name"], type_="foreignkey")

    # 3.2 PK Swap Phase: Swap all Primary Keys to UUID
    for table in [t for t in TABLES_TO_SWAP if t not in partitions]:
        columns = [c["name"] for c in inspector.get_columns(table)]
        if "id" not in columns:
            logger.info(f"Skipping PK swap for {table} (no 'id' column)...")
            continue

        logger.info(f"Swapping PK for {table}...")
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("id", new_column_name="legacy_id")
            batch_op.alter_column("uuid_id", new_column_name="id", nullable=False)

            if bind.dialect.name == "postgresql":
                batch_op.execute(
                    f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "
                    f"{table}_pkey CASCADE"
                )
            elif bind.dialect.name != "sqlite":
                batch_op.drop_constraint(f"{table}_pkey", type_="primary")

            batch_op.create_primary_key(f"{table}_pkey", ["id"])
            batch_op.create_unique_constraint(f"uq_{table}_legacy_id", ["legacy_id"])

    # 3.3 FK Swap Phase: Swap FK columns and Recreate ALL constraints
    for table in all_affected_tables:
        logger.info(f"Finalizing FKs for {table}...")
        pk_constraint = inspector.get_pk_constraint(table)
        pk_columns = (
            pk_constraint.get("constrained_columns", []) if pk_constraint else []
        )
        columns = {c["name"] for c in inspector.get_columns(table)}

        with op.batch_alter_table(table) as batch_op:
            # A. Swap Columns for FK_TO_SWAP (Migrated FKs)
            for t, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
                if t == table:
                    is_pk = legacy_col in pk_columns
                    if is_pk:
                        if bind.dialect.name == "postgresql":
                            batch_op.execute(
                                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "
                                f"{table}_pkey CASCADE"
                            )
                        elif bind.dialect.name != "sqlite":
                            batch_op.drop_constraint(f"{table}_pkey", type_="primary")

                    if legacy_col in columns:
                        batch_op.alter_column(
                            legacy_col, new_column_name=f"legacy_{legacy_col}"
                        )

                    if shadow_col in columns:
                        batch_op.alter_column(shadow_col, new_column_name=legacy_col)

                    if is_pk:
                        batch_op.create_primary_key(f"{table}_pkey", [legacy_col])

                    batch_op.create_foreign_key(
                        f"fk_{table}_{legacy_col}_uuid",
                        ref_table,
                        [legacy_col],
                        ["id"],
                        ondelete="CASCADE"
                        if t in ("notification_deliveries", "event_attendance")
                        else "SET NULL",
                    )

            # B. Recreate non-migrated FKs to point to legacy_id
            for fk in fks_to_drop.get(table, []):
                is_swapped = any(
                    t == table and lc == fk["column"] for t, lc, sc, rt in FK_TO_SWAP
                )
                if not is_swapped:
                    batch_op.create_foreign_key(
                        fk["name"] or f"fk_{table}_{fk['column']}_legacy",
                        fk["ref_table"],
                        [fk["column"]],
                        ["legacy_id"],
                        ondelete=fk["ondelete"],
                        onupdate=fk["onupdate"],
                    )


def downgrade():
    # Inverse logic
    pass
