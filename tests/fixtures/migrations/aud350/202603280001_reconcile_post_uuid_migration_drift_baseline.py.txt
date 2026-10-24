"""Reconcile post-UUID migration schema drift.

Cleans up leftover shadow indexes, uuid_id columns, re-creates foreign keys
dropped during the UUID v7 cutover, tightens nullable constraints to match ORM
models, creates the user_stats table, and adds model-defined indexes/constraints.

Revision ID: 202603280001
Revises: 7ad848733a4b
Create Date: 2026-03-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603280001"
down_revision: str | None = "7ad848733a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Shadow / uuid_id indexes to drop  (leftover from UUID migration)
# ---------------------------------------------------------------------------
_SHADOW_INDEXES: list[tuple[str, str]] = [
    # active_sessions
    ("ix_active_sessions_shadow_user_id", "active_sessions"),
    ("ix_active_sessions_uuid_id", "active_sessions"),
    ("idx_active_sessions_user_valid", "active_sessions"),
    ("ix_active_sessions_user_active_created", "active_sessions"),
    # attachments
    ("ix_attachments_shadow_message_id", "attachments"),
    ("ix_attachments_uuid_id", "attachments"),
    # chat_participants
    ("ix_chat_participants_chat_id_user_id", "chat_participants"),
    ("ix_chat_participants_shadow_chat_id", "chat_participants"),
    ("ix_chat_participants_shadow_user_id", "chat_participants"),
    ("ix_chat_participants_user_id_chat_id", "chat_participants"),
    ("ix_chat_participants_uuid_id", "chat_participants"),
    # chats
    ("ix_chats_uuid_id", "chats"),
    # data_access_logs
    ("ix_data_access_logs_shadow_actor_user_id", "data_access_logs"),
    ("ix_data_access_logs_shadow_subject_user_id", "data_access_logs"),
    ("ix_data_access_logs_uuid_id", "data_access_logs"),
    # email_change_tokens
    ("ix_email_change_tokens_shadow_user_id", "email_change_tokens"),
    ("ix_email_change_tokens_uuid_id", "email_change_tokens"),
    # event_attendance
    ("ix_event_attendance_shadow_event_id", "event_attendance"),
    ("ix_event_attendance_shadow_user_id", "event_attendance"),
    ("ix_event_attendance_uuid_id", "event_attendance"),
    # event_files
    ("ix_event_files_shadow_event_id", "event_files"),
    ("ix_event_files_uuid_id", "event_files"),
    # events
    ("ix_events_embedding_hnsw", "events"),
    ("ix_events_shadow_created_by", "events"),
    ("ix_events_uuid_id", "events"),
    # failed_login_attempts
    ("ix_failed_login_attempts_shadow_user_id", "failed_login_attempts"),
    ("ix_failed_login_attempts_uuid_id", "failed_login_attempts"),
    # groups
    ("ix_groups_uuid_id", "groups"),
    # invite_codes
    ("ix_invite_codes_shadow_used_by_user_id", "invite_codes"),
    ("ix_invite_codes_uuid_id", "invite_codes"),
    # login_history
    ("ix_login_history_shadow_user_id", "login_history"),
    ("ix_login_history_uuid_id", "login_history"),
    # messages
    ("idx_messages_chat_created", "messages"),
    ("idx_messages_chat_pagination_covering", "messages"),
    ("ix_messages_shadow_chat_id", "messages"),
    ("ix_messages_shadow_sender_id", "messages"),
    ("ix_messages_unread_chat_sender", "messages"),
    ("ix_messages_uuid_id", "messages"),
    # mfa_challenges
    ("ix_mfa_challenges_shadow_user_id", "mfa_challenges"),
    ("ix_mfa_challenges_uuid_id", "mfa_challenges"),
    # mfa_totp_enrollments
    ("ix_mfa_totp_enrollments_shadow_user_id", "mfa_totp_enrollments"),
    ("ix_mfa_totp_enrollments_uuid_id", "mfa_totp_enrollments"),
    # news
    ("ix_news_embedding_hnsw", "news"),
    ("ix_news_shadow_author_id", "news"),
    ("ix_news_uuid_id", "news"),
    ("news_embedding_hnsw_idx", "news"),
    # news_comments
    ("idx_news_comment_cursor", "news_comments"),
    ("ix_news_comments_shadow_news_id", "news_comments"),
    ("ix_news_comments_shadow_user_id", "news_comments"),
    ("ix_news_comments_uuid_id", "news_comments"),
    # news_likes
    ("ix_news_likes_shadow_news_id", "news_likes"),
    ("ix_news_likes_shadow_user_id", "news_likes"),
    ("ix_news_likes_uuid_id", "news_likes"),
    # notification_deliveries
    ("ix_notification_deliveries_shadow_notification_id", "notification_deliveries"),
    ("ix_notification_deliveries_uuid_id", "notification_deliveries"),
    # notification_queue_jobs
    ("ix_notification_queue_jobs_uuid_id", "notification_queue_jobs"),
    # notifications
    ("idx_notifications_user_unread_created", "notifications"),
    ("ix_notifications_shadow_user_id", "notifications"),
    ("ix_notifications_uuid_id", "notifications"),
    # password_reset_tokens
    ("ix_password_reset_tokens_shadow_user_id", "password_reset_tokens"),
    ("ix_password_reset_tokens_uuid_id", "password_reset_tokens"),
    # push_subscriptions
    ("ix_push_subscriptions_shadow_user_id", "push_subscriptions"),
    ("ix_push_subscriptions_uuid_id", "push_subscriptions"),
    # recovery_codes
    ("ix_recovery_codes_shadow_user_id", "recovery_codes"),
    ("ix_recovery_codes_uuid_id", "recovery_codes"),
    # schedule
    ("ix_schedule_shadow_group_id", "schedule"),
    ("ix_schedule_uuid_id", "schedule"),
    # spotify_integrations
    ("ix_spotify_integrations_shadow_user_id", "spotify_integrations"),
    ("ix_spotify_integrations_uuid_id", "spotify_integrations"),
    # stored_events
    ("ix_stored_events_aggregate_uuid", "stored_events"),
    ("ix_stored_events_pending", "stored_events"),
    ("ix_stored_events_pending_aggregate_created", "stored_events"),
    ("ix_stored_events_pending_created", "stored_events"),
    ("ix_stored_events_uuid_id", "stored_events"),
    # stories
    ("ix_stories_shadow_user_id", "stories"),
    ("ix_stories_uuid_id", "stories"),
    # trusted_devices
    ("ix_trusted_devices_shadow_user_id", "trusted_devices"),
    ("ix_trusted_devices_uuid_id", "trusted_devices"),
    # user_education_paths
    ("ix_user_education_paths_shadow_user_id", "user_education_paths"),
    ("ix_user_education_paths_uuid_id", "user_education_paths"),
    # user_preferences
    ("ix_user_preferences_shadow_user_id", "user_preferences"),
    ("ix_user_preferences_uuid_id", "user_preferences"),
    # user_profiles
    ("ix_user_profile_details_shadow_user_id", "user_profiles"),
    ("ix_user_profile_details_uuid_id", "user_profiles"),
    ("ix_user_profiles_full_name_lower", "user_profiles"),
    ("ix_user_profiles_full_name_trgm", "user_profiles"),
    # user_push_topics
    ("ix_user_push_topics_shadow_user_id", "user_push_topics"),
    ("ix_user_push_topics_uuid_id", "user_push_topics"),
    # users
    ("ix_users_shadow_group_id", "users"),
    ("ix_users_uuid_id", "users"),
    ("ux_users_lower_email", "users"),
    # webauthn_credentials
    ("ix_webauthn_credentials_shadow_user_id", "webauthn_credentials"),
    ("ix_webauthn_credentials_uuid_id", "webauthn_credentials"),
    # data_access_logs_default partition indexes
    ("data_access_logs_default_shadow_actor_user_id_idx", "data_access_logs_default"),
    ("data_access_logs_default_shadow_subject_user_id_idx", "data_access_logs_default"),
    ("data_access_logs_default_uuid_id_created_at_idx", "data_access_logs_default"),
]


# ---------------------------------------------------------------------------
# uuid_id columns to drop (vestigial from UUID migration)
# ---------------------------------------------------------------------------
_UUID_ID_COLUMNS: list[tuple[str, str]] = [
    ("chat_participants", "uuid_id"),
    ("spotify_integrations", "uuid_id"),
    ("user_education_paths", "uuid_id"),
    ("user_preferences", "uuid_id"),
    ("user_profiles", "uuid_id"),
    ("user_push_topics", "uuid_id"),
]


# ---------------------------------------------------------------------------
# Foreign keys to re-create (dropped during UUID cutover, never re-added)
# ---------------------------------------------------------------------------
_FK_SPECS: list[tuple[str, str, str, str, str]] = [
    # (table, local_col, ref_table, ref_col, ondelete)
    ("active_sessions", "user_id", "users", "id", "CASCADE"),
    ("attachments", "message_id", "messages", "id", "CASCADE"),
    ("chat_participants", "chat_id", "chats", "id", "CASCADE"),
    ("chat_participants", "user_id", "users", "id", "CASCADE"),
    ("data_access_logs", "subject_user_id", "users", "id", "SET NULL"),
    ("data_access_logs", "actor_user_id", "users", "id", "SET NULL"),
    ("email_change_tokens", "user_id", "users", "id", "CASCADE"),
    ("event_attendance", "user_id", "users", "id", "CASCADE"),
    ("event_attendance", "event_id", "events", "id", "CASCADE"),
    ("event_files", "event_id", "events", "id", "CASCADE"),
    ("events", "created_by", "users", "id", "SET NULL"),
    ("failed_login_attempts", "user_id", "users", "id", "CASCADE"),
    ("invite_codes", "used_by_user_id", "users", "id", "SET NULL"),
    ("login_history", "user_id", "users", "id", "CASCADE"),
    ("messages", "sender_id", "users", "id", "CASCADE"),
    ("messages", "chat_id", "chats", "id", "CASCADE"),
    ("mfa_challenges", "user_id", "users", "id", "CASCADE"),
    ("mfa_challenges", "session_id", "active_sessions", "id", "CASCADE"),
    ("mfa_totp_enrollments", "user_id", "users", "id", "CASCADE"),
    ("news_comments", "news_id", "news", "id", "CASCADE"),
    ("news_comments", "user_id", "users", "id", "CASCADE"),
    ("news_likes", "news_id", "news", "id", "CASCADE"),
    ("news_likes", "user_id", "users", "id", "CASCADE"),
    ("notifications", "user_id", "users", "id", "CASCADE"),
    ("password_reset_tokens", "user_id", "users", "id", "CASCADE"),
    ("push_subscriptions", "user_id", "users", "id", "CASCADE"),
    ("recovery_codes", "user_id", "users", "id", "CASCADE"),
    ("news", "author_id", "users", "id", "SET NULL"),
    ("schedule", "group_id", "groups", "id", "CASCADE"),
    ("schedule", "creator_id", "users", "id", "SET NULL"),
    ("spotify_integrations", "user_id", "users", "id", "CASCADE"),
    ("stories", "created_by", "users", "id", "SET NULL"),
    ("trusted_devices", "user_id", "users", "id", "CASCADE"),
    ("user_education_paths", "user_id", "users", "id", "CASCADE"),
    ("user_preferences", "user_id", "users", "id", "CASCADE"),
    ("user_profiles", "user_id", "users", "id", "CASCADE"),
    ("user_push_topics", "user_id", "users", "id", "CASCADE"),
    ("users", "group_id", "groups", "id", "SET NULL"),
    ("webauthn_credentials", "user_id", "users", "id", "CASCADE"),
]


# ---------------------------------------------------------------------------
# Nullable changes  (column, table) -> set NOT NULL
# ---------------------------------------------------------------------------
_NOT_NULL_CHANGES: list[tuple[str, str]] = [
    ("active_sessions", "user_id"),
    ("attachments", "message_id"),
    ("email_change_tokens", "created_at"),
    ("email_change_tokens", "user_id"),
    ("event_attendance", "event_id"),
    ("event_attendance", "registered_at"),
    ("event_attendance", "user_id"),
    ("event_files", "event_id"),
    ("events", "created_at"),
    ("events", "is_active"),
    ("failed_login_attempts", "user_id"),
    ("invite_codes", "is_active"),
    ("invite_codes", "is_used"),
    ("invite_codes", "created_at"),
    ("login_history", "user_id"),
    ("messages", "chat_id"),
    ("messages", "sender_id"),
    ("mfa_challenges", "user_id"),
    ("mfa_totp_enrollments", "user_id"),
    ("news", "created_at"),
    ("news_comments", "news_id"),
    ("news_comments", "created_at"),
    ("news_comments", "user_id"),
    ("news_likes", "news_id"),
    ("news_likes", "created_at"),
    ("news_likes", "user_id"),
    ("notification_deliveries", "notification_id"),
    ("notifications", "read"),
    ("notifications", "user_id"),
    ("password_reset_tokens", "created_at"),
    ("password_reset_tokens", "user_id"),
    ("push_subscriptions", "user_id"),
    ("recovery_codes", "user_id"),
    ("schedule", "group_id"),
    ("schedule", "parity"),
    ("spotify_integrations", "is_connected"),
    ("spotify_integrations", "is_playing"),
    ("trusted_devices", "user_id"),
    ("users", "is_active"),
    ("users", "created_at"),
    ("webauthn_credentials", "backing_up"),
    ("webauthn_credentials", "backup_state"),
    ("webauthn_credentials", "user_id"),
]


def upgrade() -> None:
    """Reconcile ORM models with DB after UUID v7 migration."""

    # ------------------------------------------------------------------
    # 0. data_access_logs_default — intentionally KEPT.
    #    Previously this block dropped the DEFAULT partition as an
    #    autogenerate clean-up step; however 202607020001 re-creates it
    #    anyway and the DEFAULT is a permanent safety-net that prevents
    #    CheckViolationError on inserts that fall outside every explicit
    #    range partition.  Dropping it here breaks the CI test suite.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 1. Drop all shadow / uuid_id / stale indexes
    # ------------------------------------------------------------------
    for idx_name, _table_name in _SHADOW_INDEXES:
        # CASCADE needed: some uuid_id unique indexes back FK constraints
        op.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name} CASCADE"))

    # ------------------------------------------------------------------
    # 2. Drop vestigial uuid_id columns
    # ------------------------------------------------------------------
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, col_name in _UUID_ID_COLUMNS:
        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        if col_name in existing_cols:
            op.drop_column(table_name, col_name)

    # ------------------------------------------------------------------
    # 3. Create user_stats table (guarded for idempotent re-run)
    # ------------------------------------------------------------------
    all_tables = set(inspector.get_table_names())
    if "user_stats" in all_tables:
        op.drop_table("user_stats")
    op.create_table(
        "user_stats",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "attendance_percent", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "attendance_present", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("attendance_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attendance_trend", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("grades_average", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("grades_trend", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "participation_events", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "participation_hours", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "participation_groups", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "participation_trend", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # 4. Tighten nullable constraints
    # ------------------------------------------------------------------
    for table_name, col_name in _NOT_NULL_CHANGES:
        op.alter_column(table_name, col_name, existing_type=sa.UUID(), nullable=False)

    # events.embedding stays nullable — events are created before embeddings
    # are computed asynchronously. Model changed to Mapped[Any | None].

    # ------------------------------------------------------------------
    # 5. Re-create foreign keys
    # ------------------------------------------------------------------
    for table, local_col, ref_table, ref_col, ondelete in _FK_SPECS:
        fk_name = f"fk_{table}_{local_col}"
        # Guard: skip if FK already exists (idempotent re-run after downgrade)
        existing_fks = {
            fk["name"] for fk in inspector.get_foreign_keys(table) if fk["name"]
        }
        if fk_name not in existing_fks:
            op.create_foreign_key(
                fk_name, table, ref_table, [local_col], [ref_col], ondelete=ondelete
            )

    # notification_deliveries composite FK to partitioned notifications
    nd_fks = {
        fk["name"]
        for fk in inspector.get_foreign_keys("notification_deliveries")
        if fk["name"]
    }
    if "fk_notification_deliveries_notification" not in nd_fks:
        op.create_foreign_key(
            "fk_notification_deliveries_notification",
            "notification_deliveries",
            "notifications",
            ["notification_id", "notification_created_at"],
            ["id", "created_at"],
            ondelete="CASCADE",
        )

    # ------------------------------------------------------------------
    # 6. Create new indexes (IF NOT EXISTS for idempotent re-run)
    # ------------------------------------------------------------------
    _INDEXES: list[tuple[str, str, str]] = [
        ("ix_active_sessions_mfa_completed_at", "active_sessions", "mfa_completed_at"),
        ("ix_active_sessions_mfa_required", "active_sessions", "mfa_required"),
        ("ix_attachments_message_id", "attachments", "message_id"),
        ("ix_data_access_logs_action", "data_access_logs", "action"),
        ("ix_data_access_logs_actor_user_id", "data_access_logs", "actor_user_id"),
        ("ix_data_access_logs_created_at", "data_access_logs", "created_at"),
        ("ix_data_access_logs_resource_id", "data_access_logs", "resource_id"),
        ("ix_data_access_logs_resource_type", "data_access_logs", "resource_type"),
        ("ix_data_access_logs_subject_user_id", "data_access_logs", "subject_user_id"),
        ("ix_events_created_by", "events", "created_by"),
        ("ix_events_title", "events", "title"),
        ("ix_failed_login_attempts_ip_address", "failed_login_attempts", "ip_address"),
        ("ix_invite_codes_used_by_user_id", "invite_codes", "used_by_user_id"),
        ("ix_news_author_id", "news", "author_id"),
        ("ix_news_title", "news", "title"),
        ("ix_news_comments_created_at", "news_comments", "created_at"),
        ("ix_news_likes_created_at", "news_likes", "created_at"),
        (
            "ix_notification_deliveries_subscription_id",
            "notification_deliveries",
            "subscription_id",
        ),
        ("ix_notifications_title", "notifications", "title"),
        ("ix_stored_events_aggregate_id_uuid", "stored_events", "aggregate_id_uuid"),
        ("ix_trusted_devices_user_id", "trusted_devices", "user_id"),
        ("ix_users_mfa_last_verified_at", "users", "mfa_last_verified_at"),
        ("ix_users_mfa_required", "users", "mfa_required"),
    ]
    for idx_name, tbl, cols in _INDEXES:
        op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({cols})"))

    # Composite indexes
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_news_comments_news_created "
            "ON news_comments (news_id, created_at)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_news_likes_news_created "
            "ON news_likes (news_id, created_at)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_notification_queue_jobs_pending_claim "
            "ON notification_queue_jobs (next_retry_at, enqueued_at, id)"
        )
    )

    # ------------------------------------------------------------------
    # 7. Unique constraints (idempotent via DO $$ guard)
    # ------------------------------------------------------------------
    _UQ_CONSTRAINTS = [
        (
            "uq_news_like_user_news",
            "news_likes",
            "user_id, news_id",
        ),
        (
            "uq_notification_delivery_once",
            "notification_deliveries",
            "notification_id, channel, subscription_id, attempted_at",
        ),
        (
            "uq_users_email",
            "users",
            "email",
        ),
    ]
    for uq_name, uq_table, uq_cols in _UQ_CONSTRAINTS:
        existing_uqs = {
            c["name"] for c in inspector.get_unique_constraints(uq_table) if c["name"]
        }
        if uq_name not in existing_uqs:
            op.create_unique_constraint(uq_name, uq_table, uq_cols.split(", "))

    # ------------------------------------------------------------------
    # 8. Type changes
    # ------------------------------------------------------------------
    op.alter_column(
        "failed_outbox_events",
        "aggregate_type",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_queue_jobs",
        "kind",
        existing_type=sa.VARCHAR(length=16),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_queue_jobs",
        "record_id",
        existing_type=sa.Integer(),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="record_id::text::uuid",
    )
    op.alter_column(
        "stored_events",
        "created_at",
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "user_preferences",
        "dnd_start",
        existing_type=sa.TIME(),
        type_=sa.Time(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "user_preferences",
        "dnd_end",
        existing_type=sa.TIME(),
        type_=sa.Time(timezone=True),
        existing_nullable=True,
    )

    # ------------------------------------------------------------------
    # 9. Column comments — older migrations set comments via add_column/
    #    alter_column but the ORM models don't define comment=.
    #    Clear them so DB matches model (both None).
    # ------------------------------------------------------------------
    op.execute(sa.text("COMMENT ON COLUMN failed_login_attempts.ip_address IS NULL"))
    op.execute(
        sa.text("COMMENT ON COLUMN mfa_totp_enrollments.last_used_code_hash IS NULL")
    )
    op.execute(sa.text("COMMENT ON COLUMN mfa_totp_enrollments.last_used_at IS NULL"))
    op.execute(
        sa.text("COMMENT ON COLUMN notification_deliveries.subscription_id IS NULL")
    )

    # ------------------------------------------------------------------
    # 10. Embedding indexes (use raw SQL for vector type)
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_events_embedding "
            "ON events USING hnsw (embedding vector_cosine_ops)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_news_embedding "
            "ON news USING hnsw (embedding vector_cosine_ops)"
        )
    )


def downgrade() -> None:
    """Reverse the reconciliation — best-effort for development use only."""

    # Drop embedding indexes
    op.drop_index("ix_news_embedding", table_name="news", if_exists=True)
    op.drop_index("ix_events_embedding", table_name="events", if_exists=True)

    # Drop unique constraints
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint(
        "uq_notification_delivery_once",
        "notification_deliveries",
        type_="unique",
    )
    op.drop_constraint("uq_news_like_user_news", "news_likes", type_="unique")

    # Drop new indexes (reverse of step 6)
    for idx_name, table_name in [
        ("ix_users_mfa_required", "users"),
        ("ix_users_mfa_last_verified_at", "users"),
        ("ix_trusted_devices_user_id", "trusted_devices"),
        ("ix_stored_events_aggregate_id_uuid", "stored_events"),
        ("ix_notifications_title", "notifications"),
        ("ix_notification_queue_jobs_pending_claim", "notification_queue_jobs"),
        ("ix_notification_deliveries_subscription_id", "notification_deliveries"),
        ("ix_news_likes_news_created", "news_likes"),
        ("ix_news_likes_created_at", "news_likes"),
        ("ix_news_comments_news_created", "news_comments"),
        ("ix_news_comments_created_at", "news_comments"),
        ("ix_news_title", "news"),
        ("ix_news_author_id", "news"),
        ("ix_invite_codes_used_by_user_id", "invite_codes"),
        ("ix_failed_login_attempts_ip_address", "failed_login_attempts"),
        ("ix_events_title", "events"),
        ("ix_events_created_by", "events"),
        ("ix_data_access_logs_subject_user_id", "data_access_logs"),
        ("ix_data_access_logs_resource_type", "data_access_logs"),
        ("ix_data_access_logs_resource_id", "data_access_logs"),
        ("ix_data_access_logs_created_at", "data_access_logs"),
        ("ix_data_access_logs_actor_user_id", "data_access_logs"),
        ("ix_data_access_logs_action", "data_access_logs"),
        ("ix_attachments_message_id", "attachments"),
        ("ix_active_sessions_mfa_required", "active_sessions"),
        ("ix_active_sessions_mfa_completed_at", "active_sessions"),
    ]:
        op.drop_index(idx_name, table_name=table_name, if_exists=True)

    # Drop FKs
    for table, local_col, ref_table, ref_col, ondelete in _FK_SPECS:
        fk_name = f"fk_{table}_{local_col}"
        op.drop_constraint(fk_name, table, type_="foreignkey")

    op.drop_constraint(
        "fk_notification_deliveries_notification",
        "notification_deliveries",
        type_="foreignkey",
    )

    # Drop user_stats
    op.drop_table("user_stats")

    # Note: not restoring shadow indexes, uuid_id columns, or partition
    # table in downgrade — those are UUID migration artefacts.
