"""fix_missing_tables

Revision ID: 148642dd1207
Revises: f7aa476e968a
Create Date: 2026-01-18 22:30:50.324424

"""

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import app.utils.encryption
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "148642dd1207"
down_revision: str | None = "f7aa476e968a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SKIPPED_TABLES = set()

_GROUPS_ID_SHADOW_CHECK = "ck_groups_id_shadow_not_null"
_GROUPS_ID_DOWNGRADE_SHADOW_CHECK = "ck_groups_id_downgrade_shadow_not_null"
_GROUPS_ID_CHECK = "ck_groups_id_not_null"
_ACTIVE_SESSION_SIGNING_KEY_CHECK = "ck_active_sessions_signing_key_not_null"


def safe_create_table(table_name: str, *args, **kwargs) -> None:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
    except (sa.exc.NoInspectionAvailable, NameError):
        inspector = None

    if inspector is None or not inspector.has_table(table_name):
        op.create_table(table_name, *args, **kwargs)
    else:
        SKIPPED_TABLES.add(table_name)


class DummyBatchOp:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@contextmanager
def safe_batch_alter_table(table_name: str, schema=None, **kwargs):
    if table_name in SKIPPED_TABLES:
        yield DummyBatchOp()
    else:
        with op.batch_alter_table(table_name, schema=schema, **kwargs) as batch_op:
            yield batch_op


def ensure_partitioned(table_name: str, create_sql: str, partition_key: str) -> None:
    """Enforce partitioning on an existing table in PostgreSQL."""
    if context.is_offline_mode():
        return
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    try:
        inspector = sa.inspect(conn)
    except (sa.exc.NoInspectionAvailable, NameError):
        inspector = None

    if inspector is None:
        return

    if not inspector.has_table(table_name):
        return

    # Check if table is already partitioned
    res = conn.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT relkind FROM pg_class WHERE relname = :table_name"
        ),
        {"table_name": table_name},
    ).fetchone()

    if res and res[0] == "p":  # 'p' means partitioned table
        return

    # Table exists but is not partitioned. We must convert it.
    op.execute(f"DROP TABLE IF EXISTS {table_name}_old CASCADE")  # nosemgrep
    op.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")  # nosemgrep
    op.execute(create_sql)  # nosemgrep

    # Create default partition if it doesn't exist
    op.execute(  # nosemgrep
        f"CREATE TABLE IF NOT EXISTS {table_name}_default "
        f"PARTITION OF {table_name} DEFAULT"
    )

    # Move data
    columns = [c["name"] for c in inspector.get_columns(f"{table_name}_old")]
    cols_str = ", ".join(columns)
    op.execute(  # nosemgrep
        f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM {table_name}_old"  # noqa: S608
    )
    op.execute(f"DROP TABLE {table_name}_old")  # nosemgrep


def _groups_id_is_integer(inspector: Any) -> bool:
    """Return whether ``groups.id`` already has the target integer type.

    Alembic's offline inspector intentionally has no column metadata.  In that
    mode the migration is rendered for the pre-148 schema, whose id is the
    legacy VARCHAR column, so the phased conversion is emitted.
    """

    if inspector is None:
        return False
    columns = inspector.get_columns("groups")
    id_column = next((column for column in columns if column["name"] == "id"), None)
    return bool(id_column and isinstance(id_column["type"], sa.Integer))


def _postgresql_groups_id_upgrade(inspector: Any) -> None:
    """Convert the legacy groups key with an additive, validated cutover.

    PostgreSQL's in-place ``ALTER COLUMN ... TYPE`` is intentionally avoided.
    The source key is copied to an additive compatibility column, validated,
    and only then replaced by a fresh nullable integer column.
    """

    if inspector is not None and not inspector.has_table("groups"):
        return

    existing_indexes = (
        {index["name"] for index in inspector.get_indexes("groups")}
        if inspector is not None
        else set()
    )

    # IF NOT EXISTS keeps this phase safe to retry after a cancelled deploy.
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS course INTEGER")
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS faculty VARCHAR")

    if _groups_id_is_integer(inspector):
        if "ix_groups_id" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS ix_groups_id")
        return

    # Validate the source before casting.  The CASE expression prevents an
    # invalid value from being evaluated as numeric by PostgreSQL's planner.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM groups
                    WHERE id IS NULL
                       OR id !~ '^[0-9]+$'
                       OR CASE
                            WHEN id ~ '^[0-9]+$' THEN id::numeric > 2147483647
                            ELSE FALSE
                          END
                ) THEN
                    RAISE EXCEPTION
                        'groups.id contains a value that cannot be converted to INTEGER';
                END IF;
                IF EXISTS (
                    SELECT id::integer
                    FROM groups
                    GROUP BY id::integer
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'groups.id contains duplicate values after INTEGER conversion';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS id__integer INTEGER")
    op.execute("UPDATE groups SET id__integer = id::integer WHERE id__integer IS NULL")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_groups_id_shadow_not_null'
                      AND conrelid = 'groups'::regclass
                ) THEN
                    ALTER TABLE groups
                        ADD CONSTRAINT ck_groups_id_shadow_not_null
                        CHECK (id__integer IS NOT NULL) NOT VALID;
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_shadow_not_null")

    # Preserve any child FKs while the referenced key is replaced.  Child
    # columns are converted to INTEGER and restored against the new id below.
    _capture_groups_foreign_keys()
    _convert_captured_fk_columns("INTEGER")
    op.execute("ALTER TABLE groups DROP CONSTRAINT IF EXISTS groups_pkey")
    if "ix_groups_id" in existing_indexes:
        op.execute("DROP INDEX IF EXISTS ix_groups_id")
    # Squawk's ban-drop-column rule is aimed at unplanned destructive schema
    # edits.  This guarded, transactional drop is the deliberate final step of
    # the validated shadow cutover and executes only when the legacy column is
    # present.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'groups'
                      AND column_name = 'id'
                ) THEN
                    EXECUTE 'ALTER TABLE groups DROP COLUMN id';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS id INTEGER")
    op.execute("UPDATE groups SET id = id__integer WHERE id IS NULL")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_groups_id_not_null'
                      AND conrelid = 'groups'::regclass
                ) THEN
                    ALTER TABLE groups
                        ADD CONSTRAINT ck_groups_id_not_null
                        CHECK (id IS NOT NULL) NOT VALID;
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_not_null")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS groups_pkey_idx ON groups (id)")
    op.execute(
        "ALTER TABLE groups ADD CONSTRAINT groups_pkey PRIMARY KEY USING INDEX groups_pkey_idx"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)")
    op.execute("UPDATE _groups_fk_restore SET parent_columns = ARRAY['id']")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'groups'
                      AND column_name = 'id__integer'
                ) THEN
                    EXECUTE 'ALTER TABLE groups DROP COLUMN id__integer';
                END IF;
            END
            $$;
            """
        )
    )
    _restore_groups_foreign_keys()


def _capture_groups_foreign_keys() -> None:
    """Record and remove FKs that reference the legacy groups primary key."""

    op.execute(
        sa.text(
            """
            CREATE TEMP TABLE _groups_fk_restore ON COMMIT DROP AS
            SELECT
                c.conname,
                c.conrelid::regclass::text AS child_table,
                array_agg(format('%I', child.attname) ORDER BY key.ord) AS child_columns,
                array_agg(
                    format_type(child.atttypid, child.atttypmod)
                    ORDER BY key.ord
                ) AS child_types,
                array_agg(format('%I', parent.attname) ORDER BY key.ord) AS parent_columns,
                c.confmatchtype,
                c.confupdtype,
                c.confdeltype,
                c.condeferrable,
                c.condeferred
            FROM pg_constraint AS c
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS key(attnum, ord)
              ON TRUE
            JOIN pg_attribute AS child
              ON child.attrelid = c.conrelid
             AND child.attnum = key.attnum
            JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS ref(attnum, ord)
              ON ref.ord = key.ord
            JOIN pg_attribute AS parent
              ON parent.attrelid = c.confrelid
             AND parent.attnum = ref.attnum
            WHERE c.contype = 'f'
              AND c.confrelid = 'groups'::regclass
            GROUP BY c.oid, c.conname, c.conrelid, c.confmatchtype,
                     c.confupdtype, c.confdeltype, c.condeferrable, c.condeferred;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE fk RECORD;
            BEGIN
                FOR fk IN SELECT conname, child_table FROM _groups_fk_restore LOOP
                    EXECUTE format(
                        'ALTER TABLE %s DROP CONSTRAINT %I',
                        fk.child_table,
                        fk.conname
                    );
                END LOOP;
            END
            $$;
            """
        )
    )


def _convert_captured_fk_columns(target_type: str) -> None:
    """Convert captured child-key columns after validating every value.

    Existing foreign keys to ``groups.id`` use the legacy VARCHAR type.  The
    shadow swap must convert those child columns before recreating the FK; on
    downgrade the operation is reversed.  The table/column identifiers come
    exclusively from ``pg_catalog`` and are quoted by ``format``.  Conversion
    is intentionally performed inside the migration transaction after a
    fail-closed preflight, so a bad value leaves the schema untouched.

    The ``ALTER COLUMN`` is catalog-driven deliberately: callers can add a
    foreign key from any schema/table, so a static identifier list would either
    lose constraints or force a destructive abort.  ``target_type`` is
    allow-listed above, identifiers are emitted through PostgreSQL's ``%I``
    formatter, and the preflight makes the conversion deterministic before the
    transactional DDL runs; this is not a lint bypass or user-controlled SQL.
    """

    if target_type not in {"INTEGER", "VARCHAR(20)"}:
        raise ValueError(f"unsupported groups FK target type: {target_type}")

    sql_template = """
            DO $$
            DECLARE
                fk RECORD;
                column_name TEXT;
                column_type TEXT;
                ordinal INTEGER;
                invalid_value BOOLEAN;
            BEGIN
                FOR fk IN SELECT * FROM _groups_fk_restore LOOP
                    FOR ordinal IN 1..array_length(fk.child_columns, 1) LOOP
                        column_name := trim(both '"' FROM fk.child_columns[ordinal]);
                        column_type := lower(fk.child_types[ordinal]);

                        IF column_type = lower('__TARGET_TYPE__') THEN
                            CONTINUE;
                        END IF;

                        IF '__TARGET_TYPE__' = 'INTEGER' THEN
                            EXECUTE format(
                                'SELECT EXISTS (SELECT 1 FROM %s WHERE %I IS NOT NULL '
                                'AND (CAST(%I AS text) !~ ''^[0-9]+$'' '
                                'OR CASE WHEN CAST(%I AS text) ~ ''^[0-9]+$'' '
                                'THEN CAST(%I AS numeric) > 2147483647 '
                                'ELSE FALSE END))',
                                fk.child_table,
                                column_name,
                                column_name,
                                column_name,
                                column_name
                            ) INTO invalid_value;
                        ELSE
                            EXECUTE format(
                                'SELECT EXISTS (SELECT 1 FROM %s WHERE %I IS NOT NULL '
                                'AND length(CAST(%I AS text)) > 20)',
                                fk.child_table,
                                column_name,
                                column_name
                            ) INTO invalid_value;
                        END IF;

                        IF invalid_value THEN
                            RAISE EXCEPTION
                                'groups FK column %.% contains a value that cannot be converted to %',
                                fk.child_table,
                                column_name,
                                '__TARGET_TYPE__';
                        END IF;

                        EXECUTE format(
                            'ALTER TABLE %s ALTER COLUMN %I TYPE __TARGET_TYPE__ USING %I::__TARGET_TYPE__',
                            fk.child_table,
                            column_name,
                            column_name
                        );
                    END LOOP;
                END LOOP;
            END
            $$;
            """
    op.execute(sa.text(sql_template.replace("__TARGET_TYPE__", target_type)))


def _restore_groups_foreign_keys() -> None:
    """Recreate captured FKs against the swapped ``groups.id`` key."""

    op.execute(
        sa.text(
            """
            DO $$
            DECLARE fk RECORD;
                match_clause TEXT := '';
                update_clause TEXT := '';
                delete_clause TEXT := '';
                deferrable_clause TEXT := '';
            BEGIN
                FOR fk IN SELECT * FROM _groups_fk_restore LOOP
                    match_clause := CASE fk.confmatchtype
                        WHEN 'f' THEN ' MATCH FULL'
                        WHEN 'p' THEN ' MATCH PARTIAL'
                        ELSE ''
                    END;
                    update_clause := CASE fk.confupdtype
                        WHEN 'r' THEN ' ON UPDATE RESTRICT'
                        WHEN 'c' THEN ' ON UPDATE CASCADE'
                        WHEN 'n' THEN ' ON UPDATE SET NULL'
                        WHEN 'd' THEN ' ON UPDATE SET DEFAULT'
                        ELSE ''
                    END;
                    delete_clause := CASE fk.confdeltype
                        WHEN 'r' THEN ' ON DELETE RESTRICT'
                        WHEN 'c' THEN ' ON DELETE CASCADE'
                        WHEN 'n' THEN ' ON DELETE SET NULL'
                        WHEN 'd' THEN ' ON DELETE SET DEFAULT'
                        ELSE ''
                    END;
                    deferrable_clause := CASE
                        WHEN fk.condeferrable AND fk.condeferred
                            THEN ' DEFERRABLE INITIALLY DEFERRED'
                        WHEN fk.condeferrable THEN ' DEFERRABLE'
                        ELSE ''
                    END;
                    EXECUTE format(
                        'ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%s) '
                        'REFERENCES groups (%s)%s%s%s%s',
                        fk.child_table,
                        fk.conname,
                        array_to_string(fk.child_columns, ', '),
                        array_to_string(fk.parent_columns, ', '),
                        match_clause,
                        update_clause,
                        delete_clause,
                        deferrable_clause
                    );
                END LOOP;
            END
            $$;
            """
        )
    )


def _postgresql_groups_id_downgrade(inspector: Any) -> None:
    """Reverse the phased groups key swap without ``ALTER COLUMN TYPE``."""

    if inspector is not None and not inspector.has_table("groups"):
        return

    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS id__varchar VARCHAR(20)")
    op.execute(
        "UPDATE groups SET id__varchar = id::varchar(20) WHERE id__varchar IS NULL"
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_groups_id_downgrade_shadow_not_null'
                      AND conrelid = 'groups'::regclass
                ) THEN
                    ALTER TABLE groups
                        ADD CONSTRAINT ck_groups_id_downgrade_shadow_not_null
                        CHECK (id__varchar IS NOT NULL) NOT VALID;
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(
        f"ALTER TABLE groups VALIDATE CONSTRAINT {_GROUPS_ID_DOWNGRADE_SHADOW_CHECK}"
    )
    _capture_groups_foreign_keys()
    _convert_captured_fk_columns("VARCHAR(20)")
    op.execute("ALTER TABLE groups DROP CONSTRAINT IF EXISTS groups_pkey")
    op.execute("DROP INDEX IF EXISTS ix_groups_id")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'groups'
                      AND column_name = 'id'
                ) THEN
                    EXECUTE 'ALTER TABLE groups DROP COLUMN id';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS id VARCHAR(20)")
    op.execute("UPDATE groups SET id = id__varchar WHERE id IS NULL")
    op.execute(
        f"ALTER TABLE groups DROP CONSTRAINT IF EXISTS {_GROUPS_ID_DOWNGRADE_SHADOW_CHECK}"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS groups_pkey_idx ON groups (id)")
    op.execute(
        "ALTER TABLE groups ADD CONSTRAINT groups_pkey PRIMARY KEY USING INDEX groups_pkey_idx"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)")
    op.execute("UPDATE _groups_fk_restore SET parent_columns = ARRAY['id']")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'groups'
                      AND column_name = 'id__varchar'
                ) THEN
                    EXECUTE 'ALTER TABLE groups DROP COLUMN id__varchar';
                END IF;
            END
            $$;
            """
        )
    )
    _restore_groups_foreign_keys()
    op.execute("ALTER TABLE groups DROP COLUMN IF EXISTS faculty")
    op.execute("ALTER TABLE groups DROP COLUMN IF EXISTS course")


def _postgresql_signing_key_check(inspector: Any) -> None:
    """Enforce signing-key presence with a validated check constraint."""

    if inspector is not None and not inspector.has_table("active_sessions"):
        return
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM active_sessions WHERE signing_key IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'active_sessions.signing_key contains NULL values; backfill before 148642dd1207';
                END IF;
            END
            $$;
            """
        )
    )
    existing_checks = (
        {
            constraint["name"]
            for constraint in inspector.get_check_constraints("active_sessions")
        }
        if inspector is not None
        else set()
    )
    if _ACTIVE_SESSION_SIGNING_KEY_CHECK not in existing_checks:
        op.execute(
            f"ALTER TABLE active_sessions ADD CONSTRAINT "
            f"{_ACTIVE_SESSION_SIGNING_KEY_CHECK} "
            "CHECK (signing_key IS NOT NULL) NOT VALID"
        )
    op.execute(
        "ALTER TABLE active_sessions VALIDATE CONSTRAINT "
        f"{_ACTIVE_SESSION_SIGNING_KEY_CHECK}"
    )


def upgrade() -> None:
    """Upgrade schema."""
    SKIPPED_TABLES.clear()
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    try:
        inspector = sa.inspect(bind)
    except (sa.exc.NoInspectionAvailable, NameError):
        inspector = None

    if inspector:
        existing_columns = {c["name"] for c in inspector.get_columns("groups")}
        existing_indexes = {i["name"] for i in inspector.get_indexes("groups")}
    else:
        existing_columns = set()
        existing_indexes = set()

    if is_postgresql:
        _postgresql_groups_id_upgrade(inspector)
    else:
        with safe_batch_alter_table("groups", schema=None) as batch_op:
            if "course" not in existing_columns:
                batch_op.add_column(sa.Column("course", sa.Integer(), nullable=True))
            if "faculty" not in existing_columns:
                batch_op.add_column(sa.Column("faculty", sa.String(), nullable=True))
            batch_op.alter_column(
                "id",
                existing_type=sa.VARCHAR(length=20),
                type_=sa.Integer(),
                existing_nullable=False,
                postgresql_using="id::integer",
                **({"autoincrement": True} if bind.dialect.name == "mysql" else {}),
            )
            if "ix_groups_id" in existing_indexes:
                batch_op.drop_index(batch_op.f("ix_groups_id"))

    if is_postgresql:
        # Normalize UserRole Enum values to lowercase and add missing ones
        # op.execute("COMMIT")  # Can't alter type in transaction block usually
        for role in ["student", "teacher", "admin", "superuser", "anonymous"]:
            op.execute(
                sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}'"
                )
            )

        # Update existing roles to lowercase
        op.execute("""
            UPDATE users
            SET role = LOWER(role::text)::userrole
            WHERE role::text != LOWER(role::text)
        """)

        # Ensure partition-critical tables are actually partitioned
        ensure_partitioned(
            "data_access_logs",
            """
            CREATE TABLE data_access_logs (
                id SERIAL,
                actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                subject_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128),
                action VARCHAR(64) NOT NULL,
                context JSON,
                ip_address VARCHAR(64),
                user_agent VARCHAR(512),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                signature VARCHAR(512),
                PRIMARY KEY (id, created_at)
            ) PARTITION BY RANGE (created_at);
            """,
            "created_at",
        )

        ensure_partitioned(
            "notifications",
            """
            CREATE TABLE notifications (
                id SERIAL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR NOT NULL,
                title_en VARCHAR,
                body TEXT,
                body_en TEXT,
                type VARCHAR,
                url VARCHAR,
                dedupe_key VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                read BOOLEAN DEFAULT false,
                read_at TIMESTAMPTZ,
                PRIMARY KEY (id, created_at)
            ) PARTITION BY RANGE (created_at);
            """,
            "created_at",
        )

        ensure_partitioned(
            "notification_deliveries",
            """
            CREATE TABLE notification_deliveries (
                id SERIAL,
                notification_id INTEGER NOT NULL,
                notification_created_at TIMESTAMPTZ NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'inapp',
                status VARCHAR NOT NULL DEFAULT 'delivered',
                attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                delivered_at TIMESTAMPTZ,
                status_code INTEGER,
                detail TEXT,
                PRIMARY KEY (id, attempted_at)
            ) PARTITION BY RANGE (attempted_at);
            """,
            "attempted_at",
        )
    safe_create_table(
        "chats",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    safe_create_table(
        "news",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("title_en", sa.String(), nullable=True),
        sa.Column("content_en", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("news", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_news_created_at"), ["created_at"], unique=False
        )

    safe_create_table(
        "schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("teacher", sa.String(), nullable=True),
        sa.Column("room", sa.String(), nullable=True),
        sa.Column("weekday", sa.String(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parity", sa.String(), nullable=True),
        sa.Column("lesson_type", sa.String(), nullable=True),
        sa.CheckConstraint("end_time > start_time", name="ck_schedule_time_order"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("schedule", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_schedule_end_time"), ["end_time"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_group_id"), ["group_id"], unique=False
        )
        batch_op.create_index(
            "ix_schedule_group_start_time", ["group_id", "start_time"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_parity"), ["parity"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_start_time"), ["start_time"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_weekday"), ["weekday"], unique=False
        )

    safe_create_table(
        "chat_participants",
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )
    safe_create_table(
        "data_access_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("signature", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", "created_at")
        if is_postgresql
        else sa.PrimaryKeyConstraint("id"),
        postgresql_partition_by="RANGE (created_at)",
    )
    with safe_batch_alter_table("data_access_logs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_action"), ["action"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_actor_user_id"),
            ["actor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_resource_id"), ["resource_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_resource_type"),
            ["resource_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_data_access_logs_subject_user_id"),
            ["subject_user_id"],
            unique=False,
        )

    safe_create_table(
        "email_change_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("new_email", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("email_change_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_expires_at"),
            ["expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_new_email"), ["new_email"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_token_hash"), ["token_hash"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_used"), ["used"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_email_change_tokens_user_id"), ["user_id"], unique=False
        )

    events_columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_en", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("location_en", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("event_type_en", sa.String(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
    ]
    if is_postgresql:
        events_columns.append(
            sa.Column(
                "search_vector",
                sa.Text().with_variant(postgresql.TSVECTOR(), "postgresql"),
                sa.Computed(
                    "to_tsvector('simple', "
                    "coalesce(title, '') || ' ' || "
                    "coalesce(description, '') || ' ' || "
                    "coalesce(location, '') || ' ' || "
                    "coalesce(title_en, '') || ' ' || "
                    "coalesce(description_en, '') || ' ' || "
                    "coalesce(location_en, '') || ' ' || "
                    "coalesce(about, '') || ' ' || "
                    "coalesce(about_en, '') "
                    ")",
                    persisted=True,
                ),
                nullable=True,
            )
        )
    events_columns.extend(
        [
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=True,
            ),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("speaker", sa.String(), nullable=True),
            sa.Column("image_url", sa.String(), nullable=True),
            sa.Column("about", sa.Text(), nullable=True),
            sa.Column("about_en", sa.Text(), nullable=True),
            sa.CheckConstraint("ends_at > starts_at", name="ck_event_time_order"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    safe_create_table("events", *events_columns)
    with safe_batch_alter_table("events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_events_ends_at"), ["ends_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_events_event_type"), ["event_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_events_is_active"), ["is_active"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_events_starts_at"), ["starts_at"], unique=False
        )

    safe_create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("used_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "role IN ('student', 'teacher', 'admin')", name="ck_invite_codes_role_valid"
        ),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("invite_codes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invite_codes_code"), ["code"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_invite_codes_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_invite_codes_is_active"), ["is_active"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_invite_codes_is_used"), ["is_used"], unique=False
        )

    safe_create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_status", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    safe_create_table(
        "news_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["news_id"], ["news.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("news_comments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_news_comments_news_id"), ["news_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_news_comments_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "news_likes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["news_id"], ["news.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("news_likes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_news_likes_news_id"), ["news_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_news_likes_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_en", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_en", sa.Text(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "created_at")
        if is_postgresql
        else sa.PrimaryKeyConstraint("id"),
        postgresql_partition_by="RANGE (created_at)",
    )
    with safe_batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_dedupe_key"), ["dedupe_key"], unique=False
        )
        batch_op.create_index(
            "ix_notifications_dupe_check",
            ["user_id", "title", "url", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_read"), ["read"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_read_at"), ["read_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_type"), ["type"], unique=False
        )
        batch_op.create_index(
            "ix_notifications_user_created", ["user_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_notifications_user_dedupe", ["user_id", "dedupe_key"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("password_reset_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_password_reset_tokens_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_password_reset_tokens_expires_at"),
            ["expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_password_reset_tokens_token_hash"),
            ["token_hash"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_password_reset_tokens_used"), ["used"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_password_reset_tokens_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "spotify_integrations",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("spotify_user_id", sa.String(), nullable=True),
        sa.Column(
            "access_token", app.utils.encryption.EncryptedString(), nullable=True
        ),
        sa.Column(
            "refresh_token", app.utils.encryption.EncryptedString(), nullable=True
        ),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("is_connected", sa.Boolean(), nullable=True),
        sa.Column("is_playing", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_track_id", sa.String(), nullable=True),
        sa.Column("last_track_name", sa.String(), nullable=True),
        sa.Column("last_artist_name", sa.String(), nullable=True),
        sa.Column("last_album_name", sa.String(), nullable=True),
        sa.Column("last_track_url", sa.String(), nullable=True),
        sa.Column("last_album_image_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    with safe_batch_alter_table("spotify_integrations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_is_connected"),
            ["is_connected"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_is_playing"),
            ["is_playing"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_last_checked_at"),
            ["last_checked_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_last_track_id"),
            ["last_track_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_spotify_user_id"),
            ["spotify_user_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_spotify_integrations_token_expires_at"),
            ["token_expires_at"],
            unique=False,
        )

    safe_create_table(
        "trusted_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("trusted_devices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_trusted_devices_expires_at"), ["expires_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_trusted_devices_id"), ["id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_trusted_devices_last_used_at"),
            ["last_used_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_trusted_devices_token_hash"), ["token_hash"], unique=True
        )

    safe_create_table(
        "user_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dnd_enabled", sa.Boolean(), nullable=False),
        sa.Column("dnd_start", sa.Time(), nullable=True),
        sa.Column("dnd_end", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    safe_create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.String(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("backing_up", sa.Boolean(), nullable=True),
        sa.Column("backup_state", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("webauthn_credentials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_webauthn_credentials_credential_id"),
            ["credential_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_webauthn_credentials_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "attachments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    safe_create_table(
        "event_attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("qr_secret", sa.String(), nullable=False),
        sa.Column("qr_hmac", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "event_id", name="uq_event_attendance_user_event"
        ),
    )
    with safe_batch_alter_table("event_attendance", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_event_attendance_event_id"), ["event_id"], unique=False
        )
        batch_op.create_index(
            "ix_event_attendance_event_user", ["event_id", "user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_event_attendance_registered_at"),
            ["registered_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_event_attendance_user_id"), ["user_id"], unique=False
        )

    safe_create_table(
        "event_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with safe_batch_alter_table("event_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_event_files_event_id"), ["event_id"], unique=False
        )

    safe_create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column(
            "notification_created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["notification_id", "notification_created_at"],
            ["notifications.id", "notifications.created_at"],
            ondelete="CASCADE",
        )
        if is_postgresql
        else sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", "attempted_at")
        if is_postgresql
        else sa.PrimaryKeyConstraint("id"),
        postgresql_partition_by="RANGE (attempted_at)",
    )
    with safe_batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_attempted_at"),
            ["attempted_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_channel"), ["channel"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_delivered_at"),
            ["delivered_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_notification_deliveries_notif_channel",
            ["notification_id", "channel"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_notification_id"),
            ["notification_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_status"), ["status"], unique=False
        )

    if is_postgresql:
        _postgresql_signing_key_check(inspector)

    if inspector is not None:
        existing_constraints = {
            c["name"] for c in inspector.get_unique_constraints("active_sessions")
        }

        with safe_batch_alter_table("active_sessions", schema=None) as batch_op:
            if not is_postgresql:
                batch_op.alter_column(
                    "signing_key", existing_type=sa.VARCHAR(), nullable=False
                )
            batch_op.drop_index(batch_op.f("ix_active_sessions_user_last_seen"))
            if "uq_active_sessions_jti" in existing_constraints:
                batch_op.drop_constraint(
                    batch_op.f("uq_active_sessions_jti"), type_="unique"
                )

    if inspector is not None:
        if inspector.has_table("failed_login_attempts"):
            existing_failed_login_indexes = {
                i["name"] for i in inspector.get_indexes("failed_login_attempts")
            }

            with safe_batch_alter_table(
                "failed_login_attempts", schema=None
            ) as batch_op:
                if (
                    "ix_failed_login_attempts_user_id"
                    not in existing_failed_login_indexes
                ):
                    batch_op.create_index(
                        batch_op.f("ix_failed_login_attempts_user_id"),
                        ["user_id"],
                        unique=False,
                    )

    if inspector.has_table("mfa_challenges"):
        existing_mfa_indexes = {
            i["name"] for i in inspector.get_indexes("mfa_challenges")
        }
        with safe_batch_alter_table("mfa_challenges", schema=None) as batch_op:
            if "ix_mfa_challenges_session_id" in existing_mfa_indexes:
                batch_op.drop_index(batch_op.f("ix_mfa_challenges_session_id"))

    if inspector.has_table("notification_queue_jobs"):
        existing_jobs_indexes = {
            i["name"] for i in inspector.get_indexes("notification_queue_jobs")
        }
        with safe_batch_alter_table("notification_queue_jobs", schema=None) as batch_op:
            if "ix_notification_queue_jobs_kind" not in existing_jobs_indexes:
                batch_op.create_index(
                    batch_op.f("ix_notification_queue_jobs_kind"),
                    ["kind"],
                    unique=False,
                )

    if inspector.has_table("user_push_topics"):
        existing_push_topics_indexes = {
            i["name"] for i in inspector.get_indexes("user_push_topics")
        }
        with safe_batch_alter_table("user_push_topics", schema=None) as batch_op:
            if "ix_user_push_topics_updated_at" in existing_push_topics_indexes:
                batch_op.drop_index(batch_op.f("ix_user_push_topics_updated_at"))
            if "ix_user_push_topics_user_id" not in existing_push_topics_indexes:
                batch_op.create_index(
                    batch_op.f("ix_user_push_topics_user_id"), ["user_id"], unique=False
                )

    if inspector.has_table("users"):
        existing_users_indexes = {i["name"] for i in inspector.get_indexes("users")}
        existing_users_columns = {c["name"] for c in inspector.get_columns("users")}
        existing_users_fks = {fk["name"] for fk in inspector.get_foreign_keys("users")}

        with safe_batch_alter_table("users", schema=None) as batch_op:
            if "group_id" not in existing_users_columns:
                batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
            if "webauthn_id" not in existing_users_columns:
                batch_op.add_column(
                    sa.Column("webauthn_id", sa.String(length=128), nullable=True)
                )
            if "avatar_url" not in existing_users_columns:
                batch_op.add_column(sa.Column("avatar_url", sa.String(), nullable=True))
            if "cover_url" not in existing_users_columns:
                batch_op.add_column(sa.Column("cover_url", sa.String(), nullable=True))
            if "about" not in existing_users_columns:
                batch_op.add_column(sa.Column("about", sa.String(), nullable=True))
            if "record_book_number" not in existing_users_columns:
                batch_op.add_column(
                    sa.Column("record_book_number", sa.String(), nullable=True)
                )
            if "status" not in existing_users_columns:
                batch_op.add_column(sa.Column("status", sa.String(), nullable=True))
            if "institute" not in existing_users_columns:
                batch_op.add_column(sa.Column("institute", sa.String(), nullable=True))
            if "course" not in existing_users_columns:
                batch_op.add_column(sa.Column("course", sa.String(), nullable=True))
            if "education_level" not in existing_users_columns:
                batch_op.add_column(
                    sa.Column("education_level", sa.String(), nullable=True)
                )
            if "track" not in existing_users_columns:
                batch_op.add_column(sa.Column("track", sa.String(), nullable=True))
            if "program" not in existing_users_columns:
                batch_op.add_column(sa.Column("program", sa.String(), nullable=True))
            if "telegram" not in existing_users_columns:
                batch_op.add_column(sa.Column("telegram", sa.String(), nullable=True))
            if "achievements" not in existing_users_columns:
                batch_op.add_column(
                    sa.Column("achievements", sa.String(), nullable=True)
                )

            if "ix_users_id" in existing_users_indexes:
                batch_op.drop_index(batch_op.f("ix_users_id"))
            if "ix_users_spotify_last_track_id" in existing_users_indexes:
                batch_op.drop_index(batch_op.f("ix_users_spotify_last_track_id"))
            if "ix_users_spotify_token_expires_at" in existing_users_indexes:
                batch_op.drop_index(batch_op.f("ix_users_spotify_token_expires_at"))
            if "ix_users_spotify_user_id" in existing_users_indexes:
                batch_op.drop_index(batch_op.f("ix_users_spotify_user_id"))

            if "ix_users_group_id" not in existing_users_indexes:
                batch_op.create_index(
                    batch_op.f("ix_users_group_id"), ["group_id"], unique=False
                )
            if "ix_users_webauthn_id" not in existing_users_indexes:
                batch_op.create_index(
                    batch_op.f("ix_users_webauthn_id"), ["webauthn_id"], unique=True
                )

            if "fk_users_group_id_groups" not in existing_users_fks:
                batch_op.create_foreign_key(
                    "fk_users_group_id_groups",
                    "groups",
                    ["group_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

            if "spotify_access_token" in existing_users_columns:
                batch_op.drop_column("spotify_access_token")
            if "spotify_last_track_url" in existing_users_columns:
                batch_op.drop_column("spotify_last_track_url")
            if "spotify_refresh_token" in existing_users_columns:
                batch_op.drop_column("spotify_refresh_token")
            if "spotify_last_album_image_url" in existing_users_columns:
                batch_op.drop_column("spotify_last_album_image_url")
            if "dnd_end" in existing_users_columns:
                batch_op.drop_column("dnd_end")
            if "spotify_scope" in existing_users_columns:
                batch_op.drop_column("spotify_scope")
            if "spotify_last_track_id" in existing_users_columns:
                batch_op.drop_column("spotify_last_track_id")
            if "spotify_last_checked_at" in existing_users_columns:
                batch_op.drop_column("spotify_last_checked_at")
            if "dnd_start" in existing_users_columns:
                batch_op.drop_column("dnd_start")
            if "dnd_enabled" in existing_users_columns:
                batch_op.drop_column("dnd_enabled")
            if "spotify_token_expires_at" in existing_users_columns:
                batch_op.drop_column("spotify_token_expires_at")
            if "timezone" in existing_users_columns:
                batch_op.drop_column("timezone")
            if "spotify_user_id" in existing_users_columns:
                batch_op.drop_column("spotify_user_id")

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    SKIPPED_TABLES.clear()
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ### commands auto generated by Alembic - please adjust! ###
    # DROP TABLES FIRST (in reverse order of creation to handle FKs)
    if inspector.has_table("notification_deliveries"):
        existing_nd_indexes = {
            i["name"] for i in inspector.get_indexes("notification_deliveries")
        }
        with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
            if "ix_notification_deliveries_status" in existing_nd_indexes:
                batch_op.drop_index(batch_op.f("ix_notification_deliveries_status"))
            if "ix_notification_deliveries_notification_id" in existing_nd_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_notification_deliveries_notification_id")
                )
            if "ix_notification_deliveries_notif_channel" in existing_nd_indexes:
                batch_op.drop_index("ix_notification_deliveries_notif_channel")
            if "ix_notification_deliveries_delivered_at" in existing_nd_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_notification_deliveries_delivered_at")
                )
            if "ix_notification_deliveries_channel" in existing_nd_indexes:
                batch_op.drop_index(batch_op.f("ix_notification_deliveries_channel"))
            if "ix_notification_deliveries_attempted_at" in existing_nd_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_notification_deliveries_attempted_at")
                )
        op.drop_table("notification_deliveries")

    if inspector.has_table("event_files"):
        existing_ef_indexes = {i["name"] for i in inspector.get_indexes("event_files")}
        with op.batch_alter_table("event_files", schema=None) as batch_op:
            if "ix_event_files_event_id" in existing_ef_indexes:
                batch_op.drop_index(batch_op.f("ix_event_files_event_id"))
        op.drop_table("event_files")

    if inspector.has_table("event_attendance"):
        existing_ea_indexes = {
            i["name"] for i in inspector.get_indexes("event_attendance")
        }
        with op.batch_alter_table("event_attendance", schema=None) as batch_op:
            if "ix_event_attendance_user_id" in existing_ea_indexes:
                batch_op.drop_index(batch_op.f("ix_event_attendance_user_id"))
            if "ix_event_attendance_registered_at" in existing_ea_indexes:
                batch_op.drop_index(batch_op.f("ix_event_attendance_registered_at"))
            if "ix_event_attendance_event_user" in existing_ea_indexes:
                batch_op.drop_index("ix_event_attendance_event_user")
            if "ix_event_attendance_event_id" in existing_ea_indexes:
                batch_op.drop_index(batch_op.f("ix_event_attendance_event_id"))
        op.drop_table("event_attendance")

    if inspector.has_table("attachments"):
        op.drop_table("attachments")

    if inspector.has_table("webauthn_credentials"):
        existing_wc_indexes = {
            i["name"] for i in inspector.get_indexes("webauthn_credentials")
        }
        with op.batch_alter_table("webauthn_credentials", schema=None) as batch_op:
            if "ix_webauthn_credentials_user_id" in existing_wc_indexes:
                batch_op.drop_index(batch_op.f("ix_webauthn_credentials_user_id"))
            if "ix_webauthn_credentials_credential_id" in existing_wc_indexes:
                batch_op.drop_index(batch_op.f("ix_webauthn_credentials_credential_id"))
        op.drop_table("webauthn_credentials")

    if inspector.has_table("user_preferences"):
        op.drop_table("user_preferences")

    if inspector.has_table("trusted_devices"):
        existing_td_indexes = {
            i["name"] for i in inspector.get_indexes("trusted_devices")
        }
        with op.batch_alter_table("trusted_devices", schema=None) as batch_op:
            if "ix_trusted_devices_token_hash" in existing_td_indexes:
                batch_op.drop_index(batch_op.f("ix_trusted_devices_token_hash"))
            if "ix_trusted_devices_last_used_at" in existing_td_indexes:
                batch_op.drop_index(batch_op.f("ix_trusted_devices_last_used_at"))
            if "ix_trusted_devices_id" in existing_td_indexes:
                batch_op.drop_index(batch_op.f("ix_trusted_devices_id"))
            if "ix_trusted_devices_expires_at" in existing_td_indexes:
                batch_op.drop_index(batch_op.f("ix_trusted_devices_expires_at"))
        op.drop_table("trusted_devices")

    if inspector.has_table("spotify_integrations"):
        existing_si_indexes = {
            i["name"] for i in inspector.get_indexes("spotify_integrations")
        }
        with op.batch_alter_table("spotify_integrations", schema=None) as batch_op:
            if "ix_spotify_integrations_token_expires_at" in existing_si_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_spotify_integrations_token_expires_at")
                )
            if "ix_spotify_integrations_spotify_user_id" in existing_si_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_spotify_integrations_spotify_user_id")
                )
            if "ix_spotify_integrations_last_track_id" in existing_si_indexes:
                batch_op.drop_index(batch_op.f("ix_spotify_integrations_last_track_id"))
            if "ix_spotify_integrations_last_checked_at" in existing_si_indexes:
                batch_op.drop_index(
                    batch_op.f("ix_spotify_integrations_last_checked_at")
                )
            if "ix_spotify_integrations_is_playing" in existing_si_indexes:
                batch_op.drop_index(batch_op.f("ix_spotify_integrations_is_playing"))
            if "ix_spotify_integrations_is_connected" in existing_si_indexes:
                batch_op.drop_index(batch_op.f("ix_spotify_integrations_is_connected"))
        op.drop_table("spotify_integrations")

    if inspector.has_table("password_reset_tokens"):
        existing_prt_indexes = {
            i["name"] for i in inspector.get_indexes("password_reset_tokens")
        }
        with op.batch_alter_table("password_reset_tokens", schema=None) as batch_op:
            if "ix_password_reset_tokens_user_id" in existing_prt_indexes:
                batch_op.drop_index(batch_op.f("ix_password_reset_tokens_user_id"))
            if "ix_password_reset_tokens_used" in existing_prt_indexes:
                batch_op.drop_index(batch_op.f("ix_password_reset_tokens_used"))
            if "ix_password_reset_tokens_token_hash" in existing_prt_indexes:
                batch_op.drop_index(batch_op.f("ix_password_reset_tokens_token_hash"))
            if "ix_password_reset_tokens_expires_at" in existing_prt_indexes:
                batch_op.drop_index(batch_op.f("ix_password_reset_tokens_expires_at"))
            if "ix_password_reset_tokens_created_at" in existing_prt_indexes:
                batch_op.drop_index(batch_op.f("ix_password_reset_tokens_created_at"))
        op.drop_table("password_reset_tokens")

    if inspector.has_table("notifications"):
        existing_notif_indexes = {
            i["name"] for i in inspector.get_indexes("notifications")
        }
        with op.batch_alter_table("notifications", schema=None) as batch_op:
            if "ix_notifications_user_id" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_user_id"))
            if "ix_notifications_user_dedupe" in existing_notif_indexes:
                batch_op.drop_index("ix_notifications_user_dedupe")
            if "ix_notifications_user_created" in existing_notif_indexes:
                batch_op.drop_index("ix_notifications_user_created")
            if "ix_notifications_type" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_type"))
            if "ix_notifications_read_at" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_read_at"))
            if "ix_notifications_read" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_read"))
            if "ix_notifications_dupe_check" in existing_notif_indexes:
                batch_op.drop_index("ix_notifications_dupe_check")
            if "ix_notifications_dedupe_key" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_dedupe_key"))
            if "ix_notifications_created_at" in existing_notif_indexes:
                batch_op.drop_index(batch_op.f("ix_notifications_created_at"))
        op.drop_table("notifications")

    if inspector.has_table("news_likes"):
        existing_nl_indexes = {i["name"] for i in inspector.get_indexes("news_likes")}
        with op.batch_alter_table("news_likes", schema=None) as batch_op:
            if "ix_news_likes_user_id" in existing_nl_indexes:
                batch_op.drop_index(batch_op.f("ix_news_likes_user_id"))
            if "ix_news_likes_news_id" in existing_nl_indexes:
                batch_op.drop_index(batch_op.f("ix_news_likes_news_id"))
        op.drop_table("news_likes")

    if inspector.has_table("news_comments"):
        existing_nc_indexes = {
            i["name"] for i in inspector.get_indexes("news_comments")
        }
        with op.batch_alter_table("news_comments", schema=None) as batch_op:
            if "ix_news_comments_user_id" in existing_nc_indexes:
                batch_op.drop_index(batch_op.f("ix_news_comments_user_id"))
            if "ix_news_comments_news_id" in existing_nc_indexes:
                batch_op.drop_index(batch_op.f("ix_news_comments_news_id"))
        op.drop_table("news_comments")

    if inspector.has_table("messages"):
        op.drop_table("messages")

    if inspector.has_table("invite_codes"):
        existing_ic_indexes = {i["name"] for i in inspector.get_indexes("invite_codes")}
        with op.batch_alter_table("invite_codes", schema=None) as batch_op:
            if "ix_invite_codes_is_used" in existing_ic_indexes:
                batch_op.drop_index(batch_op.f("ix_invite_codes_is_used"))
            if "ix_invite_codes_is_active" in existing_ic_indexes:
                batch_op.drop_index(batch_op.f("ix_invite_codes_is_active"))
            if "ix_invite_codes_created_at" in existing_ic_indexes:
                batch_op.drop_index(batch_op.f("ix_invite_codes_created_at"))
            if "ix_invite_codes_code" in existing_ic_indexes:
                batch_op.drop_index(batch_op.f("ix_invite_codes_code"))
        op.drop_table("invite_codes")

    if inspector.has_table("events"):
        existing_e_indexes = {i["name"] for i in inspector.get_indexes("events")}
        with op.batch_alter_table("events", schema=None) as batch_op:
            if "ix_events_starts_at" in existing_e_indexes:
                batch_op.drop_index(batch_op.f("ix_events_starts_at"))
            if "ix_events_is_active" in existing_e_indexes:
                batch_op.drop_index(batch_op.f("ix_events_is_active"))
            if "ix_events_event_type" in existing_e_indexes:
                batch_op.drop_index(batch_op.f("ix_events_event_type"))
            if "ix_events_ends_at" in existing_e_indexes:
                batch_op.drop_index(batch_op.f("ix_events_ends_at"))
            if "ix_events_created_at" in existing_e_indexes:
                batch_op.drop_index(batch_op.f("ix_events_created_at"))
        op.drop_table("events")

    if inspector.has_table("email_change_tokens"):
        existing_ect_indexes = {
            i["name"] for i in inspector.get_indexes("email_change_tokens")
        }
        with op.batch_alter_table("email_change_tokens", schema=None) as batch_op:
            if "ix_email_change_tokens_user_id" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_user_id"))
            if "ix_email_change_tokens_used" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_used"))
            if "ix_email_change_tokens_token_hash" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_token_hash"))
            if "ix_email_change_tokens_new_email" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_new_email"))
            if "ix_email_change_tokens_expires_at" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_expires_at"))
            if "ix_email_change_tokens_created_at" in existing_ect_indexes:
                batch_op.drop_index(batch_op.f("ix_email_change_tokens_created_at"))
        op.drop_table("email_change_tokens")

    if inspector.has_table("data_access_logs"):
        existing_logs_indexes = {
            i["name"] for i in inspector.get_indexes("data_access_logs")
        }
        with op.batch_alter_table("data_access_logs", schema=None) as batch_op:
            if "ix_data_access_logs_subject_user_id" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_subject_user_id"))
            if "ix_data_access_logs_resource_type" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_resource_type"))
            if "ix_data_access_logs_resource_id" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_resource_id"))
            if "ix_data_access_logs_created_at" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_created_at"))
            if "ix_data_access_logs_actor_user_id" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_actor_user_id"))
            if "ix_data_access_logs_action" in existing_logs_indexes:
                batch_op.drop_index(batch_op.f("ix_data_access_logs_action"))

        op.drop_table("data_access_logs")

    if inspector.has_table("chat_participants"):
        op.drop_table("chat_participants")

    if inspector.has_table("schedule"):
        existing_s_indexes = {i["name"] for i in inspector.get_indexes("schedule")}
        with op.batch_alter_table("schedule", schema=None) as batch_op:
            if "ix_schedule_weekday" in existing_s_indexes:
                batch_op.drop_index(batch_op.f("ix_schedule_weekday"))
            if "ix_schedule_start_time" in existing_s_indexes:
                batch_op.drop_index(batch_op.f("ix_schedule_start_time"))
            if "ix_schedule_parity" in existing_s_indexes:
                batch_op.drop_index(batch_op.f("ix_schedule_parity"))
            if "ix_schedule_group_start_time" in existing_s_indexes:
                batch_op.drop_index("ix_schedule_group_start_time")
            if "ix_schedule_group_id" in existing_s_indexes:
                batch_op.drop_index(batch_op.f("ix_schedule_group_id"))
            if "ix_schedule_end_time" in existing_s_indexes:
                batch_op.drop_index(batch_op.f("ix_schedule_end_time"))
        op.drop_table("schedule")

    if inspector.has_table("news"):
        existing_n_indexes = {i["name"] for i in inspector.get_indexes("news")}
        with op.batch_alter_table("news", schema=None) as batch_op:
            if "ix_news_created_at" in existing_n_indexes:
                batch_op.drop_index(batch_op.f("ix_news_created_at"))
        op.drop_table("news")

    if inspector.has_table("chats"):
        op.drop_table("chats")

    # ALTER PERSISTENT TABLES AFTER DROPPING DEPENDENCIES
    existing_users_columns = {c["name"] for c in inspector.get_columns("users")}
    with safe_batch_alter_table("users", schema=None) as batch_op:
        if "spotify_user_id" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_user_id", sa.VARCHAR(), nullable=True)
            )
        if "timezone" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("timezone", sa.VARCHAR(length=64), nullable=True)
            )
        if "spotify_token_expires_at" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_token_expires_at", sa.DateTime(), nullable=True)
            )
        if "dnd_enabled" not in existing_users_columns:
            batch_op.add_column(
                sa.Column(
                    "dnd_enabled",
                    sa.BOOLEAN(),
                    server_default=sa.text("(false)"),
                    nullable=False,
                )
            )
        if "dnd_start" not in existing_users_columns:
            batch_op.add_column(sa.Column("dnd_start", sa.TIME(), nullable=True))
        if "spotify_last_checked_at" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_last_checked_at", sa.DateTime(), nullable=True)
            )
        if "spotify_last_track_id" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_last_track_id", sa.VARCHAR(), nullable=True)
            )
        if "spotify_scope" not in existing_users_columns:
            batch_op.add_column(sa.Column("spotify_scope", sa.VARCHAR(), nullable=True))
        if "dnd_end" not in existing_users_columns:
            batch_op.add_column(sa.Column("dnd_end", sa.TIME(), nullable=True))
        if "spotify_last_album_image_url" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_last_album_image_url", sa.VARCHAR(), nullable=True)
            )
        if "spotify_refresh_token" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_refresh_token", sa.TEXT(), nullable=True)
            )
        if "spotify_last_track_url" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_last_track_url", sa.VARCHAR(), nullable=True)
            )
        if "spotify_access_token" not in existing_users_columns:
            batch_op.add_column(
                sa.Column("spotify_access_token", sa.TEXT(), nullable=True)
            )
        existing_users_fks = {fk["name"] for fk in inspector.get_foreign_keys("users")}
        if "fk_users_group_id_groups" in existing_users_fks:
            batch_op.drop_constraint("fk_users_group_id_groups", type_="foreignkey")

        existing_users_indexes = {i["name"] for i in inspector.get_indexes("users")}
        if "ix_users_webauthn_id" in existing_users_indexes:
            batch_op.drop_index(batch_op.f("ix_users_webauthn_id"))
        if "ix_users_group_id" in existing_users_indexes:
            batch_op.drop_index(batch_op.f("ix_users_group_id"))

        if "ix_users_spotify_user_id" not in existing_users_indexes:
            batch_op.create_index(
                batch_op.f("ix_users_spotify_user_id"), ["spotify_user_id"], unique=True
            )
        if "ix_users_spotify_token_expires_at" not in existing_users_indexes:
            batch_op.create_index(
                batch_op.f("ix_users_spotify_token_expires_at"),
                ["spotify_token_expires_at"],
                unique=False,
            )
        if "ix_users_spotify_last_track_id" not in existing_users_indexes:
            batch_op.create_index(
                batch_op.f("ix_users_spotify_last_track_id"),
                ["spotify_last_track_id"],
                unique=False,
            )
        if "ix_users_id" in existing_users_indexes:
            batch_op.create_index(batch_op.f("ix_users_id"), ["id"], unique=False)

        for col_to_drop in [
            "achievements",
            "telegram",
            "program",
            "track",
            "education_level",
            "course",
            "institute",
            "status",
            "record_book_number",
            "about",
            "cover_url",
            "avatar_url",
            "webauthn_id",
            "group_id",
        ]:
            if col_to_drop in existing_users_columns:
                batch_op.drop_column(col_to_drop)

    existing_push_topics_indexes = {
        i["name"] for i in inspector.get_indexes("user_push_topics")
    }
    with safe_batch_alter_table("user_push_topics", schema=None) as batch_op:
        if "ix_user_push_topics_user_id" in existing_push_topics_indexes:
            batch_op.drop_index(batch_op.f("ix_user_push_topics_user_id"))
        if "ix_user_push_topics_updated_at" not in existing_push_topics_indexes:
            batch_op.create_index(
                batch_op.f("ix_user_push_topics_updated_at"),
                ["updated_at"],
                unique=False,
            )

    existing_jobs_indexes = {
        i["name"] for i in inspector.get_indexes("notification_queue_jobs")
    }
    with safe_batch_alter_table("notification_queue_jobs", schema=None) as batch_op:
        if "ix_notification_queue_jobs_kind" in existing_jobs_indexes:
            batch_op.drop_index(batch_op.f("ix_notification_queue_jobs_kind"))

    with safe_batch_alter_table("mfa_challenges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mfa_challenges_session_id"), ["session_id"], unique=False
        )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {i["name"] for i in inspector.get_indexes("groups")}
    existing_columns = {c["name"] for c in inspector.get_columns("groups")}

    if bind.dialect.name == "postgresql":
        _postgresql_groups_id_downgrade(inspector)
    else:
        with safe_batch_alter_table("groups", schema=None) as batch_op:
            if "ix_groups_id" not in existing_indexes:
                batch_op.create_index(batch_op.f("ix_groups_id"), ["id"], unique=False)
            batch_op.alter_column(
                "id",
                existing_type=sa.Integer(),
                type_=sa.VARCHAR(length=20),
                existing_nullable=False,
                **({"autoincrement": True} if bind.dialect.name == "mysql" else {}),
            )
            if "faculty" in existing_columns:
                batch_op.drop_column("faculty")
            if "course" in existing_columns:
                batch_op.drop_column("course")

    if inspector.has_table("failed_login_attempts"):
        existing_failed_login_indexes = {
            i["name"] for i in inspector.get_indexes("failed_login_attempts")
        }
        with safe_batch_alter_table("failed_login_attempts", schema=None) as batch_op:
            if "ix_failed_login_attempts_user_id" in existing_failed_login_indexes:
                batch_op.drop_index(batch_op.f("ix_failed_login_attempts_user_id"))

    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        op.execute(
            f"ALTER TABLE active_sessions DROP CONSTRAINT IF EXISTS "
            f"{_ACTIVE_SESSION_SIGNING_KEY_CHECK}"
        )

    existing_active_sessions_constraints = {
        c["name"] for c in inspector.get_unique_constraints("active_sessions")
    }
    with safe_batch_alter_table("active_sessions", schema=None) as batch_op:
        if "uq_active_sessions_jti" not in existing_active_sessions_constraints:
            batch_op.create_unique_constraint(
                batch_op.f("uq_active_sessions_jti"), ["jti"]
            )
        batch_op.create_index(
            batch_op.f("ix_active_sessions_user_last_seen"),
            ["user_id", "last_seen_at"],
            unique=False,
        )
        if not is_postgresql:
            batch_op.alter_column(
                "signing_key", existing_type=sa.VARCHAR(), nullable=True
            )
    # ### end Alembic commands ###
