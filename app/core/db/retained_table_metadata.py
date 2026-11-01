"""Migration-owned schemas retained after their runtime models were retired.

Keep these definitions in Alembic's target metadata until a separately reviewed
maintenance migration removes the physical tables. They remain subject to normal
autogenerate drift checks; application metadata must not reclaim them implicitly.
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

RETAINED_TABLES = frozenset({"user_stats", "vector_chunks"})

# The squashed MVP baseline is the single revision that owns every migration-owned
# object below. It replaces the historical revisions these annotations used to name.
_BASELINE_REVISION = "202611020000"

# The MVP baseline still owns these columns after the runtime
# models stopped mapping them. Keep their FK and index in Alembic metadata so
# later autogenerate checks do not propose destructive removals.
MIGRATION_OWNED_TENANT_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)
_MIGRATION_OWNED_TENANT_REVISION = _BASELINE_REVISION

# These indexes are created by the MVP baseline rather than runtime models.
# Register only indexes that the baseline creates for the selected dialect.
_MIGRATION_OWNED_HOT_INDEXES: tuple[
    tuple[str, str, tuple[str, ...], tuple[str, ...], str], ...
] = (
    (
        "ix_chat_participants_user_id_chat_id",
        "chat_participants",
        ("user_id", "chat_id"),
        (),
        _BASELINE_REVISION,
    ),
    (
        "ix_chat_participants_chat_id_user_id",
        "chat_participants",
        ("chat_id", "user_id"),
        (),
        _BASELINE_REVISION,
    ),
    (
        "ix_messages_unread_chat_sender",
        "messages",
        ("chat_id", "sender_id"),
        ("read_status",),
        _BASELINE_REVISION,
    ),
    (
        "idx_messages_chat_pagination_covering",
        "messages",
        ("chat_id", "created_at", "id"),
        ("sender_id", "read_status"),
        _BASELINE_REVISION,
    ),
    (
        "idx_news_comment_cursor",
        "news_comments",
        ("news_id", "created_at", "id"),
        (),
        _BASELINE_REVISION,
    ),
    (
        "ix_stored_events_pending_created",
        "stored_events",
        ("created_at", "id"),
        ("processed_at",),
        _BASELINE_REVISION,
    ),
    (
        "ix_stored_events_pending_aggregate_created",
        "stored_events",
        ("aggregate_id", "created_at", "id"),
        ("processed_at",),
        _BASELINE_REVISION,
    ),
    (
        "ix_stored_events_aggregate_uuid",
        "stored_events",
        ("aggregate_id_uuid", "sequence_number"),
        ("processed_at",),
        _BASELINE_REVISION,
    ),
)
_POSTGRESQL_ONLY_HOT_INDEXES = frozenset(
    {
        "ix_chat_participants_user_id_chat_id",
        "ix_chat_participants_chat_id_user_id",
        "ix_messages_unread_chat_sender",
        "idx_messages_chat_pagination_covering",
    }
)


def build_migration_metadata(
    runtime_metadata: sa.MetaData, *, dialect_name: str
) -> sa.MetaData:
    """Copy active schemas and add migration-owned schemas for one dialect."""
    if dialect_name not in {"postgresql", "sqlite"}:
        raise ValueError(f"Unsupported migration metadata dialect: {dialect_name}")
    conflicts = RETAINED_TABLES.intersection(runtime_metadata.tables)
    if conflicts:
        raise ValueError(
            f"Retained tables have competing runtime ownership: {sorted(conflicts)}"
        )
    metadata = sa.MetaData(naming_convention=runtime_metadata.naming_convention)
    for table in runtime_metadata.tables.values():
        table.to_metadata(metadata)
    _register_retained_tables(metadata)
    _register_migration_owned_tenant_columns(metadata)
    _register_migration_owned_hot_indexes(metadata, dialect_name=dialect_name)
    for name in RETAINED_TABLES:
        metadata.tables[name].info["retained_by_revision"] = _BASELINE_REVISION
    return metadata


def _register_migration_owned_tenant_columns(metadata: sa.MetaData) -> None:
    """Retain the tenant schema owned by the MVP baseline revision."""
    if "tenants" not in metadata.tables:
        # Small isolated metadata fixtures may not model the tenant registry.
        return
    for table_name in MIGRATION_OWNED_TENANT_TABLES:
        table = metadata.tables.get(table_name)
        if table is None:
            continue
        if "tenant_id" in table.c:
            raise ValueError(
                "Migration-owned tenant_id has competing runtime ownership: "
                f"{table_name}"
            )
        index_name = f"ix_{table_name}_tenant_id"
        if any(index.name == index_name for index in table.indexes):
            raise ValueError(
                "Migration-owned tenant index has competing runtime ownership: "
                f"{index_name}"
            )
        tenant_id = sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            info={"migration_owned_by_revision": _MIGRATION_OWNED_TENANT_REVISION},
        )
        table.append_column(tenant_id)
        sa.Index(index_name, tenant_id)


def _register_migration_owned_hot_indexes(
    metadata: sa.MetaData, *, dialect_name: str
) -> None:
    selected = tuple(
        spec
        for spec in _MIGRATION_OWNED_HOT_INDEXES
        if dialect_name == "postgresql" or spec[0] not in _POSTGRESQL_ONLY_HOT_INDEXES
    )
    names = {spec[0] for spec in selected}
    conflicts = {
        str(index.name)
        for table in metadata.tables.values()
        for index in table.indexes
        if index.name in names
    }
    if conflicts:
        raise ValueError(
            "Migration-owned hot index has competing runtime ownership: "
            f"{sorted(conflicts)}"
        )

    for index_name, table_name, column_names, extra_columns, revision in selected:
        table = metadata.tables.get(table_name)
        if table is None:
            # Do not hide removal of a runtime table from normal drift detection.
            continue
        missing = set(column_names + extra_columns).difference(table.c.keys())
        if missing:
            raise ValueError(
                "Migration-owned hot index is missing required column: "
                f"{table_name}.{sorted(missing)}"
            )

        columns = [
            table.c[name].desc()
            if index_name == "idx_messages_chat_pagination_covering"
            and name in {"created_at", "id"}
            else table.c[name]
            for name in column_names
        ]
        postgresql_where: sa.ColumnElement[bool] | None = None
        sqlite_where: sa.ColumnElement[bool] | None = None
        postgresql_include: tuple[str, ...] | None = None
        if index_name == "ix_messages_unread_chat_sender":
            postgresql_where = table.c.read_status == sa.false()
        elif index_name in {
            "ix_stored_events_pending_created",
            "ix_stored_events_pending_aggregate_created",
        }:
            if dialect_name == "postgresql":
                postgresql_where = table.c.processed_at.is_(None)
            else:
                sqlite_where = table.c.processed_at.is_(None)
        elif (
            index_name == "ix_stored_events_aggregate_uuid"
            and dialect_name == "postgresql"
        ):
            postgresql_where = sa.and_(
                table.c.processed_at.is_(None),
                table.c.aggregate_id_uuid.is_not(None),
            )
        if index_name == "idx_messages_chat_pagination_covering":
            postgresql_include = ("sender_id", "read_status")
        sa.Index(
            index_name,
            *columns,
            info={"migration_owned_by_revision": revision},
            postgresql_where=postgresql_where,
            sqlite_where=sqlite_where,
            postgresql_include=postgresql_include,
        )


def _register_retained_tables(metadata: sa.MetaData) -> None:
    sa.Table(
        "user_stats",
        metadata,
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attendance_percent", sa.Float(), server_default="0.0", nullable=False
        ),
        sa.Column(
            "attendance_present", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("attendance_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attendance_trend", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("grades_average", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("grades_trend", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "participation_events", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "participation_hours", sa.Float(), server_default="0.0", nullable=False
        ),
        sa.Column(
            "participation_groups", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "participation_trend", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    vector_chunks = sa.Table(
        "vector_chunks",
        metadata,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.String(length=256), nullable=True),
        sa.Column("document_id", sa.String(length=256), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_vector_chunks_chunk_index", ["chunk_index"]),
        ("ix_vector_chunks_course_id", ["course_id"]),
        ("ix_vector_chunks_created_at", ["created_at"]),
        ("ix_vector_chunks_document_id", ["document_id"]),
        ("ix_vector_chunks_embedding", ["embedding"]),
        ("ix_vector_chunks_is_active", ["is_active"]),
        ("ix_vector_chunks_tenant_course", ["tenant_id", "course_id"]),
        ("ix_vector_chunks_tenant_doc", ["tenant_id", "document_id"]),
        ("ix_vector_chunks_tenant_id", ["tenant_id"]),
    ):
        sa.Index(name, *(vector_chunks.c[column] for column in columns))
