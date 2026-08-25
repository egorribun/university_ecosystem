"""Final Cutover: Swap all IDs and FKs to UUID v7

Revision ID: 202602010003
Revises: 202602010002
Create Date: 2026-02-01 05:00:00.000000

"""

# ruff: noqa: S608

import logging

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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
    "chats",
    "attachments",
    "notifications",
    "notification_deliveries",
    "data_access_logs",
    "schedule",
]

PARTITION_KEYS = {
    "notifications": "created_at",
    "notification_deliveries": "attempted_at",
    "data_access_logs": "created_at",
}


def _is_inherited_partition_constraint(bind, table_name, constraint_name):
    """Return whether PostgreSQL forbids dropping this child constraint directly."""
    if bind.dialect.name != "postgresql":
        return False
    inherited_count = bind.execute(
        sa.text(
            "SELECT c.coninhcount FROM pg_constraint AS c "
            "WHERE c.conrelid = to_regclass(:table_name) "
            "AND c.conname = :constraint_name"
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).scalar_one_or_none()
    return bool(inherited_count)


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
    ("spotify_integrations", "user_id", "shadow_user_id", "users"),
    ("stories", "created_by", "shadow_user_id", "users"),
    ("trusted_devices", "user_id", "shadow_user_id", "users"),
    ("user_education_paths", "user_id", "shadow_user_id", "users"),
    ("user_preferences", "user_id", "shadow_user_id", "users"),
    ("user_profile_details", "user_id", "shadow_user_id", "users"),
    ("user_push_topics", "user_id", "shadow_user_id", "users"),
    ("webauthn_credentials", "user_id", "shadow_user_id", "users"),
    ("recovery_codes", "user_id", "shadow_user_id", "users"),
    ("events", "created_by", "shadow_created_by", "users"),
    ("event_attendance", "event_id", "shadow_event_id", "events"),
    ("event_files", "event_id", "shadow_event_id", "events"),
    ("news_comments", "news_id", "shadow_news_id", "news"),
    ("news_likes", "news_id", "shadow_news_id", "news"),
    ("users", "group_id", "shadow_group_id", "groups"),
    ("schedule", "group_id", "shadow_group_id", "groups"),
    ("news", "author_id", "shadow_author_id", "users"),
    ("notifications", "user_id", "shadow_user_id", "users"),
    (
        "notification_deliveries",
        "notification_id",
        "shadow_notification_id",
        "notifications",
    ),
    ("data_access_logs", "actor_user_id", "shadow_actor_user_id", "users"),
    ("data_access_logs", "subject_user_id", "shadow_subject_user_id", "users"),
    ("attachments", "message_id", "shadow_message_id", "messages"),
    ("chat_participants", "chat_id", "shadow_chat_id", "chats"),
    ("messages", "chat_id", "shadow_chat_id", "chats"),
]


def upgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_postgresql = bind.dialect.name == "postgresql"
    index_cascade = " CASCADE" if is_postgresql else ""
    from app.utils.uuid_v7 import generate_uuid7

    # 1. Identify all affected tables and their FKs

    # Filter out tables that are already migrated (id is UUID)
    tables_to_process = []

    # Need to check columns
    for table in TABLES_TO_SWAP:
        if not inspector.has_table(table):
            continue

        columns = {c["name"]: c for c in inspector.get_columns(table)}
        id_col = columns.get("id")

        # If id is UUID, it's already migrated. Skip.
        if id_col and isinstance(id_col["type"], postgresql.UUID):
            logger.info(f"Skipping {table} - already migrated to UUID")
            continue

        tables_to_process.append(table)

    TABLES_TO_SWAP[:] = tables_to_process

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

    # 1.1 Create name map for name preservation
    fk_name_map = {}  # {(table_name, column_name): original_name}
    for t_name, fks_list in fks_to_drop.items():
        for f in fks_list:
            fk_name_map[(t_name, f["column"])] = f["name"]

    # 2. Data Migration: Populate uuid_id and shadow FKs (Raw SQL)
    # 2.1 uuid_id
    for table in TABLES_TO_SWAP:
        columns = [c["name"] for c in inspector.get_columns(table)]
        if "id" not in columns:
            continue

        logger.info(f"Populating uuid_id for {table}...")
        has_created_at = "created_at" in columns
        rows = bind.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                f"SELECT id{(', created_at' if has_created_at else '')} "
                f"FROM {table} WHERE uuid_id IS NULL"
            )
        ).fetchall()
        for row in rows:
            new_uuid = str(generate_uuid7(row.created_at if has_created_at else None))
            bind.execute(
                sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    f"UPDATE {table} SET uuid_id = :val WHERE id = :id"
                ),
                {"val": new_uuid, "id": row.id},
            )

    # 2.2 Shadow FKs
    truncated_tables = set()

    for table, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
        # Check if table is being processed (it might have been filtered out
        # if already migrated)
        # Note: We modified TABLES_TO_SWAP list in-place previously,
        # but FK_TO_SWAP is static.
        # We need to check if 'table' is in the CURRENT TABLES_TO_SWAP list?
        # Actually, simpler: check if 'shadow_col' exists. If not, we skip.
        # But we must be careful. If 'table' IS in TABLES_TO_SWAP,
        # we must process it.
        # If 'table' was Removed from TABLES_TO_SWAP, it means it is
        # already migrated, so we skip.

        if table not in TABLES_TO_SWAP:
            # Table is already done (or skipped).
            continue

        columns = [c["name"] for c in inspector.get_columns(table)]
        if legacy_col not in columns or shadow_col not in columns:
            logger.info(
                f"Skipping population for {shadow_col} in {table} (column missing)..."
            )
            continue

        # Check ref_table state
        ref_columns = {c["name"]: c for c in inspector.get_columns(ref_table)}
        ref_id_col = ref_columns.get("id")
        ref_uuid_col = ref_columns.get("uuid_id")

        ref_is_already_migrated = (
            ref_id_col is not None
            and isinstance(ref_id_col["type"], postgresql.UUID)
            and ref_uuid_col is None
        )

        if ref_is_already_migrated:
            if table not in truncated_tables:
                logger.warning(
                    f"Referenced table {ref_table} is already migrated and "
                    "Legacy IDs are lost. "
                    f"Cannot map records in {table}. TRUNCATING {table} to proceed."
                )
                bind.execute(
                    sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        f'TRUNCATE TABLE "{table}" CASCADE'
                    )
                )
                truncated_tables.add(table)
            continue

        logger.info(f"Populating {shadow_col} for {table}...")
        stmt = sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"""
            UPDATE "{table}"
            SET "{shadow_col}" = (
                SELECT r.uuid_id FROM "{ref_table}" r
                WHERE r.id = "{table}"."{legacy_col}"
            )
            WHERE EXISTS (
                SELECT 1 FROM "{ref_table}" r
                WHERE r.id = "{table}"."{legacy_col}"
            ) AND "{shadow_col}" IS NULL
        """
        )
        bind.execute(stmt)

    # 3. Multi-Pass Structural Swap (to avoid type mismatches during FK creation)
    # Collect all tables that need any change
    all_affected_tables_set = (
        set(TABLES_TO_SWAP) | set(fks_to_drop.keys()) | {t for t, _, _, _ in FK_TO_SWAP}
    )
    # Filter by actual existence to avoid processing dropped/missing tables
    all_affected_tables_set = {
        t for t in all_affected_tables_set if inspector.has_table(t)
    }

    # Pass 0: Detect partitions to avoid direct manipulation (must be done on parent)
    partitions = set()
    parent_map = {}
    if bind.dialect.name == "postgresql":
        results = bind.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                SELECT parent.relname, child.relname
                FROM pg_inherits
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                """
            )
        ).fetchall()
        for parent, child in results:
            partitions.add(child)
            parent_map.setdefault(parent, []).append(child)

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

            # Drop old PK
            pk_constraint = inspector.get_pk_constraint(table)
            if pk_constraint and pk_constraint["name"]:
                logger.info(f"Dropping PK {pk_constraint['name']} for {table}...")
                if bind.dialect.name == "postgresql":
                    batch_op.execute(
                        f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS '
                        f'"{pk_constraint["name"]}" CASCADE'
                    )
                else:
                    batch_op.drop_constraint(pk_constraint["name"], type_="primary")

            pk_cols = ["id"]
            if bind.dialect.name == "postgresql" and table in PARTITION_KEYS:
                pk_cols.append(PARTITION_KEYS[table])

            batch_op.create_primary_key(f"{table}_pkey", pk_cols)

            # Check if UQ exists
            uq_name = f"uq_{table}_legacy_id"
            existing_constraints = inspector.get_unique_constraints(table)
            if not any(c["name"] == uq_name for c in existing_constraints):
                # Keep both unique for transition
                uq_cols = ["legacy_id"]
                if bind.dialect.name == "postgresql" and table in PARTITION_KEYS:
                    uq_cols.append(PARTITION_KEYS[table])
                batch_op.create_unique_constraint(uq_name, uq_cols)

    # 3.3 FK Swap Phase: Swap FK columns and Recreate ALL constraints
    for table in all_affected_tables:
        logger.info(f"Finalizing FKs for {table}...")
        pk_constraint = inspector.get_pk_constraint(table)
        pk_columns = (
            pk_constraint.get("constrained_columns", []) if pk_constraint else []
        )
        columns = {c["name"] for c in inspector.get_columns(table)}
        try:
            existing_fks = inspector.get_foreign_keys(table)
        except Exception:
            existing_fks = []
            logger.warning(f"Could not fetch FKs for {table}")

        # and drop them. They are on data that will become
        # legacy/dropped, so we don't need them.

        # 1. Identify columns being swapped for this table
        swapped_cols = {legacy_col for t, legacy_col, _, _ in FK_TO_SWAP if t == table}

        # Expand tables to verify: table itself + any children (partitions)
        tables_to_purge = [table]
        if "parent_map" in locals() and table in parent_map:
            tables_to_purge.extend(parent_map[table])

        # Data structures to hold objects for recreation
        uqs_to_recreate = []  # List of (parent_table, name, columns)
        indexes_to_recreate = []  # List of (parent_table, name, columns, unique)

        for t_name in tables_to_purge:
            # 2. explicit legacy names from previous failed runs
            for col in swapped_cols:
                op.execute(  # nosemgrep
                    f'DROP INDEX IF EXISTS "ix_{t_name}_legacy_{col}"{index_cascade}'
                )

            if swapped_cols:
                # 3. Existing unique constraints on these columns
                try:
                    existing_uq = inspector.get_unique_constraints(t_name)
                except Exception:
                    existing_uq = []

                dropped_uq_names = set()
                for uq in existing_uq:
                    if not uq.get("name"):
                        continue
                    if _is_inherited_partition_constraint(bind, t_name, uq["name"]):
                        logger.info(
                            "Skipping inherited unique constraint %s on partition %s; "
                            "the parent constraint owns its lifecycle",
                            uq["name"],
                            t_name,
                        )
                        continue
                    msg = (
                        f"Dropping unique constraint {uq['name']} on {t_name} "
                        "involved in swap"
                    )
                    logger.info(msg)
                    if bind.dialect.name == "postgresql":
                        op.execute(
                            f'ALTER TABLE "{t_name}" DROP CONSTRAINT IF EXISTS '
                            f'"{uq["name"]}" CASCADE'
                        )
                    else:
                        with op.batch_alter_table(t_name) as batch_op:
                            batch_op.drop_constraint(uq["name"], type_="unique")

                    # Store for recreation (only for the parent table)
                    if t_name == table:
                        uqs_to_recreate.append((table, uq["name"], uq["column_names"]))
                    dropped_uq_names.add(uq["name"])

                # 4. Existing indexes on these columns
                try:
                    existing_indexes = inspector.get_indexes(t_name)
                except Exception:
                    existing_indexes = []

                for idx in existing_indexes:
                    # Skip if this is a primary key index (handled elsewhere)
                    # or already dropped via constraint
                    if idx["name"].endswith("_pkey") or idx["name"] in dropped_uq_names:
                        continue

                    # If index uses any of the swapped columns, drop it
                    if set(idx["column_names"]) & swapped_cols:
                        msg = (
                            f"Dropping index {idx['name']} on {t_name} involved in swap"
                        )
                        logger.info(msg)
                        op.execute(  # nosemgrep
                            f'DROP INDEX IF EXISTS "{idx["name"]}"{index_cascade}'
                        )

                        # Store for recreation (only for the parent table)
                        if t_name == table:
                            indexes_to_recreate.append(
                                (
                                    table,
                                    idx["name"],
                                    idx["column_names"],
                                    idx.get("unique", False),
                                )
                            )
        with op.batch_alter_table(table) as batch_op:
            # A. Swap Columns for FK_TO_SWAP (Migrated FKs)
            # A. Swap Columns for FK_TO_SWAP (Migrated FKs)
            pk_dropped = False
            recreate_pk = False

            for t, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
                if t == table:
                    is_pk = legacy_col in pk_columns
                    if is_pk:
                        recreate_pk = True
                        if not pk_dropped:
                            # Drop old PK
                            # We re-fetch PK constraint here just in case,
                            # but we have it above.
                            # However, since we are inside a loop that might modify
                            # the table, relying on the initial fetch is safer if we
                            # haven't dropped it yet.
                            if pk_constraint and pk_constraint["name"]:
                                logger.info(
                                    f"Dropping PK {pk_constraint['name']} "
                                    f"for {table}..."
                                )
                                if bind.dialect.name == "postgresql":
                                    batch_op.execute(
                                        f"ALTER TABLE {table} "
                                        "DROP CONSTRAINT IF EXISTS "
                                        f'"{pk_constraint["name"]}" CASCADE'
                                    )
                                else:
                                    batch_op.drop_constraint(
                                        pk_constraint["name"], type_="primary"
                                    )
                            pk_dropped = True

                    if legacy_col in columns:
                        # Safety check: if legacy_{legacy_col} already exists
                        # (from failed run), we must drop it first to allow rename.
                        target_legacy_name = f"legacy_{legacy_col}"
                        if target_legacy_name in columns:
                            logger.info(
                                f"Dropping stale column {target_legacy_name} "
                                f"from {table}"
                            )
                            # We use execute to ensure CASCADE works if needed
                            # (though drop_column might be enough)
                            # batch_op doesn't strictly support CASCADE flag easily
                            # in all backends, but on Postgres we explicitly want to
                            # kill indexes.
                            if bind.dialect.name == "postgresql":
                                batch_op.execute(
                                    f"ALTER TABLE {table} DROP COLUMN "
                                    f"IF EXISTS {target_legacy_name} CASCADE"
                                )
                            else:
                                batch_op.drop_column(target_legacy_name)

                        batch_op.alter_column(
                            legacy_col, new_column_name=target_legacy_name
                        )

                    if shadow_col in columns:
                        batch_op.alter_column(shadow_col, new_column_name=legacy_col)

                    original_name = fk_name_map.get((table, legacy_col))

                    local_cols = [legacy_col]
                    ref_cols = ["id"]
                    if (
                        bind.dialect.name == "postgresql"
                        and table == "notification_deliveries"
                        and ref_table == "notifications"
                    ):
                        local_cols.append("notification_created_at")
                        ref_cols.append("created_at")

                    # Check if FK already exists to prevent duplication error
                    fk_exists = False
                    # We need to refresh FKs if possible, or use pre-fetched.
                    # Since we are in batch block, we rely on pre-fetched `existing_fks`
                    # (which we need to fetch before batch block)
                    # BUT wait, we just renamed columns. The inspector results from
                    # start of loop (before batch) reflect old state?
                    # "legacy_col" was renamed to "legacy_..."
                    # "shadow_col" was renamed to "legacy_col" (which is now user_id)
                    # So current "user_id" (legacy_col) IS the one we want to put FK on.

                    # If FK exists on 'user_id' pointing to 'users.id', we skip.
                    if "existing_fks" in locals():
                        for efk in existing_fks:
                            # Check exact name match
                            target_name = (
                                original_name or f"fk_{table}_{legacy_col}_uuid"
                            )
                            if efk["name"] == target_name:
                                fk_exists = True
                                break

                    if not fk_exists:
                        batch_op.create_foreign_key(
                            original_name or f"fk_{table}_{legacy_col}_uuid",
                            ref_table,
                            local_cols,
                            ref_cols,
                            ondelete="CASCADE"
                            if t in ("notification_deliveries", "event_attendance")
                            else "SET NULL",
                        )

            # C. Recreate collected UniqueConstraints and Indices
            for _, uq_name, uq_cols in uqs_to_recreate:
                # For partitioned tables, ensure partition key is included
                # in unique constraint
                target_uq_cols = list(uq_cols)
                if bind.dialect.name == "postgresql" and table in PARTITION_KEYS:
                    pk_part = PARTITION_KEYS[table]
                    if pk_part not in target_uq_cols:
                        target_uq_cols.append(pk_part)
                batch_op.create_unique_constraint(uq_name, target_uq_cols)

            for _, idx_name, idx_cols, idx_unique in indexes_to_recreate:
                if idx_unique:
                    target_idx_cols = list(idx_cols)
                    if bind.dialect.name == "postgresql" and table in PARTITION_KEYS:
                        pk_part = PARTITION_KEYS[table]
                        if pk_part not in target_idx_cols:
                            target_idx_cols.append(pk_part)
                    batch_op.create_unique_constraint(idx_name, target_idx_cols)
                else:
                    batch_op.create_index(idx_name, idx_cols)

            if recreate_pk and pk_dropped:
                # Recreate PK using original columns (which now hold UUIDs)
                # Ensure we handle partition keys if they weren't in the original PK
                # (though usually they should be)
                logger.info(f"Recreating PK for {table} with columns {pk_columns}...")

                # Check if we need to append partition key (if not present)
                # strictly speaking, inspector.get_pk_constraint return ALL columns
                # in PK. So we should just use pk_columns.

                batch_op.create_primary_key(f"{table}_pkey", pk_columns)

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
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Discovery Phase: Identify all current foreign keys pointing to swapped tables
    fks_to_restore = {}  # {table_name: [fk_definitions]}
    all_table_names = inspector.get_table_names()

    for table_name in all_table_names:
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            if fk["referred_table"] in TABLES_TO_SWAP:
                fks_to_restore.setdefault(table_name, []).append(
                    {
                        "name": fk["name"],
                        "column": fk["constrained_columns"][0],
                        "ref_table": fk["referred_table"],
                        "ref_column": fk["referred_columns"][0],
                        "ondelete": fk.get("options", {}).get("ondelete", "NO ACTION"),
                        "onupdate": fk.get("options", {}).get("onupdate", "NO ACTION"),
                    }
                )

    # Pass 0: Detect partitions
    partitions = set()
    parent_map = {}
    if bind.dialect.name == "postgresql":
        results = bind.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                SELECT parent.relname, child.relname
                FROM pg_inherits
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                """
            )
        ).fetchall()
        for parent, child in results:
            partitions.add(child)
            parent_map.setdefault(parent, []).append(child)

    all_affected_tables_set = (
        set(TABLES_TO_SWAP)
        | set(fks_to_restore.keys())
        | {t for t, _, _, _ in FK_TO_SWAP}
    )
    all_affected_tables = [t for t in all_affected_tables_set if t not in partitions]

    # 2. Drop Phase: Drop all current foreign keys first
    is_postgresql = bind.dialect.name == "postgresql"
    index_cascade = " CASCADE" if is_postgresql else ""

    for table_name in all_affected_tables:
        fks = fks_to_restore.get(table_name, [])
        if fks:
            logger.info(f"Dropping FKs for {table_name}...")
            with op.batch_alter_table(table_name) as batch_op:
                for fk in fks:
                    if fk["name"]:
                        batch_op.drop_constraint(fk["name"], type_="foreignkey")

    # 3. Dynamic Index/UQ Restoration Preparation
    # We must drop indexes/UQs on swapped columns before renaming,
    # then recreate them after renaming.
    for table in all_affected_tables:
        swapped_cols = {legacy_col for t, legacy_col, _, _ in FK_TO_SWAP if t == table}
        if table in TABLES_TO_SWAP:
            swapped_cols.add("id")

        if not swapped_cols:
            continue

        tables_to_purge = [table]
        if table in parent_map:
            tables_to_purge.extend(parent_map[table])

        uqs_to_recreate = []
        indexes_to_recreate = []

        for t_name in tables_to_purge:
            # Drop explicit legacy indexes if any exist from failed runs
            for col in swapped_cols:
                op.execute(  # nosemgrep
                    f'DROP INDEX IF EXISTS "ix_{t_name}_legacy_{col}"{index_cascade}'
                )

            # Collect and drop existing UQs and Indexes on swapped columns
            try:
                existing_uq = inspector.get_unique_constraints(t_name)
            except Exception:
                existing_uq = []

            dropped_uq_names = set()
            for uq in existing_uq:
                if not uq.get("name"):
                    continue
                if set(uq["column_names"]) & swapped_cols:
                    if _is_inherited_partition_constraint(bind, t_name, uq["name"]):
                        logger.info(
                            "Skipping inherited UQ %s on partition %s; "
                            "the parent constraint owns its lifecycle",
                            uq["name"],
                            t_name,
                        )
                        continue
                    logger.info(f"Dropping UQ {uq['name']} on {t_name} for swap")
                    if is_postgresql:
                        op.execute(
                            f'ALTER TABLE "{t_name}" DROP CONSTRAINT IF EXISTS '
                            f'"{uq["name"]}" CASCADE'
                        )
                    else:
                        with op.batch_alter_table(t_name) as batch_op:
                            batch_op.drop_constraint(uq["name"], type_="unique")
                    if t_name == table:
                        uqs_to_recreate.append((table, uq["name"], uq["column_names"]))
                    dropped_uq_names.add(uq["name"])

            try:
                existing_indexes = inspector.get_indexes(t_name)
            except Exception:
                existing_indexes = []

            for idx in existing_indexes:
                if idx["name"].endswith("_pkey") or idx["name"] in dropped_uq_names:
                    continue
                if set(idx["column_names"]) & swapped_cols:
                    logger.info(f"Dropping index {idx['name']} on {t_name} for swap")
                    op.execute(  # nosemgrep
                        f'DROP INDEX IF EXISTS "{idx["name"]}"{index_cascade}'
                    )
                    if t_name == table:
                        indexes_to_recreate.append(
                            (
                                table,
                                idx["name"],
                                idx["column_names"],
                                idx.get("unique", False),
                            )
                        )

        # 4. Reverse Column Swap Phase
        with op.batch_alter_table(table) as batch_op:
            # A. FK Column Renames
            for t, legacy_col, shadow_col, ref_table in FK_TO_SWAP:
                if t == table:
                    columns = {c["name"] for c in inspector.get_columns(table)}
                    legacy_int_col = f"legacy_{legacy_col}"
                    if legacy_col in columns:
                        if legacy_int_col in columns:
                            logger.info(
                                f"Reversing FK swap for {table}.{legacy_col}..."
                            )
                            batch_op.alter_column(
                                legacy_col, new_column_name=shadow_col
                            )
                            batch_op.alter_column(
                                legacy_int_col, new_column_name=legacy_col
                            )
                        else:
                            logger.info(
                                f"Reversing single FK for {table}.{legacy_col}..."
                            )
                            batch_op.alter_column(
                                legacy_col, new_column_name=shadow_col
                            )

            # B. PK Column Renames (if table is in TABLES_TO_SWAP)
            if table in TABLES_TO_SWAP and table not in partitions:
                columns = {c["name"] for c in inspector.get_columns(table)}
                if "id" in columns and "legacy_id" in columns:
                    logger.info(f"Reversing PK swap for {table}...")
                    if is_postgresql:
                        batch_op.execute(
                            f'ALTER TABLE "{table}" '
                            f'DROP CONSTRAINT IF EXISTS "{table}_pkey" CASCADE'
                        )
                        batch_op.execute(
                            f'ALTER TABLE "{table}" '
                            f'DROP CONSTRAINT IF EXISTS "uq_{table}_legacy_id" CASCADE'
                        )
                    else:
                        if bind.dialect.name != "sqlite":
                            batch_op.drop_constraint(f"{table}_pkey", type_="primary")
                            batch_op.drop_constraint(
                                f"uq_{table}_legacy_id", type_="unique"
                            )

                    batch_op.alter_column("id", new_column_name="uuid_id")
                    batch_op.alter_column(
                        "legacy_id", new_column_name="id", nullable=False
                    )

                    pk_cols = ["id"]
                    if is_postgresql and table in PARTITION_KEYS:
                        pk_part = PARTITION_KEYS[table]
                        if pk_part not in pk_cols:
                            pk_cols.append(pk_part)
                    batch_op.create_primary_key(f"{table}_pkey", pk_cols)

            # C. Recreate UQs and Indexes
            for _, uq_name, uq_cols in uqs_to_recreate:
                batch_op.create_unique_constraint(uq_name, uq_cols)

            for _, idx_name, idx_cols, idx_unique in indexes_to_recreate:
                if idx_unique:
                    batch_op.create_unique_constraint(idx_name, idx_cols)
                else:
                    batch_op.create_index(idx_name, idx_cols)

    # 5. Restore Original FKs Phase: Recreate FKs pointing back to the Integer 'id'
    # We refresh the inspector to see renamed columns
    refreshed_inspector = sa.inspect(bind)
    for table in all_affected_tables:
        fks = fks_to_restore.get(table, [])
        if fks:
            current_columns = {
                c["name"] for c in refreshed_inspector.get_columns(table)
            }
            logger.info(f"Restoring original FKs for {table}...")
            with op.batch_alter_table(table) as batch_op:
                for fk in fks:
                    # Point back to 'id' (restored Int) only if column still exists
                    if fk["column"] in current_columns:
                        batch_op.create_foreign_key(
                            fk["name"] or f"fk_{table}_{fk['column']}_original",
                            fk["ref_table"],
                            [fk["column"]],
                            ["id"],
                            ondelete=fk["ondelete"],
                            onupdate=fk["onupdate"],
                        )
                    else:
                        logger.info(
                            f"Skipping FK restoration for {table}.{fk['column']} "
                            "(column no longer exists after downgrade)"
                        )
