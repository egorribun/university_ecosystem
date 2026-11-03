"""MVP baseline: the schema of the squashed chain, as one explicit revision.

This revision replaces the 143 revisions that ran from the initial migration to
202610310001 (pre-squash commit 3ff5375fb). It creates the same PostgreSQL
objects in dependency order: roles, extensions, types, functions, sequences,
tables, keys, indexes, monthly range partitions, row-level security, policies,
triggers and the pg_cron cleanup jobs. Two owner-approved additions follow that
reproduction:

* AUD-269 restores the eight hot-path indexes that revision 202603280001 dropped
  without replacement (``_RESTORED_HOT_PATH_INDEXES``).
* AUD-272 adds ``notification_delivery_once``, a claim ledger that admits at most
  one push delivery per notification, subscription and channel
  (``_DELIVERY_ONCE_TABLE``).

PostgreSQL is required. The statements are literal DDL and nothing is replayed
from a dump at runtime. Nothing is deployed, so the squashed chain is not a
rollback path: ``downgrade()`` is irreversible and raises before it changes any
schema. Recover an earlier state from a consistent backup and restore set.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "202611020000"
down_revision: str | None = None
branch_labels = None
depends_on = None
downgrade_policy = "irreversible"
downgrade_reason = (
    "The MVP baseline cannot be downgraded: reaching base or any earlier schema "
    "is not a supported recovery path. Restore a consistent backup set instead."
)

# Transaction-scoped waits for the whole baseline; SET LOCAL ends with the transaction.
_TRANSACTION_TIMEOUTS: tuple[str, ...] = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '60s'",
)

# NOLOGIN role that row-level-security policies test for bypass membership.
_ROLES: tuple[str, ...] = (
    (
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
        "'ue_rls_bypass') THEN CREATE ROLE ue_rls_bypass NOLOGIN; END IF; END $$"
    ),
)

_EXTENSIONS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public",
    (
        "COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index "
        "searching based on trigrams'"
    ),
    "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public",
    (
        "COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw "
        "access methods'"
    ),
)

_TYPES: tuple[str, ...] = (
    (
        "CREATE TYPE public.challenge_state_enum AS ENUM (\n"
        "    'pending',\n"
        "    'consumed',\n"
        "    'locked',\n"
        "    'expired'\n"
        ")"
    ),
    (
        "CREATE TYPE public.userrole AS ENUM (\n"
        "    'STUDENT',\n"
        "    'TEACHER',\n"
        "    'ADMIN',\n"
        "    'SUPERUSER',\n"
        "    'student',\n"
        "    'teacher',\n"
        "    'admin',\n"
        "    'superuser',\n"
        "    'anonymous'\n"
        ")"
    ),
)

_FUNCTIONS: tuple[str, ...] = (
    (
        "CREATE FUNCTION public.notify_outbox_event() RETURNS trigger\n"
        "    LANGUAGE plpgsql\n"
        "    AS $$\n"
        "            BEGIN\n"
        "                PERFORM pg_notify('outbox_events', '');\n"
        "                RETURN NEW;\n"
        "            END;\n"
        "            $$"
    ),
    (
        "CREATE FUNCTION public.ue_rls_assign_session_tenant() RETURNS trigger\n"
        "    LANGUAGE plpgsql\n"
        "    AS $$ BEGIN IF NEW.tenant_id IS NULL THEN NEW.tenant_id := "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid; END IF; "
        "RETURN NEW; END $$"
    ),
)

_SEQUENCES: tuple[str, ...] = (
    (
        "CREATE SEQUENCE public.dead_letter_jobs_id_seq\n"
        "    AS integer\n"
        "    START WITH 1\n"
        "    INCREMENT BY 1\n"
        "    NO MINVALUE\n"
        "    NO MAXVALUE\n"
        "    CACHE 1"
    ),
)

_TABLES: tuple[str, ...] = (
    (
        "CREATE TABLE public.active_sessions (\n"
        "    jti character varying NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    revoked_at timestamp with time zone,\n"
        "    ip_address character varying(64),\n"
        "    user_agent character varying(512),\n"
        "    last_seen_at timestamp with time zone,\n"
        "    signing_key character varying(128) NOT NULL,\n"
        "    mfa_required boolean DEFAULT false NOT NULL,\n"
        "    mfa_completed_at timestamp with time zone,\n"
        "    mfa_method character varying(64),\n"
        "    mfa_verified_at timestamp with time zone,\n"
        "    accept_language character varying(256),\n"
        "    fingerprint_hash character varying(64),\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    mfa_epoch integer DEFAULT 0 NOT NULL,\n"
        "    CONSTRAINT ck_active_sessions_signing_key_not_null CHECK ((signing_key IS NOT NULL)),\n"
        "    CONSTRAINT active_sessions_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.attachments (\n"
        "    url character varying NOT NULL,\n"
        "    file_type character varying NOT NULL,\n"
        "    filename character varying NOT NULL,\n"
        "    size integer NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    message_id uuid NOT NULL,\n"
        "    CONSTRAINT attachments_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.chat_participants (\n"
        "    user_id uuid NOT NULL,\n"
        "    chat_id uuid NOT NULL,\n"
        "    CONSTRAINT chat_participants_pkey PRIMARY KEY (chat_id, user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.chat_read_receipts (\n"
        "    id uuid NOT NULL,\n"
        "    chat_id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    last_read_at timestamp with time zone NOT NULL,\n"
        "    CONSTRAINT chat_read_receipts_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.chat_send_receipts (\n"
        "    id uuid NOT NULL,\n"
        "    chat_id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    key_digest character varying(64) NOT NULL,\n"
        "    message_id uuid,\n"
        "    completed_at timestamp with time zone NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    CONSTRAINT chat_send_receipts_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.chats (\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    updated_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    chat_type character varying(20) DEFAULT 'dm'::character varying NOT NULL,\n"
        "    name character varying(128),\n"
        "    created_by uuid,\n"
        "    tenant_id uuid,\n"
        "    demo_seed_key character varying(96),\n"
        "    CONSTRAINT ck_chats_chat_type CHECK (chat_type IN ('dm', 'group')),\n"
        "    CONSTRAINT chats_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.cwv_observations (\n"
        "    id uuid NOT NULL,\n"
        "    metric character varying(3) NOT NULL,\n"
        "    unit character varying(5) NOT NULL,\n"
        "    value double precision NOT NULL,\n"
        "    metric_id character varying(32) NOT NULL,\n"
        "    collector_id character varying(32) NOT NULL,\n"
        "    navigation_id character varying(128) NOT NULL,\n"
        "    session_id character varying(128) NOT NULL,\n"
        "    device_class character varying(7) NOT NULL,\n"
        "    route_group character varying(48) NOT NULL,\n"
        "    observed_at timestamp with time zone NOT NULL,\n"
        "    sampling_bucket timestamp with time zone NOT NULL,\n"
        "    release_sha character varying(40) NOT NULL,\n"
        "    frontend_image_digest character varying(71) NOT NULL,\n"
        "    deployment_run_id bigint NOT NULL,\n"
        "    deployment_run_attempt integer NOT NULL,\n"
        "    envelope_nonce character varying(128) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT ck_cwv_device_class CHECK (device_class IN ('mobile','desktop')),\n"
        "    CONSTRAINT ck_cwv_observation_metric CHECK (metric IN ('LCP','INP','CLS')),\n"
        "    CONSTRAINT ck_cwv_value_nonnegative CHECK ((value >= (0)::double precision)),\n"
        "    CONSTRAINT cwv_observations_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.data_access_logs (\n"
        "    resource_type character varying(64) NOT NULL,\n"
        "    resource_id character varying(128),\n"
        "    action character varying(64) NOT NULL,\n"
        "    context json,\n"
        "    ip_address character varying(64),\n"
        "    user_agent character varying(512),\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    signature character varying(512),\n"
        "    id uuid NOT NULL,\n"
        "    actor_user_id uuid,\n"
        "    subject_user_id uuid,\n"
        "    CONSTRAINT data_access_logs_pkey PRIMARY KEY (id, created_at)\n"
        ")\n"
        "PARTITION BY RANGE (created_at)"
    ),
    (
        "CREATE TABLE public.dead_letter_jobs (\n"
        "    id integer NOT NULL,\n"
        "    job_type character varying(100) NOT NULL,\n"
        "    job_hash character varying(64) NOT NULL,\n"
        "    payload text NOT NULL,\n"
        "    error_message text,\n"
        "    retry_count integer DEFAULT 0 NOT NULL,\n"
        "    max_retries integer DEFAULT 3 NOT NULL,\n"
        "    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,\n"
        "    next_retry_at timestamp with time zone,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    updated_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT dead_letter_jobs_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.email_change_tokens (\n"
        "    new_email character varying(254) NOT NULL,\n"
        "    token_hash character varying NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    used boolean DEFAULT false NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT email_change_tokens_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.event_attendance (\n"
        "    registered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    qr_secret character varying NOT NULL,\n"
        "    qr_hmac character varying NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    event_id uuid NOT NULL,\n"
        "    CONSTRAINT event_attendance_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.event_files (\n"
        "    file_url character varying NOT NULL,\n"
        "    description character varying,\n"
        "    id uuid NOT NULL,\n"
        "    event_id uuid NOT NULL,\n"
        "    CONSTRAINT event_files_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.events (\n"
        "    title character varying NOT NULL,\n"
        "    title_en character varying,\n"
        "    description text,\n"
        "    description_en text,\n"
        "    location character varying,\n"
        "    location_en character varying,\n"
        "    event_type character varying,\n"
        "    event_type_en character varying,\n"
        "    starts_at timestamp with time zone NOT NULL,\n"
        "    ends_at timestamp with time zone NOT NULL,\n"
        "    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, (((((((((((((((COALESCE(title, ''::character varying))::text || ' '::text) || COALESCE(description, ''::text)) || ' '::text) || (COALESCE(location, ''::character varying))::text) || ' '::text) || (COALESCE(title_en, ''::character varying))::text) || ' '::text) || COALESCE(description_en, ''::text)) || ' '::text) || (COALESCE(location_en, ''::character varying))::text) || ' '::text) || COALESCE(about, ''::text)) || ' '::text) || COALESCE(about_en, ''::text)))) STORED,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    speaker character varying,\n"
        "    image_url character varying,\n"
        "    about text,\n"
        "    about_en text,\n"
        "    embedding public.vector(1536),\n"
        "    id uuid NOT NULL,\n"
        "    created_by uuid,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT ck_event_time_order CHECK ((ends_at > starts_at)),\n"
        "    CONSTRAINT events_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.failed_login_attempts (\n"
        "    email character varying(254) NOT NULL,\n"
        "    attempted_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid,\n"
        "    ip_address character varying(45),\n"
        "    user_agent character varying(512),\n"
        "    CONSTRAINT failed_login_attempts_pkey PRIMARY KEY (id, attempted_at)\n"
        ")\n"
        "PARTITION BY RANGE (attempted_at)"
    ),
    (
        "CREATE TABLE public.failed_outbox_events (\n"
        "    id uuid NOT NULL,\n"
        "    original_event_id uuid NOT NULL,\n"
        "    event_type character varying(100) NOT NULL,\n"
        "    aggregate_type character varying(128) NOT NULL,\n"
        "    aggregate_id character varying(100) NOT NULL,\n"
        "    payload json NOT NULL,\n"
        "    error_message text NOT NULL,\n"
        "    retry_count integer DEFAULT 0 NOT NULL,\n"
        "    failed_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    resolved_at timestamp with time zone,\n"
        "    resolution_note text,\n"
        "    CONSTRAINT failed_outbox_events_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.grades (\n"
        "    student_id uuid NOT NULL,\n"
        "    subject character varying(100) NOT NULL,\n"
        "    score double precision NOT NULL,\n"
        "    assessment_type character varying(50) DEFAULT 'exam'::character varying NOT NULL,\n"
        "    assigned_by uuid,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    updated_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    CONSTRAINT grades_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.groups (\n"
        "    name character varying,\n"
        "    course integer,\n"
        "    faculty character varying,\n"
        "    id uuid NOT NULL,\n"
        "    tenant_id uuid,\n"
        "    demo_seed_key character varying(96),\n"
        "    CONSTRAINT groups_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.invite_codes (\n"
        "    code character varying NOT NULL,\n"
        "    role character varying NOT NULL,\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    is_used boolean DEFAULT false NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    used_by_user_id uuid,\n"
        "    CONSTRAINT ck_invite_codes_role_valid CHECK (role IN ('student', 'teacher', 'admin')),\n"
        "    CONSTRAINT invite_codes_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.login_history (\n"
        "    ip_address character varying(45) NOT NULL,\n"
        "    user_agent character varying(512),\n"
        "    country character varying(2),\n"
        "    city character varying(128),\n"
        "    latitude numeric(9,6),\n"
        "    longitude numeric(9,6),\n"
        "    status character varying(20) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    is_suspicious boolean DEFAULT false NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT login_history_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.message_reactions (\n"
        "    id uuid NOT NULL,\n"
        "    message_id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    emoji character varying(16) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT message_reactions_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.messages (\n"
        "    content character varying NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    read_status boolean DEFAULT false NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    sender_id uuid NOT NULL,\n"
        "    chat_id uuid NOT NULL,\n"
        "    read_at timestamp with time zone,\n"
        "    edited_at timestamp with time zone,\n"
        "    deleted_at timestamp with time zone,\n"
        "    reply_to_message_id uuid,\n"
        "    forwarded_from_name character varying(128),\n"
        "    forwarded_from_chat_id uuid,\n"
        "    forwarded_from_message_id uuid,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT messages_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.mfa_challenges (\n"
        "    challenge_type character varying(64) NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    consumed_at timestamp with time zone,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    payload json,\n"
        "    attempt_count integer DEFAULT 0 NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    session_id uuid,\n"
        "    locked_at timestamp with time zone,\n"
        "    state public.challenge_state_enum DEFAULT 'pending'::public.challenge_state_enum NOT NULL,\n"
        "    flow character varying(32),\n"
        "    session_identifier character varying(128),\n"
        "    client_fingerprint character varying(64),\n"
        "    method character varying(20),\n"
        "    revision integer DEFAULT 1,\n"
        "    trust_device_requested boolean DEFAULT false NOT NULL,\n"
        "    token_digest character varying(64),\n"
        "    token_key_id character varying(64),\n"
        "    recipient_digest character varying(64),\n"
        "    otp_digest character varying(64),\n"
        "    otp_key_id character varying(64),\n"
        "    resend_available_at timestamp with time zone,\n"
        "    CONSTRAINT ck_mfa_challenges_client_fingerprint_not_null CHECK ((client_fingerprint IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_email_recipient_digest CHECK ((((method)::text <> 'email_otp'::text) OR (recipient_digest IS NOT NULL))),\n"
        "    CONSTRAINT ck_mfa_challenges_flow_not_null CHECK ((flow IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_method_not_null CHECK ((method IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_revision_not_null CHECK ((revision IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_session_identifier_not_null CHECK ((session_identifier IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_token_digest_not_null CHECK ((token_digest IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_challenges_token_key_id_not_null CHECK ((token_key_id IS NOT NULL)),\n"
        "    CONSTRAINT mfa_challenges_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.mfa_email_deliveries (\n"
        "    id uuid NOT NULL,\n"
        "    challenge_id uuid NOT NULL,\n"
        "    revision integer NOT NULL,\n"
        "    message_id character varying(255) NOT NULL,\n"
        "    template character varying(64) NOT NULL,\n"
        "    locale character varying(2) NOT NULL,\n"
        "    kek_id character varying(64) NOT NULL,\n"
        "    envelope_nonce bytea,\n"
        "    envelope_ciphertext bytea,\n"
        "    wrap_nonce bytea,\n"
        "    wrapped_dek bytea,\n"
        "    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,\n"
        "    attempt_count integer DEFAULT 0 NOT NULL,\n"
        "    lease_token character varying(64),\n"
        "    lease_expires_at timestamp with time zone,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    sent_at timestamp with time zone,\n"
        "    shredded_at timestamp with time zone,\n"
        "    CONSTRAINT ck_mfa_email_delivery_envelope_lifecycle CHECK ((status IN ('pending','sending') AND envelope_nonce IS NOT NULL AND envelope_ciphertext IS NOT NULL AND wrap_nonce IS NOT NULL AND wrapped_dek IS NOT NULL AND shredded_at IS NULL) OR (status IN ('sent','cancelled') AND envelope_nonce IS NULL AND envelope_ciphertext IS NULL AND wrap_nonce IS NULL AND wrapped_dek IS NULL AND shredded_at IS NOT NULL)),\n"
        "    CONSTRAINT ck_mfa_email_delivery_locale CHECK (locale IN ('en','ru')),\n"
        "    CONSTRAINT ck_mfa_email_delivery_status CHECK (status IN ('pending','sending','sent','cancelled')),\n"
        "    CONSTRAINT mfa_email_deliveries_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.mfa_totp_enrollments (\n"
        "    secret text NOT NULL,\n"
        "    label character varying(255),\n"
        "    is_active boolean DEFAULT false NOT NULL,\n"
        "    confirmed_at timestamp with time zone,\n"
        "    revoked_at timestamp with time zone,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    last_used_code_hash character varying(64),\n"
        "    last_used_at timestamp with time zone,\n"
        "    last_used_timecode bigint,\n"
        "    CONSTRAINT mfa_totp_enrollments_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.news (\n"
        "    title character varying NOT NULL,\n"
        "    content text NOT NULL,\n"
        "    title_en character varying,\n"
        "    content_en text,\n"
        "    image_url character varying,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    embedding public.vector(1536),\n"
        "    id uuid NOT NULL,\n"
        "    author_id uuid,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT news_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.news_comments (\n"
        "    content text NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    news_id uuid NOT NULL,\n"
        "    CONSTRAINT news_comments_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.news_likes (\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    news_id uuid NOT NULL,\n"
        "    CONSTRAINT news_likes_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.news_media_assets (\n"
        "    id uuid NOT NULL,\n"
        "    storage_url character varying(2048) NOT NULL,\n"
        "    owner_user_id uuid,\n"
        "    news_id uuid,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT news_media_assets_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.notification_deliveries (\n"
        "    notification_created_at timestamp with time zone NOT NULL,\n"
        "    channel character varying DEFAULT 'inapp'::character varying NOT NULL,\n"
        "    status character varying DEFAULT 'delivered'::character varying NOT NULL,\n"
        "    attempted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    delivered_at timestamp with time zone,\n"
        "    status_code integer,\n"
        "    detail text,\n"
        "    id uuid NOT NULL,\n"
        "    notification_id uuid NOT NULL,\n"
        "    subscription_id uuid,\n"
        "    CONSTRAINT notification_deliveries_pkey PRIMARY KEY (id, attempted_at)\n"
        ")\n"
        "PARTITION BY RANGE (attempted_at)"
    ),
    (
        "CREATE TABLE public.notification_queue_jobs (\n"
        "    kind character varying(50) NOT NULL,\n"
        "    record_id uuid NOT NULL,\n"
        "    locale character varying(16),\n"
        "    enqueued_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    claimed_at timestamp with time zone,\n"
        "    attempts integer DEFAULT 0 NOT NULL,\n"
        "    last_error text,\n"
        "    next_retry_at timestamp with time zone,\n"
        "    dead_lettered boolean DEFAULT false NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    CONSTRAINT ck_notification_queue_jobs_kind CHECK (((kind)::text = ANY (ARRAY[('event'::character varying)::text, ('news'::character varying)::text]))),\n"
        "    CONSTRAINT notification_queue_jobs_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.notifications (\n"
        "    title character varying NOT NULL,\n"
        "    title_en character varying,\n"
        "    body text,\n"
        "    body_en text,\n"
        "    type character varying,\n"
        "    url character varying,\n"
        "    dedupe_key character varying(255),\n"
        "    read boolean DEFAULT false NOT NULL,\n"
        "    read_at timestamp with time zone,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT notifications_pkey PRIMARY KEY (id, created_at)\n"
        ")\n"
        "PARTITION BY RANGE (created_at)"
    ),
    (
        "CREATE TABLE public.password_reset_tokens (\n"
        "    token_hash character varying NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    used boolean DEFAULT false NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.push_subscriptions (\n"
        "    endpoint text NOT NULL,\n"
        "    p256dh character varying(200) NOT NULL,\n"
        "    auth character varying(200) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    user_agent character varying(512),\n"
        "    last_seen_at timestamp with time zone,\n"
        "    topics json DEFAULT '[]'::json NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.quarantine_reservations (\n"
        "    id uuid NOT NULL,\n"
        "    scope_id character varying(64) NOT NULL,\n"
        "    object_key character varying(2048) NOT NULL,\n"
        "    size_bytes bigint NOT NULL,\n"
        "    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    expires_at timestamp with time zone,\n"
        "    CONSTRAINT ck_quarantine_reservation_size CHECK ((size_bytes >= 0)),\n"
        "    CONSTRAINT ck_quarantine_reservation_status CHECK (status IN ('pending', 'stored', 'deleting')),\n"
        "    CONSTRAINT quarantine_reservations_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.quarantine_storage_scopes (\n"
        "    scope_id character varying(64) NOT NULL,\n"
        "    inventory_complete boolean DEFAULT false NOT NULL,\n"
        "    inventory_cursor text,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT quarantine_storage_scopes_pkey PRIMARY KEY (scope_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.recovery_codes (\n"
        "    code_hash character varying(255) NOT NULL,\n"
        "    is_used boolean DEFAULT false NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    used_at timestamp with time zone,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT recovery_codes_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.schedule (\n"
        "    subject character varying NOT NULL,\n"
        "    teacher character varying,\n"
        "    room character varying,\n"
        "    weekday character varying NOT NULL,\n"
        "    start_time timestamp with time zone NOT NULL,\n"
        "    end_time timestamp with time zone NOT NULL,\n"
        "    parity character varying DEFAULT 'both'::character varying NOT NULL,\n"
        "    lesson_type character varying,\n"
        "    id uuid NOT NULL,\n"
        "    group_id uuid NOT NULL,\n"
        "    creator_id uuid,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT ck_schedule_time_order CHECK ((end_time > start_time)),\n"
        "    CONSTRAINT schedule_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.spotify_integrations (\n"
        "    spotify_user_id character varying,\n"
        "    access_token text,\n"
        "    refresh_token text,\n"
        "    token_expires_at timestamp with time zone,\n"
        "    scope character varying,\n"
        "    display_name character varying,\n"
        "    is_connected boolean DEFAULT false NOT NULL,\n"
        "    is_playing boolean DEFAULT false NOT NULL,\n"
        "    last_checked_at timestamp with time zone,\n"
        "    last_track_id character varying,\n"
        "    last_track_name character varying,\n"
        "    last_artist_name character varying,\n"
        "    last_album_name character varying,\n"
        "    last_track_url character varying,\n"
        "    last_album_image_url character varying,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT spotify_integrations_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.stored_events (\n"
        "    event_type character varying(100) NOT NULL,\n"
        "    aggregate_type character varying(50) NOT NULL,\n"
        "    aggregate_id character varying(100) NOT NULL,\n"
        "    payload json NOT NULL,\n"
        "    metadata json,\n"
        "    version integer DEFAULT 1 NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    processed_at timestamp with time zone,\n"
        "    error_count integer DEFAULT 0 NOT NULL,\n"
        "    last_error character varying,\n"
        "    id uuid NOT NULL,\n"
        "    subject character varying(255),\n"
        "    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,\n"
        "    trace_context json,\n"
        "    aggregate_id_uuid uuid,\n"
        "    sequence_number bigint,\n"
        "    prev_hash character varying(64),\n"
        "    hash character varying(64),\n"
        "    CONSTRAINT stored_events_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.stories (\n"
        "    title character varying NOT NULL,\n"
        "    title_en character varying,\n"
        "    short_text text NOT NULL,\n"
        "    short_text_en text,\n"
        "    cover_url character varying,\n"
        "    cta_url character varying,\n"
        "    published_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    created_by uuid,\n"
        "    tenant_id uuid,\n"
        "    CONSTRAINT stories_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.tenants (\n"
        "    id uuid NOT NULL,\n"
        "    name character varying(256) NOT NULL,\n"
        "    slug character varying(64) NOT NULL,\n"
        "    domain character varying(256),\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT tenants_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.trusted_devices (\n"
        "    token_hash character varying(128) NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL,\n"
        "    last_used_at timestamp with time zone,\n"
        "    user_agent character varying(512),\n"
        "    ip_address character varying(45),\n"
        "    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n"
        "    id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    ip_hash character varying(64),\n"
        "    ua_hash character varying(64),\n"
        "    mfa_epoch integer DEFAULT 0 NOT NULL,\n"
        "    token_key_id character varying(64),\n"
        "    binding_digest character varying(64),\n"
        "    CONSTRAINT ck_trusted_devices_binding_digest_not_null CHECK ((binding_digest IS NOT NULL)),\n"
        "    CONSTRAINT ck_trusted_devices_token_key_id_not_null CHECK ((token_key_id IS NOT NULL)),\n"
        "    CONSTRAINT trusted_devices_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.user_education_paths (\n"
        "    institute character varying(512),\n"
        "    course character varying(64),\n"
        "    education_level character varying(128),\n"
        "    track character varying(256),\n"
        "    program character varying(512),\n"
        "    record_book_number character varying(64),\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT user_education_paths_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.user_preferences (\n"
        "    dnd_enabled boolean DEFAULT false NOT NULL,\n"
        "    dnd_start time without time zone,\n"
        "    dnd_end time without time zone,\n"
        "    timezone character varying(64),\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.user_profiles (\n"
        "    about character varying(4096),\n"
        "    telegram character varying(128),\n"
        "    status character varying(256),\n"
        "    achievements character varying(2048),\n"
        '    "position" character varying(256),\n'
        "    department character varying(256),\n"
        "    user_id uuid NOT NULL,\n"
        "    full_name character varying(256),\n"
        "    avatar_url character varying(2048),\n"
        "    cover_url character varying(2048),\n"
        "    CONSTRAINT user_profile_details_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.user_push_topics (\n"
        "    topics json NOT NULL,\n"
        "    updated_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    CONSTRAINT user_push_topics_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.user_stats (\n"
        "    user_id uuid NOT NULL,\n"
        "    attendance_percent double precision DEFAULT '0'::double precision NOT NULL,\n"
        "    attendance_present integer DEFAULT 0 NOT NULL,\n"
        "    attendance_total integer DEFAULT 0 NOT NULL,\n"
        "    attendance_trend double precision DEFAULT '0'::double precision NOT NULL,\n"
        "    grades_average double precision DEFAULT '0'::double precision NOT NULL,\n"
        "    grades_trend double precision DEFAULT '0'::double precision NOT NULL,\n"
        "    participation_events integer DEFAULT 0 NOT NULL,\n"
        "    participation_hours double precision DEFAULT '0'::double precision NOT NULL,\n"
        "    participation_groups integer DEFAULT 0 NOT NULL,\n"
        "    participation_trend integer DEFAULT 0 NOT NULL,\n"
        "    last_computed_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT user_stats_pkey PRIMARY KEY (user_id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.users (\n"
        "    email character varying(254) NOT NULL,\n"
        "    hashed_password character varying NOT NULL,\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    role public.userrole DEFAULT 'student'::public.userrole NOT NULL,\n"
        "    mfa_required boolean DEFAULT false NOT NULL,\n"
        "    mfa_default_method character varying(64),\n"
        "    mfa_last_verified_at timestamp with time zone,\n"
        "    id uuid NOT NULL,\n"
        "    group_id uuid,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    pending_email character varying,\n"
        "    tenant_id uuid,\n"
        "    email_verified_at timestamp with time zone,\n"
        "    email_mfa_enabled_at timestamp with time zone,\n"
        "    mfa_epoch integer DEFAULT 0 NOT NULL,\n"
        "    demo_seed_key character varying(96),\n"
        "    CONSTRAINT users_pkey PRIMARY KEY (id)\n"
        ")"
    ),
    (
        "CREATE TABLE public.vector_chunks (\n"
        "    tenant_id uuid NOT NULL,\n"
        "    course_id character varying(256),\n"
        "    document_id character varying(256) NOT NULL,\n"
        "    chunk_index integer DEFAULT 0 NOT NULL,\n"
        "    content text NOT NULL,\n"
        "    embedding public.vector(1536),\n"
        "    payload json,\n"
        "    is_active boolean DEFAULT true NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    updated_at timestamp with time zone,\n"
        "    id uuid NOT NULL,\n"
        "    CONSTRAINT vector_chunks_pkey PRIMARY KEY (id)\n"
        ")"
    ),
)

# AUD-272 claim ledger. One claim per notification, subscription and channel;
# NULL subscriptions compare equal (NULLS NOT DISTINCT), so in-app rows count too.
_DELIVERY_ONCE_TABLE: tuple[str, ...] = (
    (
        "CREATE TABLE public.notification_delivery_once (\n"
        "    id uuid NOT NULL,\n"
        "    notification_id uuid NOT NULL,\n"
        "    subscription_id uuid,\n"
        "    channel character varying(50) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    CONSTRAINT notification_delivery_once_pkey PRIMARY KEY (id)\n"
        ")"
    ),
)

_SEQUENCE_DEFAULTS: tuple[str, ...] = (
    (
        "ALTER SEQUENCE public.dead_letter_jobs_id_seq OWNED BY "
        "public.dead_letter_jobs.id"
    ),
    (
        "ALTER TABLE ONLY public.dead_letter_jobs ALTER COLUMN id SET DEFAULT "
        "nextval('public.dead_letter_jobs_id_seq'::regclass)"
    ),
)

# Primary keys are declared in CREATE TABLE, before any table can hold rows.
# Other constraints retain their original dependency order and definitions.
_CONSTRAINTS: tuple[str, ...] = (
    (
        "ALTER TABLE ONLY public.cwv_observations\n"
        "    ADD CONSTRAINT cwv_observations_metric_id_key UNIQUE (metric_id)"
    ),
    (
        "ALTER TABLE ONLY public.dead_letter_jobs\n"
        "    ADD CONSTRAINT dead_letter_jobs_job_hash_key UNIQUE (job_hash)"
    ),
    (
        "ALTER TABLE ONLY public.mfa_email_deliveries\n"
        "    ADD CONSTRAINT mfa_email_deliveries_message_id_key UNIQUE (message_id)"
    ),
    (
        "ALTER TABLE ONLY public.notification_deliveries\n"
        "    ADD CONSTRAINT uq_notification_delivery_once UNIQUE (notification_id, "
        "channel, subscription_id, attempted_at)"
    ),
    (
        "ALTER TABLE ONLY public.chat_read_receipts\n"
        "    ADD CONSTRAINT uq_chat_read_receipts_chat_user UNIQUE (chat_id, user_id)"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT uq_chat_send_receipts_chat_user_key UNIQUE (chat_id, "
        "user_id, key_digest)"
    ),
    (
        "ALTER TABLE ONLY public.chats\n"
        "    ADD CONSTRAINT uq_chats_demo_seed_key UNIQUE (demo_seed_key)"
    ),
    (
        "ALTER TABLE ONLY public.cwv_observations\n"
        "    ADD CONSTRAINT uq_cwv_manual_sample_bucket UNIQUE (release_sha, "
        "deployment_run_id, deployment_run_attempt, collector_id, route_group, "
        "metric, sampling_bucket)"
    ),
    (
        "ALTER TABLE ONLY public.cwv_observations\n"
        "    ADD CONSTRAINT uq_cwv_navigation_metric UNIQUE (navigation_id, metric)"
    ),
    (
        "ALTER TABLE ONLY public.cwv_observations\n"
        "    ADD CONSTRAINT uq_cwv_nonce_metric UNIQUE (envelope_nonce, metric)"
    ),
    (
        "ALTER TABLE ONLY public.event_attendance\n"
        "    ADD CONSTRAINT uq_event_attendance_user_event UNIQUE (user_id, event_id)"
    ),
    (
        "ALTER TABLE ONLY public.groups\n"
        "    ADD CONSTRAINT uq_groups_demo_seed_key UNIQUE (demo_seed_key)"
    ),
    (
        "ALTER TABLE ONLY public.message_reactions\n"
        "    ADD CONSTRAINT uq_message_reactions_user_message_emoji UNIQUE (user_id, "
        "message_id, emoji)"
    ),
    (
        "ALTER TABLE ONLY public.mfa_email_deliveries\n"
        "    ADD CONSTRAINT uq_mfa_email_delivery_challenge_revision UNIQUE "
        "(challenge_id, revision)"
    ),
    (
        "ALTER TABLE ONLY public.news_likes\n"
        "    ADD CONSTRAINT uq_news_like_user_news UNIQUE (user_id, news_id)"
    ),
    (
        "ALTER TABLE ONLY public.news_media_assets\n"
        "    ADD CONSTRAINT uq_news_media_asset_news_id UNIQUE (news_id)"
    ),
    (
        "ALTER TABLE ONLY public.news_media_assets\n"
        "    ADD CONSTRAINT uq_news_media_asset_storage_url UNIQUE (storage_url)"
    ),
    (
        "ALTER TABLE ONLY public.notification_queue_jobs\n"
        "    ADD CONSTRAINT uq_notification_queue_jobs_kind_record UNIQUE (kind, "
        "record_id)"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_reservations\n"
        "    ADD CONSTRAINT uq_quarantine_reservation_object UNIQUE (scope_id, "
        "object_key)"
    ),
    (
        "ALTER TABLE ONLY public.users\n"
        "    ADD CONSTRAINT uq_users_demo_seed_key UNIQUE (demo_seed_key)"
    ),
    ("ALTER TABLE ONLY public.users\n    ADD CONSTRAINT uq_users_email UNIQUE (email)"),
)

_DELIVERY_ONCE_CONSTRAINTS: tuple[str, ...] = (
    (
        "ALTER TABLE ONLY public.notification_delivery_once ADD CONSTRAINT "
        "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT "
        "(notification_id, subscription_id, channel)"
    ),
)

_FOREIGN_KEYS: tuple[str, ...] = (
    (
        "ALTER TABLE ONLY public.chat_read_receipts\n"
        "    ADD CONSTRAINT chat_read_receipts_chat_id_fkey FOREIGN KEY (chat_id) "
        "REFERENCES public.chats(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_read_receipts\n"
        "    ADD CONSTRAINT chat_read_receipts_user_id_fkey FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_chat_id_fkey FOREIGN KEY (chat_id) "
        "REFERENCES public.chats(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_message_id_fkey FOREIGN KEY "
        "(message_id) REFERENCES public.messages(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_user_id_fkey FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chats\n"
        "    ADD CONSTRAINT chats_created_by_fkey FOREIGN KEY (created_by) "
        "REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.chats\n"
        "    ADD CONSTRAINT chats_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES "
        "public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.events\n"
        "    ADD CONSTRAINT events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES "
        "public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.active_sessions\n"
        "    ADD CONSTRAINT fk_active_sessions_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.attachments\n"
        "    ADD CONSTRAINT fk_attachments_message_id FOREIGN KEY (message_id) "
        "REFERENCES public.messages(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_participants\n"
        "    ADD CONSTRAINT fk_chat_participants_chat_id FOREIGN KEY (chat_id) "
        "REFERENCES public.chats(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_participants\n"
        "    ADD CONSTRAINT fk_chat_participants_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE public.data_access_logs\n"
        "    ADD CONSTRAINT fk_data_access_logs_actor_user_id FOREIGN KEY "
        "(actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE public.data_access_logs\n"
        "    ADD CONSTRAINT fk_data_access_logs_subject_user_id FOREIGN KEY "
        "(subject_user_id) REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.email_change_tokens\n"
        "    ADD CONSTRAINT fk_email_change_tokens_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.event_attendance\n"
        "    ADD CONSTRAINT fk_event_attendance_event_id FOREIGN KEY (event_id) "
        "REFERENCES public.events(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.event_attendance\n"
        "    ADD CONSTRAINT fk_event_attendance_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.event_files\n"
        "    ADD CONSTRAINT fk_event_files_event_id FOREIGN KEY (event_id) "
        "REFERENCES public.events(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.events\n"
        "    ADD CONSTRAINT fk_events_created_by FOREIGN KEY (created_by) REFERENCES "
        "public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE public.failed_login_attempts\n"
        "    ADD CONSTRAINT fk_failed_login_attempts_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.invite_codes\n"
        "    ADD CONSTRAINT fk_invite_codes_used_by_user_id FOREIGN KEY "
        "(used_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.login_history\n"
        "    ADD CONSTRAINT fk_login_history_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT fk_messages_chat_id FOREIGN KEY (chat_id) REFERENCES "
        "public.chats(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT fk_messages_sender_id FOREIGN KEY (sender_id) REFERENCES "
        "public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.mfa_challenges\n"
        "    ADD CONSTRAINT fk_mfa_challenges_session_id FOREIGN KEY (session_id) "
        "REFERENCES public.active_sessions(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.mfa_challenges\n"
        "    ADD CONSTRAINT fk_mfa_challenges_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.mfa_totp_enrollments\n"
        "    ADD CONSTRAINT fk_mfa_totp_enrollments_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.news\n"
        "    ADD CONSTRAINT fk_news_author_id FOREIGN KEY (author_id) REFERENCES "
        "public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.news_comments\n"
        "    ADD CONSTRAINT fk_news_comments_news_id FOREIGN KEY (news_id) "
        "REFERENCES public.news(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.news_comments\n"
        "    ADD CONSTRAINT fk_news_comments_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.news_likes\n"
        "    ADD CONSTRAINT fk_news_likes_news_id FOREIGN KEY (news_id) REFERENCES "
        "public.news(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.news_likes\n"
        "    ADD CONSTRAINT fk_news_likes_user_id FOREIGN KEY (user_id) REFERENCES "
        "public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE public.notification_deliveries\n"
        "    ADD CONSTRAINT fk_notification_deliveries_notification FOREIGN KEY "
        "(notification_id, notification_created_at) REFERENCES "
        "public.notifications(id, created_at) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE public.notifications\n"
        "    ADD CONSTRAINT fk_notifications_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.password_reset_tokens\n"
        "    ADD CONSTRAINT fk_password_reset_tokens_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.push_subscriptions\n"
        "    ADD CONSTRAINT fk_push_subscriptions_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.recovery_codes\n"
        "    ADD CONSTRAINT fk_recovery_codes_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.schedule\n"
        "    ADD CONSTRAINT fk_schedule_creator_id FOREIGN KEY (creator_id) "
        "REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.schedule\n"
        "    ADD CONSTRAINT fk_schedule_group_id FOREIGN KEY (group_id) REFERENCES "
        "public.groups(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.spotify_integrations\n"
        "    ADD CONSTRAINT fk_spotify_integrations_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.stories\n"
        "    ADD CONSTRAINT fk_stories_created_by FOREIGN KEY (created_by) "
        "REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.trusted_devices\n"
        "    ADD CONSTRAINT fk_trusted_devices_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.user_education_paths\n"
        "    ADD CONSTRAINT fk_user_education_paths_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.user_preferences\n"
        "    ADD CONSTRAINT fk_user_preferences_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.user_profiles\n"
        "    ADD CONSTRAINT fk_user_profiles_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.user_push_topics\n"
        "    ADD CONSTRAINT fk_user_push_topics_user_id FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.users\n"
        "    ADD CONSTRAINT fk_users_group_id FOREIGN KEY (group_id) REFERENCES "
        "public.groups(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.grades\n"
        "    ADD CONSTRAINT grades_assigned_by_fkey FOREIGN KEY (assigned_by) "
        "REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.grades\n"
        "    ADD CONSTRAINT grades_student_id_fkey FOREIGN KEY (student_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.groups\n"
        "    ADD CONSTRAINT groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES "
        "public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.message_reactions\n"
        "    ADD CONSTRAINT message_reactions_message_id_fkey FOREIGN KEY "
        "(message_id) REFERENCES public.messages(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.message_reactions\n"
        "    ADD CONSTRAINT message_reactions_user_id_fkey FOREIGN KEY (user_id) "
        "REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT messages_forwarded_from_chat_id_fkey FOREIGN KEY "
        "(forwarded_from_chat_id) REFERENCES public.chats(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT messages_forwarded_from_message_id_fkey FOREIGN KEY "
        "(forwarded_from_message_id) REFERENCES public.messages(id) ON DELETE SET "
        "NULL"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT messages_reply_to_message_id_fkey FOREIGN KEY "
        "(reply_to_message_id) REFERENCES public.messages(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.messages\n"
        "    ADD CONSTRAINT messages_tenant_id_fkey FOREIGN KEY (tenant_id) "
        "REFERENCES public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.mfa_email_deliveries\n"
        "    ADD CONSTRAINT mfa_email_deliveries_challenge_id_fkey FOREIGN KEY "
        "(challenge_id) REFERENCES public.mfa_challenges(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.news_media_assets\n"
        "    ADD CONSTRAINT news_media_assets_news_id_fkey FOREIGN KEY (news_id) "
        "REFERENCES public.news(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.news_media_assets\n"
        "    ADD CONSTRAINT news_media_assets_owner_user_id_fkey FOREIGN KEY "
        "(owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.news\n"
        "    ADD CONSTRAINT news_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES "
        "public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE public.notifications\n"
        "    ADD CONSTRAINT notifications_tenant_id_fkey FOREIGN KEY (tenant_id) "
        "REFERENCES public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_reservations\n"
        "    ADD CONSTRAINT quarantine_reservations_scope_id_fkey FOREIGN KEY "
        "(scope_id) REFERENCES public.quarantine_storage_scopes(scope_id)"
    ),
    (
        "ALTER TABLE ONLY public.schedule\n"
        "    ADD CONSTRAINT schedule_tenant_id_fkey FOREIGN KEY (tenant_id) "
        "REFERENCES public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.stories\n"
        "    ADD CONSTRAINT stories_tenant_id_fkey FOREIGN KEY (tenant_id) "
        "REFERENCES public.tenants(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.user_stats\n"
        "    ADD CONSTRAINT user_stats_user_id_fkey FOREIGN KEY (user_id) REFERENCES "
        "public.users(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.users\n"
        "    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES "
        "public.tenants(id) ON DELETE CASCADE"
    ),
)

_INDEXES: tuple[str, ...] = (
    (
        "CREATE INDEX ix_data_access_logs_action ON ONLY public.data_access_logs "
        "USING btree (action)"
    ),
    (
        "CREATE INDEX ix_data_access_logs_actor_user_id ON ONLY "
        "public.data_access_logs USING btree (actor_user_id)"
    ),
    (
        "CREATE INDEX ix_data_access_logs_created_at ON ONLY public.data_access_logs "
        "USING btree (created_at)"
    ),
    (
        "CREATE INDEX ix_data_access_logs_resource_id ON ONLY "
        "public.data_access_logs USING btree (resource_id)"
    ),
    (
        "CREATE INDEX ix_data_access_logs_resource_type ON ONLY "
        "public.data_access_logs USING btree (resource_type)"
    ),
    (
        "CREATE INDEX ix_data_access_logs_subject_user_id ON ONLY "
        "public.data_access_logs USING btree (subject_user_id)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_attempted_at ON ONLY "
        "public.failed_login_attempts USING btree (attempted_at)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_email_attempted_at ON ONLY "
        "public.failed_login_attempts USING btree (email, attempted_at)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_email ON ONLY "
        "public.failed_login_attempts USING btree (email)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_ip_attempted_at ON ONLY "
        "public.failed_login_attempts USING btree (ip_address, attempted_at)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_ip_address ON ONLY "
        "public.failed_login_attempts USING btree (ip_address)"
    ),
    (
        "CREATE INDEX ix_failed_login_attempts_user_id ON ONLY "
        "public.failed_login_attempts USING btree (user_id)"
    ),
    (
        "CREATE INDEX idx_messages_chat_pagination_covering ON public.messages USING "
        "btree (chat_id, created_at DESC, id DESC) INCLUDE (sender_id, read_status)"
    ),
    (
        "CREATE INDEX idx_news_comment_cursor ON public.news_comments USING btree "
        "(news_id, created_at, id)"
    ),
    (
        "CREATE INDEX ix_active_sessions_expires_at ON public.active_sessions USING "
        "btree (expires_at)"
    ),
    (
        "CREATE INDEX ix_active_sessions_fingerprint_hash ON public.active_sessions "
        "USING btree (fingerprint_hash)"
    ),
    (
        "CREATE UNIQUE INDEX ix_active_sessions_jti ON public.active_sessions USING "
        "btree (jti)"
    ),
    (
        "CREATE INDEX ix_active_sessions_last_seen_at ON public.active_sessions "
        "USING btree (last_seen_at)"
    ),
    (
        "CREATE INDEX ix_active_sessions_mfa_completed_at ON public.active_sessions "
        "USING btree (mfa_completed_at)"
    ),
    (
        "CREATE INDEX ix_active_sessions_mfa_required ON public.active_sessions "
        "USING btree (mfa_required)"
    ),
    (
        "CREATE INDEX ix_active_sessions_mfa_verified_at ON public.active_sessions "
        "USING btree (mfa_verified_at)"
    ),
    (
        "CREATE INDEX ix_active_sessions_revoked_at ON public.active_sessions USING "
        "btree (revoked_at)"
    ),
    (
        "CREATE INDEX ix_active_sessions_user_id ON public.active_sessions USING "
        "btree (user_id)"
    ),
    (
        "CREATE INDEX ix_active_sessions_user_id_expires_at ON "
        "public.active_sessions USING btree (user_id, expires_at)"
    ),
    (
        "CREATE INDEX ix_attachments_message_id ON public.attachments USING btree "
        "(message_id)"
    ),
    (
        "CREATE INDEX ix_chat_participants_chat_id_user_id ON "
        "public.chat_participants USING btree (chat_id, user_id)"
    ),
    (
        "CREATE INDEX ix_chat_participants_user_id_chat_id ON "
        "public.chat_participants USING btree (user_id, chat_id)"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_expires_at ON public.chat_send_receipts "
        "USING btree (expires_at, id)"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_message_id ON public.chat_send_receipts "
        "USING btree (message_id)"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_user_id ON public.chat_send_receipts "
        "USING btree (user_id)"
    ),
    "CREATE INDEX ix_chats_tenant_id ON public.chats USING btree (tenant_id)",
    (
        "CREATE INDEX ix_cwv_created_at ON public.cwv_observations USING btree "
        "(created_at)"
    ),
    (
        "CREATE INDEX ix_cwv_release_deployment_observed ON public.cwv_observations "
        "USING btree (release_sha, frontend_image_digest, deployment_run_id, "
        "deployment_run_attempt, observed_at)"
    ),
    (
        "CREATE INDEX ix_dead_letter_jobs_job_type ON public.dead_letter_jobs USING "
        "btree (job_type)"
    ),
    (
        "CREATE INDEX ix_dead_letter_jobs_next_retry_at ON public.dead_letter_jobs "
        "USING btree (next_retry_at)"
    ),
    (
        "CREATE INDEX ix_dead_letter_jobs_status ON public.dead_letter_jobs USING "
        "btree (status)"
    ),
    (
        "CREATE INDEX ix_dlq_status_next_retry ON public.dead_letter_jobs USING "
        "btree (status, next_retry_at)"
    ),
    (
        "CREATE INDEX ix_email_change_tokens_created_at ON "
        "public.email_change_tokens USING btree (created_at)"
    ),
    (
        "CREATE INDEX ix_email_change_tokens_expires_at ON "
        "public.email_change_tokens USING btree (expires_at)"
    ),
    (
        "CREATE INDEX ix_email_change_tokens_new_email ON public.email_change_tokens "
        "USING btree (new_email)"
    ),
    (
        "CREATE UNIQUE INDEX ix_email_change_tokens_token_hash ON "
        "public.email_change_tokens USING btree (token_hash)"
    ),
    (
        "CREATE INDEX ix_email_change_tokens_used ON public.email_change_tokens "
        "USING btree (used)"
    ),
    (
        "CREATE INDEX ix_email_change_tokens_user_id ON public.email_change_tokens "
        "USING btree (user_id)"
    ),
    (
        "CREATE INDEX ix_event_attendance_event_id ON public.event_attendance USING "
        "btree (event_id)"
    ),
    (
        "CREATE INDEX ix_event_attendance_event_user ON public.event_attendance "
        "USING btree (event_id, user_id)"
    ),
    (
        "CREATE INDEX ix_event_attendance_registered_at ON public.event_attendance "
        "USING btree (registered_at)"
    ),
    (
        "CREATE INDEX ix_event_attendance_user_id ON public.event_attendance USING "
        "btree (user_id)"
    ),
    (
        "CREATE INDEX ix_event_files_event_id ON public.event_files USING btree "
        "(event_id)"
    ),
    "CREATE INDEX ix_events_created_at ON public.events USING btree (created_at)",
    "CREATE INDEX ix_events_created_by ON public.events USING btree (created_by)",
    (
        "CREATE INDEX ix_events_embedding ON public.events USING hnsw (embedding "
        "public.vector_cosine_ops)"
    ),
    "CREATE INDEX ix_events_ends_at ON public.events USING btree (ends_at)",
    "CREATE INDEX ix_events_event_type ON public.events USING btree (event_type)",
    "CREATE INDEX ix_events_is_active ON public.events USING btree (is_active)",
    ("CREATE INDEX ix_events_search_vector ON public.events USING gin (search_vector)"),
    "CREATE INDEX ix_events_starts_at ON public.events USING btree (starts_at)",
    (
        "CREATE INDEX ix_events_starts_at_is_active ON public.events USING btree "
        "(starts_at, is_active)"
    ),
    "CREATE INDEX ix_events_tenant_id ON public.events USING btree (tenant_id)",
    "CREATE INDEX ix_events_title ON public.events USING btree (title)",
    (
        "CREATE INDEX ix_failed_outbox_events_aggregate_id ON "
        "public.failed_outbox_events USING btree (aggregate_id)"
    ),
    (
        "CREATE INDEX ix_failed_outbox_events_event_type ON "
        "public.failed_outbox_events USING btree (event_type)"
    ),
    (
        "CREATE INDEX ix_failed_outbox_events_failed_at ON "
        "public.failed_outbox_events USING btree (failed_at)"
    ),
    (
        "CREATE INDEX ix_failed_outbox_events_original_event_id ON "
        "public.failed_outbox_events USING btree (original_event_id)"
    ),
    "CREATE INDEX ix_grades_student_id ON public.grades USING btree (student_id)",
    (
        "CREATE INDEX ix_grades_student_subject ON public.grades USING btree "
        "(student_id, subject)"
    ),
    "CREATE INDEX ix_grades_subject ON public.grades USING btree (subject)",
    "CREATE INDEX ix_groups_name ON public.groups USING btree (name)",
    "CREATE INDEX ix_groups_tenant_id ON public.groups USING btree (tenant_id)",
    (
        "CREATE UNIQUE INDEX ix_invite_codes_code ON public.invite_codes USING btree "
        "(code)"
    ),
    (
        "CREATE INDEX ix_invite_codes_created_at ON public.invite_codes USING btree "
        "(created_at)"
    ),
    (
        "CREATE INDEX ix_invite_codes_is_active ON public.invite_codes USING btree "
        "(is_active)"
    ),
    (
        "CREATE INDEX ix_invite_codes_is_used ON public.invite_codes USING btree "
        "(is_used)"
    ),
    (
        "CREATE INDEX ix_invite_codes_used_by_user_id ON public.invite_codes USING "
        "btree (used_by_user_id)"
    ),
    (
        "CREATE INDEX ix_login_history_created_at ON public.login_history USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_login_history_user_id ON public.login_history USING btree "
        "(user_id)"
    ),
    (
        "CREATE INDEX ix_message_reactions_message_id ON public.message_reactions "
        "USING btree (message_id)"
    ),
    (
        "CREATE INDEX ix_messages_forwarded_from_message_id ON public.messages USING "
        "btree (forwarded_from_message_id)"
    ),
    (
        "CREATE INDEX ix_messages_reply_to_message_id ON public.messages USING btree "
        "(reply_to_message_id)"
    ),
    ("CREATE INDEX ix_messages_tenant_id ON public.messages USING btree (tenant_id)"),
    (
        "CREATE INDEX ix_messages_unread_chat_sender ON public.messages USING btree "
        "(chat_id, sender_id) WHERE (read_status = false)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_binding ON public.mfa_challenges USING btree "
        "(user_id, flow, session_identifier, method)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_challenge_type ON public.mfa_challenges "
        "USING btree (challenge_type)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_consumed_at ON public.mfa_challenges USING "
        "btree (consumed_at)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_consumed_expires ON public.mfa_challenges "
        "USING btree (consumed_at, expires_at)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_expires_at ON public.mfa_challenges USING "
        "btree (expires_at)"
    ),
    ("CREATE INDEX ix_mfa_challenges_flow ON public.mfa_challenges USING btree (flow)"),
    (
        "CREATE INDEX ix_mfa_challenges_method ON public.mfa_challenges USING btree "
        "(method)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_resend_available_at ON public.mfa_challenges "
        "USING btree (resend_available_at)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_session_id ON public.mfa_challenges USING "
        "btree (session_id)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_session_identifier ON public.mfa_challenges "
        "USING btree (session_identifier)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_state ON public.mfa_challenges USING btree "
        "(state)"
    ),
    (
        "CREATE UNIQUE INDEX ix_mfa_challenges_token_digest ON public.mfa_challenges "
        "USING btree (token_digest)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_user_expires ON public.mfa_challenges USING "
        "btree (user_id, expires_at)"
    ),
    (
        "CREATE INDEX ix_mfa_challenges_user_id ON public.mfa_challenges USING btree "
        "(user_id)"
    ),
    (
        "CREATE INDEX ix_mfa_email_deliveries_challenge_id ON "
        "public.mfa_email_deliveries USING btree (challenge_id)"
    ),
    (
        "CREATE INDEX ix_mfa_email_deliveries_pending_created ON "
        "public.mfa_email_deliveries USING btree (created_at, id) WHERE "
        "((status)::text = 'pending'::text)"
    ),
    (
        "CREATE INDEX ix_mfa_totp_enrollments_active ON public.mfa_totp_enrollments "
        "USING btree (user_id, is_active)"
    ),
    (
        "CREATE INDEX ix_mfa_totp_enrollments_confirmed_at ON "
        "public.mfa_totp_enrollments USING btree (confirmed_at)"
    ),
    (
        "CREATE INDEX ix_mfa_totp_enrollments_is_active ON "
        "public.mfa_totp_enrollments USING btree (is_active)"
    ),
    (
        "CREATE INDEX ix_mfa_totp_enrollments_revoked_at ON "
        "public.mfa_totp_enrollments USING btree (revoked_at)"
    ),
    (
        "CREATE INDEX ix_mfa_totp_enrollments_user_id ON public.mfa_totp_enrollments "
        "USING btree (user_id)"
    ),
    "CREATE INDEX ix_news_author_id ON public.news USING btree (author_id)",
    (
        "CREATE INDEX ix_news_comments_created_at ON public.news_comments USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_news_comments_news_created ON public.news_comments USING "
        "btree (news_id, created_at)"
    ),
    (
        "CREATE INDEX ix_news_comments_news_id ON public.news_comments USING btree "
        "(news_id)"
    ),
    (
        "CREATE INDEX ix_news_comments_user_id ON public.news_comments USING btree "
        "(user_id)"
    ),
    "CREATE INDEX ix_news_created_at ON public.news USING btree (created_at)",
    (
        "CREATE INDEX ix_news_embedding ON public.news USING hnsw (embedding "
        "public.vector_cosine_ops)"
    ),
    (
        "CREATE INDEX ix_news_likes_created_at ON public.news_likes USING btree "
        "(created_at)"
    ),
    (
        "CREATE INDEX ix_news_likes_news_created ON public.news_likes USING btree "
        "(news_id, created_at)"
    ),
    ("CREATE INDEX ix_news_likes_news_id ON public.news_likes USING btree (news_id)"),
    ("CREATE INDEX ix_news_likes_user_id ON public.news_likes USING btree (user_id)"),
    (
        "CREATE INDEX ix_news_media_assets_owner_user_id ON public.news_media_assets "
        "USING btree (owner_user_id)"
    ),
    "CREATE INDEX ix_news_tenant_id ON public.news USING btree (tenant_id)",
    "CREATE INDEX ix_news_title ON public.news USING btree (title)",
    (
        "CREATE INDEX ix_notification_deliveries_attempted_at ON ONLY "
        "public.notification_deliveries USING btree (attempted_at)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_channel ON ONLY "
        "public.notification_deliveries USING btree (channel)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_dedup ON ONLY "
        "public.notification_deliveries USING btree (notification_id, channel, "
        "subscription_id)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_delivered_at ON ONLY "
        "public.notification_deliveries USING btree (delivered_at)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_notif_channel ON ONLY "
        "public.notification_deliveries USING btree (notification_id, channel)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_notification_id ON ONLY "
        "public.notification_deliveries USING btree (notification_id)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_status ON ONLY "
        "public.notification_deliveries USING btree (status)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_subscription_id ON ONLY "
        "public.notification_deliveries USING btree (subscription_id)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_claimed_at ON "
        "public.notification_queue_jobs USING btree (claimed_at)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_dead_lettered ON "
        "public.notification_queue_jobs USING btree (dead_lettered)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_kind ON "
        "public.notification_queue_jobs USING btree (kind)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_kind_record ON "
        "public.notification_queue_jobs USING btree (kind, record_id)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_next_retry_at ON "
        "public.notification_queue_jobs USING btree (next_retry_at)"
    ),
    (
        "CREATE INDEX ix_notification_queue_jobs_pending_claim ON "
        "public.notification_queue_jobs USING btree (next_retry_at, enqueued_at, id)"
    ),
    (
        "CREATE INDEX ix_notifications_created_at ON ONLY public.notifications USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_notifications_dedupe_key ON ONLY public.notifications USING "
        "btree (dedupe_key)"
    ),
    (
        "CREATE INDEX ix_notifications_dupe_check ON ONLY public.notifications USING "
        "btree (user_id, title, url, created_at)"
    ),
    (
        "CREATE INDEX ix_notifications_read ON ONLY public.notifications USING btree "
        "(read)"
    ),
    (
        "CREATE INDEX ix_notifications_read_at ON ONLY public.notifications USING "
        "btree (read_at)"
    ),
    (
        "CREATE INDEX ix_notifications_tenant_id ON ONLY public.notifications USING "
        "btree (tenant_id)"
    ),
    (
        "CREATE INDEX ix_notifications_title ON ONLY public.notifications USING "
        "btree (title)"
    ),
    (
        "CREATE INDEX ix_notifications_type ON ONLY public.notifications USING btree "
        "(type)"
    ),
    (
        "CREATE INDEX ix_notifications_user_created ON ONLY public.notifications "
        "USING btree (user_id, created_at)"
    ),
    (
        "CREATE INDEX ix_notifications_user_dedupe ON ONLY public.notifications "
        "USING btree (user_id, dedupe_key)"
    ),
    (
        "CREATE INDEX ix_notifications_user_id ON ONLY public.notifications USING "
        "btree (user_id)"
    ),
    (
        "CREATE INDEX ix_notifications_user_id_read ON ONLY public.notifications "
        "USING btree (user_id, read)"
    ),
    (
        "CREATE INDEX ix_password_reset_tokens_created_at ON "
        "public.password_reset_tokens USING btree (created_at)"
    ),
    (
        "CREATE INDEX ix_password_reset_tokens_expires_at ON "
        "public.password_reset_tokens USING btree (expires_at)"
    ),
    (
        "CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON "
        "public.password_reset_tokens USING btree (token_hash)"
    ),
    (
        "CREATE INDEX ix_password_reset_tokens_used ON public.password_reset_tokens "
        "USING btree (used)"
    ),
    (
        "CREATE INDEX ix_password_reset_tokens_user_id ON "
        "public.password_reset_tokens USING btree (user_id)"
    ),
    (
        "CREATE INDEX ix_push_subscriptions_created_at ON public.push_subscriptions "
        "USING btree (created_at)"
    ),
    (
        "CREATE UNIQUE INDEX ix_push_subscriptions_endpoint ON "
        "public.push_subscriptions USING btree (endpoint)"
    ),
    (
        "CREATE INDEX ix_push_subscriptions_last_seen_at ON "
        "public.push_subscriptions USING btree (last_seen_at)"
    ),
    (
        "CREATE INDEX ix_push_subscriptions_user_id ON public.push_subscriptions "
        "USING btree (user_id)"
    ),
    (
        "CREATE INDEX ix_quarantine_reservations_expiry ON "
        "public.quarantine_reservations USING btree (scope_id, status, expires_at)"
    ),
    (
        "CREATE INDEX ix_recovery_codes_is_used ON public.recovery_codes USING btree "
        "(is_used)"
    ),
    (
        "CREATE INDEX ix_recovery_codes_user_id ON public.recovery_codes USING btree "
        "(user_id)"
    ),
    (
        "CREATE INDEX ix_schedule_creator_id ON public.schedule USING btree "
        "(creator_id) WHERE (creator_id IS NOT NULL)"
    ),
    "CREATE INDEX ix_schedule_end_time ON public.schedule USING btree (end_time)",
    "CREATE INDEX ix_schedule_group_id ON public.schedule USING btree (group_id)",
    (
        "CREATE INDEX ix_schedule_group_start_time ON public.schedule USING btree "
        "(group_id, start_time)"
    ),
    "CREATE INDEX ix_schedule_parity ON public.schedule USING btree (parity)",
    ("CREATE INDEX ix_schedule_start_time ON public.schedule USING btree (start_time)"),
    ("CREATE INDEX ix_schedule_tenant_id ON public.schedule USING btree (tenant_id)"),
    "CREATE INDEX ix_schedule_weekday ON public.schedule USING btree (weekday)",
    (
        "CREATE INDEX ix_spotify_integrations_is_connected ON "
        "public.spotify_integrations USING btree (is_connected)"
    ),
    (
        "CREATE INDEX ix_spotify_integrations_is_playing ON "
        "public.spotify_integrations USING btree (is_playing)"
    ),
    (
        "CREATE INDEX ix_spotify_integrations_last_checked_at ON "
        "public.spotify_integrations USING btree (last_checked_at)"
    ),
    (
        "CREATE INDEX ix_spotify_integrations_last_track_id ON "
        "public.spotify_integrations USING btree (last_track_id)"
    ),
    (
        "CREATE UNIQUE INDEX ix_spotify_integrations_spotify_user_id ON "
        "public.spotify_integrations USING btree (spotify_user_id)"
    ),
    (
        "CREATE INDEX ix_spotify_integrations_token_expires_at ON "
        "public.spotify_integrations USING btree (token_expires_at)"
    ),
    (
        "CREATE INDEX ix_stored_events_aggregate_id ON public.stored_events USING "
        "btree (aggregate_id)"
    ),
    (
        "CREATE INDEX ix_stored_events_aggregate_id_uuid ON public.stored_events "
        "USING btree (aggregate_id_uuid)"
    ),
    (
        "CREATE INDEX ix_stored_events_aggregate_type ON public.stored_events USING "
        "btree (aggregate_type)"
    ),
    (
        "CREATE INDEX ix_stored_events_aggregate_uuid ON public.stored_events USING "
        "btree (aggregate_id_uuid, sequence_number) WHERE ((processed_at IS NULL) "
        "AND (aggregate_id_uuid IS NOT NULL))"
    ),
    (
        "CREATE INDEX ix_stored_events_created_at ON public.stored_events USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_stored_events_error_count ON public.stored_events USING "
        "btree (error_count)"
    ),
    (
        "CREATE INDEX ix_stored_events_event_type ON public.stored_events USING "
        "btree (event_type)"
    ),
    ("CREATE INDEX ix_stored_events_hash ON public.stored_events USING btree (hash)"),
    (
        "CREATE INDEX ix_stored_events_pending_aggregate_created ON "
        "public.stored_events USING btree (aggregate_id, created_at, id) WHERE "
        "(processed_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending_created ON public.stored_events USING "
        "btree (created_at, id) WHERE (processed_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_stored_events_processed_at ON public.stored_events USING "
        "btree (processed_at)"
    ),
    (
        "CREATE INDEX ix_stored_events_status ON public.stored_events USING btree "
        "(status)"
    ),
    (
        "CREATE INDEX ix_stored_events_subject ON public.stored_events USING btree "
        "(subject)"
    ),
    ("CREATE INDEX ix_stories_created_at ON public.stories USING btree (created_at)"),
    ("CREATE INDEX ix_stories_created_by ON public.stories USING btree (created_by)"),
    (
        "CREATE INDEX ix_stories_expires_at_is_active ON public.stories USING btree "
        "(expires_at, is_active)"
    ),
    "CREATE INDEX ix_stories_is_active ON public.stories USING btree (is_active)",
    "CREATE INDEX ix_stories_tenant_id ON public.stories USING btree (tenant_id)",
    "CREATE UNIQUE INDEX ix_tenants_domain ON public.tenants USING btree (domain)",
    "CREATE INDEX ix_tenants_is_active ON public.tenants USING btree (is_active)",
    "CREATE UNIQUE INDEX ix_tenants_slug ON public.tenants USING btree (slug)",
    (
        "CREATE INDEX ix_trusted_devices_expires_at ON public.trusted_devices USING "
        "btree (expires_at)"
    ),
    (
        "CREATE INDEX ix_trusted_devices_last_used_at ON public.trusted_devices "
        "USING btree (last_used_at)"
    ),
    (
        "CREATE UNIQUE INDEX ix_trusted_devices_token_hash ON public.trusted_devices "
        "USING btree (token_hash)"
    ),
    (
        "CREATE INDEX ix_trusted_devices_user_id ON public.trusted_devices USING "
        "btree (user_id)"
    ),
    (
        "CREATE INDEX ix_user_push_topics_user_id ON public.user_push_topics USING "
        "btree (user_id)"
    ),
    "CREATE INDEX ix_users_created_at ON public.users USING btree (created_at)",
    (
        "CREATE INDEX ix_users_email_mfa_enabled_at ON public.users USING btree "
        "(email_mfa_enabled_at)"
    ),
    (
        "CREATE INDEX ix_users_email_verified_at ON public.users USING btree "
        "(email_verified_at)"
    ),
    "CREATE INDEX ix_users_group_id ON public.users USING btree (group_id)",
    "CREATE INDEX ix_users_is_active ON public.users USING btree (is_active)",
    (
        "CREATE INDEX ix_users_mfa_last_verified_at ON public.users USING btree "
        "(mfa_last_verified_at)"
    ),
    ("CREATE INDEX ix_users_mfa_required ON public.users USING btree (mfa_required)"),
    "CREATE INDEX ix_users_role ON public.users USING btree (role)",
    "CREATE INDEX ix_users_tenant_id ON public.users USING btree (tenant_id)",
    (
        "CREATE INDEX ix_vector_chunks_chunk_index ON public.vector_chunks USING "
        "btree (chunk_index)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_course_id ON public.vector_chunks USING btree "
        "(course_id)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_created_at ON public.vector_chunks USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_document_id ON public.vector_chunks USING "
        "btree (document_id)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_embedding ON public.vector_chunks USING btree "
        "(embedding)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_is_active ON public.vector_chunks USING btree "
        "(is_active)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_tenant_course ON public.vector_chunks USING "
        "btree (tenant_id, course_id)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_tenant_doc ON public.vector_chunks USING "
        "btree (tenant_id, document_id)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_tenant_id ON public.vector_chunks USING btree "
        "(tenant_id)"
    ),
)

# AUD-269 hot-path indexes. Definitions are the catalog text immediately before
# revision 202603280001 dropped them. They precede the partitions so the partitioned
# notifications index propagates to every child partition.
_RESTORED_HOT_PATH_INDEXES: tuple[str, ...] = (
    (
        "CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree "
        "(lower((email)::text))"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_lower ON public.user_profiles USING "
        "btree (lower((full_name)::text) text_pattern_ops) WHERE (full_name IS NOT "
        "NULL)"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_trgm ON public.user_profiles USING "
        "gin (full_name public.gin_trgm_ops) WHERE (full_name IS NOT NULL)"
    ),
    (
        "CREATE INDEX idx_notifications_user_unread_created ON ONLY "
        "public.notifications USING btree (user_id, created_at DESC) WHERE (read = "
        "false)"
    ),
    (
        "CREATE INDEX idx_messages_chat_created ON public.messages USING btree "
        "(chat_id, created_at DESC)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending ON public.stored_events USING btree "
        "(status, created_at)"
    ),
    (
        "CREATE INDEX idx_active_sessions_user_valid ON public.active_sessions USING "
        "btree (user_id, revoked_at) WHERE (revoked_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_active_sessions_user_active_created ON "
        "public.active_sessions USING btree (user_id, created_at) WHERE (revoked_at "
        "IS NULL)"
    ),
)

# Monthly range partitions 2026-05 through 2028-05, plus one default partition per parent.
_PARTITIONS: tuple[str, ...] = (
    (
        "CREATE TABLE public.data_access_logs_2026_05 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-05-01 00:00:00+00') TO "
        "('2026-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_06 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-06-01 00:00:00+00') TO "
        "('2026-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_07 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-07-01 00:00:00+00') TO "
        "('2026-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_08 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-08-01 00:00:00+00') TO "
        "('2026-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_09 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-09-01 00:00:00+00') TO "
        "('2026-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_10 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-10-01 00:00:00+00') TO "
        "('2026-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_11 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-11-01 00:00:00+00') TO "
        "('2026-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2026_12 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-12-01 00:00:00+00') TO "
        "('2027-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_01 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-01-01 00:00:00+00') TO "
        "('2027-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_02 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-02-01 00:00:00+00') TO "
        "('2027-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_03 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-03-01 00:00:00+00') TO "
        "('2027-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_04 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-04-01 00:00:00+00') TO "
        "('2027-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_05 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-05-01 00:00:00+00') TO "
        "('2027-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_06 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-06-01 00:00:00+00') TO "
        "('2027-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_07 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-07-01 00:00:00+00') TO "
        "('2027-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_08 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-08-01 00:00:00+00') TO "
        "('2027-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_09 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-09-01 00:00:00+00') TO "
        "('2027-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_10 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-10-01 00:00:00+00') TO "
        "('2027-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_11 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-11-01 00:00:00+00') TO "
        "('2027-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2027_12 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2027-12-01 00:00:00+00') TO "
        "('2028-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2028_01 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2028-01-01 00:00:00+00') TO "
        "('2028-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2028_02 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2028-02-01 00:00:00+00') TO "
        "('2028-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2028_03 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2028-03-01 00:00:00+00') TO "
        "('2028-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2028_04 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2028-04-01 00:00:00+00') TO "
        "('2028-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_2028_05 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2028-05-01 00:00:00+00') TO "
        "('2028-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.data_access_logs_default PARTITION OF "
        "public.data_access_logs DEFAULT"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_05 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-05-01 00:00:00+00') TO "
        "('2026-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_06 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-06-01 00:00:00+00') TO "
        "('2026-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_07 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-07-01 00:00:00+00') TO "
        "('2026-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_08 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-08-01 00:00:00+00') TO "
        "('2026-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_09 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-09-01 00:00:00+00') TO "
        "('2026-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_10 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-10-01 00:00:00+00') TO "
        "('2026-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_11 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-11-01 00:00:00+00') TO "
        "('2026-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2026_12 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2026-12-01 00:00:00+00') TO "
        "('2027-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_01 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-01-01 00:00:00+00') TO "
        "('2027-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_02 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-02-01 00:00:00+00') TO "
        "('2027-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_03 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-03-01 00:00:00+00') TO "
        "('2027-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_04 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-04-01 00:00:00+00') TO "
        "('2027-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_05 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-05-01 00:00:00+00') TO "
        "('2027-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_06 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-06-01 00:00:00+00') TO "
        "('2027-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_07 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-07-01 00:00:00+00') TO "
        "('2027-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_08 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-08-01 00:00:00+00') TO "
        "('2027-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_09 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-09-01 00:00:00+00') TO "
        "('2027-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_10 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-10-01 00:00:00+00') TO "
        "('2027-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_11 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-11-01 00:00:00+00') TO "
        "('2027-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2027_12 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2027-12-01 00:00:00+00') TO "
        "('2028-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2028_01 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2028-01-01 00:00:00+00') TO "
        "('2028-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2028_02 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2028-02-01 00:00:00+00') TO "
        "('2028-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2028_03 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2028-03-01 00:00:00+00') TO "
        "('2028-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2028_04 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2028-04-01 00:00:00+00') TO "
        "('2028-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_2028_05 PARTITION OF "
        "public.failed_login_attempts FOR VALUES FROM ('2028-05-01 00:00:00+00') TO "
        "('2028-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.failed_login_attempts_default PARTITION OF "
        "public.failed_login_attempts DEFAULT"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_05 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-05-01 00:00:00+00') "
        "TO ('2026-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_06 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-06-01 00:00:00+00') "
        "TO ('2026-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_07 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-07-01 00:00:00+00') "
        "TO ('2026-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_08 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-08-01 00:00:00+00') "
        "TO ('2026-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_09 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-09-01 00:00:00+00') "
        "TO ('2026-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_10 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-10-01 00:00:00+00') "
        "TO ('2026-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_11 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-11-01 00:00:00+00') "
        "TO ('2026-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2026_12 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2026-12-01 00:00:00+00') "
        "TO ('2027-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_01 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-01-01 00:00:00+00') "
        "TO ('2027-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_02 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-02-01 00:00:00+00') "
        "TO ('2027-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_03 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-03-01 00:00:00+00') "
        "TO ('2027-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_04 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-04-01 00:00:00+00') "
        "TO ('2027-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_05 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-05-01 00:00:00+00') "
        "TO ('2027-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_06 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-06-01 00:00:00+00') "
        "TO ('2027-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_07 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-07-01 00:00:00+00') "
        "TO ('2027-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_08 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-08-01 00:00:00+00') "
        "TO ('2027-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_09 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-09-01 00:00:00+00') "
        "TO ('2027-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_10 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-10-01 00:00:00+00') "
        "TO ('2027-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_11 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-11-01 00:00:00+00') "
        "TO ('2027-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2027_12 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2027-12-01 00:00:00+00') "
        "TO ('2028-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2028_01 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2028-01-01 00:00:00+00') "
        "TO ('2028-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2028_02 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2028-02-01 00:00:00+00') "
        "TO ('2028-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2028_03 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2028-03-01 00:00:00+00') "
        "TO ('2028-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2028_04 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2028-04-01 00:00:00+00') "
        "TO ('2028-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_2028_05 PARTITION OF "
        "public.notification_deliveries FOR VALUES FROM ('2028-05-01 00:00:00+00') "
        "TO ('2028-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notification_deliveries_default PARTITION OF "
        "public.notification_deliveries DEFAULT"
    ),
    (
        "CREATE TABLE public.notifications_2026_05 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_06 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-06-01 00:00:00+00') TO ('2026-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_07 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_08 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_09 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_10 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_11 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2026_12 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_01 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_02 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-02-01 00:00:00+00') TO ('2027-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_03 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-03-01 00:00:00+00') TO ('2027-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_04 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-04-01 00:00:00+00') TO ('2027-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_05 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-05-01 00:00:00+00') TO ('2027-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_06 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-06-01 00:00:00+00') TO ('2027-07-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_07 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-07-01 00:00:00+00') TO ('2027-08-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_08 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-08-01 00:00:00+00') TO ('2027-09-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_09 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-09-01 00:00:00+00') TO ('2027-10-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_10 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-10-01 00:00:00+00') TO ('2027-11-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_11 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-11-01 00:00:00+00') TO ('2027-12-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2027_12 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2027-12-01 00:00:00+00') TO ('2028-01-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2028_01 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2028-01-01 00:00:00+00') TO ('2028-02-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2028_02 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2028-02-01 00:00:00+00') TO ('2028-03-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2028_03 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2028-03-01 00:00:00+00') TO ('2028-04-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2028_04 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2028-04-01 00:00:00+00') TO ('2028-05-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_2028_05 PARTITION OF public.notifications "
        "FOR VALUES FROM ('2028-05-01 00:00:00+00') TO ('2028-06-01 00:00:00+00')"
    ),
    (
        "CREATE TABLE public.notifications_default PARTITION OF public.notifications "
        "DEFAULT"
    ),
)

_ROW_LEVEL_SECURITY: tuple[str, ...] = (
    "ALTER TABLE ONLY public.chat_send_receipts FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.chats FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.events FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.groups FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.messages FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.news FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.notifications FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.schedule FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.stories FORCE ROW LEVEL SECURITY",
    "ALTER TABLE ONLY public.users FORCE ROW LEVEL SECURITY",
    "ALTER TABLE public.chat_send_receipts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.chats ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.events ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.groups ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.news ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.schedule ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.stories ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.users ENABLE ROW LEVEL SECURITY",
)

_POLICIES: tuple[str, ...] = (
    (
        "CREATE POLICY chat_send_receipts_owner_participant ON "
        "public.chat_send_receipts USING (((user_id = "
        "(NULLIF(current_setting('app.current_user_id'::text, true), "
        "''::text))::uuid) AND (EXISTS ( SELECT 1\n"
        "   FROM (public.chat_participants participant\n"
        "     JOIN public.chats chat ON ((chat.id = participant.chat_id)))\n"
        "  WHERE ((participant.chat_id = chat_send_receipts.chat_id) AND "
        "(participant.user_id = chat_send_receipts.user_id)))))) WITH CHECK "
        "(((user_id = (NULLIF(current_setting('app.current_user_id'::text, true), "
        "''::text))::uuid) AND (EXISTS ( SELECT 1\n"
        "   FROM (public.chat_participants participant\n"
        "     JOIN public.chats chat ON ((chat.id = participant.chat_id)))\n"
        "  WHERE ((participant.chat_id = chat_send_receipts.chat_id) AND "
        "(participant.user_id = chat_send_receipts.user_id))))))"
    ),
    (
        "CREATE POLICY messages_participant_isolation ON public.messages USING "
        "((chat_id IN ( SELECT chat_participants.chat_id\n"
        "   FROM public.chat_participants\n"
        "  WHERE (chat_participants.user_id = "
        "(NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.chats USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.events USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.groups USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.messages AS RESTRICTIVE "
        "USING ((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.news USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.notifications USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.schedule USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.stories USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
    (
        "CREATE POLICY tenant_isolation_policy ON public.users USING "
        "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
        "((tenant_id IS NOT NULL) AND (tenant_id = "
        "(NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid)))) WITH CHECK ((pg_has_role(CURRENT_USER, "
        "'ue_rls_bypass'::name, 'MEMBER'::text) OR ((tenant_id IS NOT NULL) AND "
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::uuid))))"
    ),
)

_TRIGGERS: tuple[str, ...] = (
    (
        "CREATE TRIGGER trg_notify_outbox_event AFTER INSERT ON public.stored_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.notify_outbox_event()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.chats FOR EACH "
        "ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.events FOR EACH "
        "ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.groups FOR EACH "
        "ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.messages FOR "
        "EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.news FOR EACH "
        "ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.notifications "
        "FOR EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.schedule FOR "
        "EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.stories FOR "
        "EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
    (
        "CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.users FOR EACH "
        "ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
    ),
)

# Token cleanup jobs. Scheduled only where the pg_cron extension is installed.
_PG_CRON_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pg_cron",
    (
        "SELECT cron.schedule('expire-password-reset-tokens', '0 * * * *', $$DELETE "
        "FROM password_reset_tokens WHERE expires_at < NOW() AND used IS FALSE$$)"
    ),
    (
        "SELECT cron.schedule('expire-mfa-challenges', '*/15 * * * *', $$UPDATE "
        "mfa_challenges SET state = 'expired' WHERE expires_at < NOW() AND state = "
        "'pending'$$)"
    ),
    (
        "SELECT cron.schedule('clean-trusted-devices', '0 3 1 * *', $$DELETE FROM "
        "trusted_devices WHERE expires_at < NOW()$$)"
    ),
)


def _execute(statements: tuple[str, ...]) -> None:
    for statement in statements:
        op.execute(statement)


def _schedule_pg_cron_jobs(bind: Any) -> None:
    """Schedule cleanup jobs only where pg_cron is installed, as the chain did."""
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron'")
    ).fetchone()
    if not available:
        return
    _execute(_PG_CRON_STATEMENTS)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("The MVP baseline requires PostgreSQL.")
    # Bounded waits before the first DDL statement, as the squashed chain's migrations
    # do; Squawk's require-lock-timeout and require-statement-timeout rules need them.
    _execute(_TRANSACTION_TIMEOUTS)
    _execute(_ROLES)
    _execute(_EXTENSIONS)
    _execute(_TYPES)
    _execute(_FUNCTIONS)
    _execute(_SEQUENCES)
    _execute(_TABLES)
    _execute(_DELIVERY_ONCE_TABLE)
    _execute(_SEQUENCE_DEFAULTS)
    _execute(_CONSTRAINTS)
    _execute(_DELIVERY_ONCE_CONSTRAINTS)
    _execute(_FOREIGN_KEYS)
    _execute(_INDEXES)
    _execute(_RESTORED_HOT_PATH_INDEXES)
    _execute(_PARTITIONS)
    _execute(_ROW_LEVEL_SECURITY)
    _execute(_POLICIES)
    _execute(_TRIGGERS)
    _schedule_pg_cron_jobs(bind)


def downgrade() -> None:
    raise RuntimeError(downgrade_reason)
