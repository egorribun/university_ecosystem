"""Owner-scoped read-only PostgreSQL evidence for the disabled NATS coordinator.

The collector binds effective Compose metadata and one captured PostgreSQL
container, then performs bounded fixed-SQL reads. The coordinator remains the
phase authority. Local Docker-child cleanup does not establish remote psql
termination, and this module is not connected to a runtime caller.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import NoReturn, TypeGuard, cast
from uuid import UUID

from scripts import owned_nats_docker as docker
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import (
    AdmissionEvidence,
    ChatParticipantRow,
    ChatRow,
    ChatRowsEvidence,
    CorrelationRows,
    OwnerEvidence,
    PgRoleRow,
    PrincipalEvidence,
    UserRow,
)
from scripts.owned_nats_docker import (
    ComposeConfigPins,
    ComposeMetadataStatus,
    CoordinatorMetadataPair,
    DaemonMetadataResult,
    DaemonMetadataStatus,
    DockerReadPins,
)
from scripts.owned_nats_outage import (
    ContainerSnapshot,
    Deadline,
    DeadlineVerdict,
    MessageEvidence,
    StoredEventState,
    StoredMessageEvent,
)
from scripts.owned_nats_owner_adapter import SignedOwnerLeasePort
from scripts.owned_nats_process import PrivateProcessRequest, PrivateProcessResult

_SQL_STDOUT_LIMIT = 262_144
_SQL_STDERR_LIMIT = 8_192
_SQL_OPERATION_CAP_SECONDS = 10.0
_SQL_STATEMENT_TIMEOUT_MS = 5_000
_SQL_LOCK_TIMEOUT_MS = 1_000
_MAX_COUNT = 2**63 - 1
_MAX_JSON_DEPTH = 16
_MAX_COMPOSE_JSON_DEPTH = 64
_MAX_MESSAGE_CONTENT = 32_768
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_UUID_VARIABLES = MappingProxyType(
    {
        "admission": (),
        "read_dm": ("chat_id",),
        "pending_count": (),
        "correlation": ("message_id",),
        "outbox_state": ("event_id",),
    }
)

_REQUIRED_COLUMNS = (
    ("users", "id", "pg_catalog", "uuid"),
    ("users", "email", "pg_catalog", "varchar"),
    ("users", "role", "public", "userrole"),
    ("users", "is_active", "pg_catalog", "bool"),
    ("users", "demo_seed_key", "pg_catalog", "varchar"),
    ("chats", "id", "pg_catalog", "uuid"),
    ("chats", "chat_type", "pg_catalog", "varchar"),
    ("chats", "demo_seed_key", "pg_catalog", "varchar"),
    ("chat_participants", "chat_id", "pg_catalog", "uuid"),
    ("chat_participants", "user_id", "pg_catalog", "uuid"),
    ("messages", "id", "pg_catalog", "uuid"),
    ("messages", "chat_id", "pg_catalog", "uuid"),
    ("messages", "sender_id", "pg_catalog", "uuid"),
    ("messages", "content", "pg_catalog", "varchar"),
    ("stored_events", "id", "pg_catalog", "uuid"),
    ("stored_events", "event_type", "pg_catalog", "varchar"),
    ("stored_events", "aggregate_type", "pg_catalog", "varchar"),
    ("stored_events", "aggregate_id", "pg_catalog", "varchar"),
    ("stored_events", "payload", "pg_catalog", "json"),
    ("stored_events", "processed_at", "pg_catalog", "timestamptz"),
    ("stored_events", "error_count", "pg_catalog", "int4"),
    ("failed_outbox_events", "original_event_id", "pg_catalog", "uuid"),
)
_SQL_HEADER = """BEGIN READ ONLY;
SET LOCAL search_path TO pg_catalog, pg_temp;
SET LOCAL statement_timeout = '5000ms';
SET LOCAL lock_timeout = '1000ms';
WITH
principal AS (
    SELECT session_user::text AS session_user,
           current_user::text AS current_user_name,
           role_row.rolname::text AS rolname,
           role_row.rolsuper AS rolsuper
    FROM pg_catalog.pg_roles AS role_row
    WHERE role_row.rolname = session_user
      AND session_user = 'postgres'
      AND current_user = 'postgres'
      AND role_row.rolsuper IS TRUE
      AND current_database() = 'university'
),
required_columns(table_name, column_name, type_schema, type_name) AS (
    VALUES
        ('users', 'id', 'pg_catalog', 'uuid'),
        ('users', 'email', 'pg_catalog', 'varchar'),
        ('users', 'role', 'public', 'userrole'),
        ('users', 'is_active', 'pg_catalog', 'bool'),
        ('users', 'demo_seed_key', 'pg_catalog', 'varchar'),
        ('chats', 'id', 'pg_catalog', 'uuid'),
        ('chats', 'chat_type', 'pg_catalog', 'varchar'),
        ('chats', 'demo_seed_key', 'pg_catalog', 'varchar'),
        ('chat_participants', 'chat_id', 'pg_catalog', 'uuid'),
        ('chat_participants', 'user_id', 'pg_catalog', 'uuid'),
        ('messages', 'id', 'pg_catalog', 'uuid'),
        ('messages', 'chat_id', 'pg_catalog', 'uuid'),
        ('messages', 'sender_id', 'pg_catalog', 'uuid'),
        ('messages', 'content', 'pg_catalog', 'varchar'),
        ('stored_events', 'id', 'pg_catalog', 'uuid'),
        ('stored_events', 'event_type', 'pg_catalog', 'varchar'),
        ('stored_events', 'aggregate_type', 'pg_catalog', 'varchar'),
        ('stored_events', 'aggregate_id', 'pg_catalog', 'varchar'),
        ('stored_events', 'payload', 'pg_catalog', 'json'),
        ('stored_events', 'processed_at', 'pg_catalog', 'timestamptz'),
        ('stored_events', 'error_count', 'pg_catalog', 'int4'),
        ('failed_outbox_events', 'original_event_id', 'pg_catalog', 'uuid')
),
catalog_shape AS (
    SELECT COUNT(*) = (SELECT COUNT(*) FROM required_columns) AS valid
    FROM required_columns AS expected
    JOIN pg_catalog.pg_class AS relation
      ON relation.relname = expected.table_name
     AND relation.relkind IN ('r', 'p')
     AND relation.relpersistence = 'p'
    JOIN pg_catalog.pg_namespace AS relation_schema
      ON relation_schema.oid = relation.relnamespace
     AND relation_schema.nspname = 'public'
    JOIN pg_catalog.pg_attribute AS column_row
      ON column_row.attrelid = relation.oid
     AND column_row.attname = expected.column_name
     AND column_row.attnum > 0
     AND column_row.attisdropped IS FALSE
    JOIN pg_catalog.pg_type AS column_type
      ON column_type.oid = column_row.atttypid
     AND column_type.typname = expected.type_name
    JOIN pg_catalog.pg_namespace AS type_schema
      ON type_schema.oid = column_type.typnamespace
     AND type_schema.nspname = expected.type_schema
),
admitted AS (
    SELECT 1
    FROM principal
    WHERE (SELECT valid FROM catalog_shape) IS TRUE
)
"""
_ADMISSION_BODY = """
, actor_users AS (
    SELECT user_row.id, user_row.email, user_row.role, user_row.is_active,
           user_row.demo_seed_key
    FROM public.users AS user_row
    WHERE user_row.email IN ('admin@university.dev', 'demo.peer@example.com')
       OR user_row.demo_seed_key = 'ue-demo-v1:user:primary-peer'
    ORDER BY user_row.id
    LIMIT 3
),
pair_chats AS (
    SELECT chat_row.id, chat_row.chat_type, chat_row.demo_seed_key
    FROM public.chats AS chat_row
    WHERE chat_row.chat_type = 'dm'
      AND EXISTS (
        SELECT 1
        FROM public.chat_participants AS member
        JOIN public.users AS actor ON actor.id = member.user_id
        WHERE member.chat_id = chat_row.id
          AND actor.email = 'admin@university.dev'
    )
      AND EXISTS (
        SELECT 1
        FROM public.chat_participants AS member
        JOIN public.users AS actor ON actor.id = member.user_id
        WHERE member.chat_id = chat_row.id
          AND actor.email = 'demo.peer@example.com'
    )
    ORDER BY chat_row.id
    LIMIT 1
),
chat_rows AS (
    SELECT COALESCE(
        json_agg(json_build_object(
            'id', chat_row.id::text,
            'chat_type', chat_row.chat_type,
            'demo_seed_key', chat_row.demo_seed_key
        ) ORDER BY chat_row.id),
        '[]'::json
    ) AS rows
    FROM pair_chats AS chat_row
),
participant_rows AS (
    SELECT COALESCE(
        json_agg(json_build_object(
            'chat_id', member.chat_id::text,
            'user_id', member.user_id::text
        ) ORDER BY member.chat_id, member.user_id),
        '[]'::json
    ) AS rows
    FROM pair_chats AS chat_row
    JOIN public.chat_participants AS member ON member.chat_id = chat_row.id
    JOIN public.users AS actor ON actor.id = member.user_id
    WHERE actor.email IN ('admin@university.dev', 'demo.peer@example.com')
)
SELECT json_build_object(
    'principal', (SELECT json_build_object(
        'session_user', session_user,
        'current_user', current_user_name,
        'rolname', rolname,
        'rolsuper', rolsuper
    ) FROM principal),
    'users', COALESCE((
        SELECT json_agg(json_build_object(
            'id', user_row.id::text,
            'email', user_row.email,
            'role', user_row.role::text,
            'is_active', user_row.is_active,
            'demo_seed_key', user_row.demo_seed_key
        ) ORDER BY user_row.id)
        FROM actor_users AS user_row
    ), '[]'::json),
    'chats', (SELECT rows FROM chat_rows),
    'participants', (SELECT rows FROM participant_rows)
)::text
FROM admitted;
"""

_READ_DM_BODY = """
, chat_rows AS (
    SELECT chat_row.id, chat_row.chat_type, chat_row.demo_seed_key
    FROM public.chats AS chat_row
    WHERE chat_row.id = :'chat_id'::uuid
    ORDER BY chat_row.id
    LIMIT 2
),
participant_rows AS (
    SELECT member.chat_id, member.user_id
    FROM public.chat_participants AS member
    WHERE member.chat_id = :'chat_id'::uuid
    ORDER BY member.user_id
    LIMIT 3
),
participant_count AS (
    SELECT COUNT(*) > 2 AS overflow
    FROM public.chat_participants
    WHERE chat_id = :'chat_id'::uuid
)
SELECT json_build_object(
    'chat_rows', COALESCE((
        SELECT json_agg(json_build_object(
            'id', chat_row.id::text,
            'chat_type', chat_row.chat_type,
            'demo_seed_key', chat_row.demo_seed_key
        ) ORDER BY chat_row.id)
        FROM chat_rows AS chat_row
    ), '[]'::json),
    'participants', COALESCE((
        SELECT json_agg(json_build_object(
            'chat_id', member.chat_id::text,
            'user_id', member.user_id::text
        ) ORDER BY member.user_id)
        FROM participant_rows AS member
    ), '[]'::json),
    'participant_overflow', (SELECT overflow FROM participant_count)
)::text
FROM admitted;
"""

_PENDING_BODY = """
SELECT json_build_object(
    'count', (
        SELECT COUNT(*)::bigint
        FROM public.stored_events
        WHERE processed_at IS NULL
    )
)::text
FROM admitted;
"""

_CORRELATION_BODY = """
, message_rows AS (
    SELECT json_build_object(
        'message_id', message_row.id::text,
        'chat_id', message_row.chat_id::text,
        'sender_id', message_row.sender_id::text,
        'content', message_row.content
    ) AS row
    FROM public.messages AS message_row
    WHERE message_row.id = :'message_id'::uuid
    ORDER BY message_row.id
    LIMIT 2
),
event_rows AS (
    SELECT event_row.id, event_row.event_type, event_row.aggregate_type,
           event_row.aggregate_id, event_row.payload
    FROM public.stored_events AS event_row
    WHERE event_row.aggregate_id = :'message_id'
       OR event_row.payload->>'message_id' = :'message_id'
    ORDER BY event_row.id
    LIMIT 2
),
event_json AS (
    SELECT COALESCE(
        json_agg(json_build_object(
            'event_id', event_row.id::text,
            'event_type', event_row.event_type,
            'aggregate_type', event_row.aggregate_type,
            'aggregate_id', event_row.aggregate_id,
            'payload', json_build_object(
                '_schema_version', event_row.payload->'_schema_version',
                'message_id', event_row.payload->>'message_id',
                'chat_id', event_row.payload->>'chat_id',
                'sender_id', event_row.payload->>'sender_id',
                'content_preview', event_row.payload->>'content_preview'
            )
        ) ORDER BY event_row.id),
        '[]'::json
    ) AS rows
    FROM event_rows AS event_row
)
SELECT json_build_object(
    'database_message', (SELECT row FROM message_rows),
    'stored_events', (SELECT rows FROM event_json)
)::text
FROM admitted;
"""

_OUTBOX_STATE_BODY = """
, event_rows AS (
    SELECT event_row.id, event_row.processed_at IS NOT NULL AS processed,
           event_row.error_count
    FROM public.stored_events AS event_row
    WHERE event_row.id = :'event_id'::uuid
    ORDER BY event_row.id
    LIMIT 2
),
dead_letter_count AS (
    SELECT COUNT(*)::bigint AS count
    FROM public.failed_outbox_events AS failed_row
    WHERE failed_row.original_event_id = :'event_id'::uuid
)
SELECT json_build_object(
    'states', COALESCE((
        SELECT json_agg(json_build_object(
            'stored_event_id', event_row.id::text,
            'processed_at_present', event_row.processed,
            'error_count', event_row.error_count
        ) ORDER BY event_row.id)
        FROM event_rows AS event_row
    ), '[]'::json),
    'dlq_count', (SELECT count FROM dead_letter_count)
)::text
FROM admitted;
"""

SQL_STATEMENTS = MappingProxyType(
    {
        "admission": (_SQL_HEADER + _ADMISSION_BODY + "\nROLLBACK;\n").encode(),
        "read_dm": (_SQL_HEADER + _READ_DM_BODY + "\nROLLBACK;\n").encode(),
        "pending_count": (_SQL_HEADER + _PENDING_BODY + "\nROLLBACK;\n").encode(),
        "correlation": (_SQL_HEADER + _CORRELATION_BODY + "\nROLLBACK;\n").encode(),
        "outbox_state": (_SQL_HEADER + _OUTBOX_STATE_BODY + "\nROLLBACK;\n").encode(),
    }
)


class SqlReadNotReady(RuntimeError):
    """Closed non-sensitive failure for an owner-scoped SQL observation."""

    def __init__(self) -> None:
        super().__init__("owner-scoped SQL read is not ready")


def _deadline_live(deadline: object) -> bool:
    if type(deadline) is not Deadline:
        return False
    try:
        budget = deadline.timeout_for(_SQL_OPERATION_CAP_SECONDS)
    except Exception:
        return False
    return (
        budget.verdict is DeadlineVerdict.VALID
        and type(budget.seconds) in (int, float)
        and budget.seconds is not None
        and budget.seconds > 0
    )


def _canonical_uuid(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.int != 0 and str(parsed) == value


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate SQL evidence key")
        result[key] = value
    return result


def _json_constant(_value: str) -> None:
    raise ValueError("non-finite SQL evidence")


def _depth_within_limit(value: object, *, limit: int = _MAX_JSON_DEPTH) -> bool:
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if type(current) is dict or type(current) is list:
            if depth > limit:
                return False
            children = current.values() if type(current) is dict else current
            pending.extend((child, depth + 1) for child in children)
    return True


def _decode_json(raw: object, *, deadline: Deadline) -> object | None:
    if type(raw) is not bytes or not raw or len(raw) > _SQL_STDOUT_LIMIT:
        return None
    if not _deadline_live(deadline):
        return None
    try:
        value = cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_json_object,
                parse_constant=_json_constant,
            ),
        )
    except (UnicodeError, ValueError, RecursionError):
        return None
    if not _depth_within_limit(value) or not _deadline_live(deadline):
        return None
    return value


def _mapping(value: object, keys: set[str]) -> TypeGuard[dict[str, object]]:
    return type(value) is dict and set(value) == keys


def _bounded_text(value: object, limit: int) -> bool:
    return type(value) is str and len(value) <= limit and value.isprintable()


def _effective_postgres_settings(raw: object) -> tuple[str, str] | None:
    """Read only the two effective, non-secret settings needed by this adapter."""
    if type(raw) is not bytes or not raw or len(raw) > 1_048_576:
        return None
    try:
        project = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_json_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        return None
    if type(project) is not dict or not _depth_within_limit(
        project, limit=_MAX_COMPOSE_JSON_DEPTH
    ):
        return None
    services = project.get("services")
    postgres = services.get("postgres") if type(services) is dict else None
    environment = postgres.get("environment") if type(postgres) is dict else None
    if type(environment) is not dict:
        return None
    user = environment.get("POSTGRES_USER")
    database = environment.get("POSTGRES_DB")
    if user != "postgres" or database != "university":
        return None
    return user, database


def prepare_psql_request(
    pins: DockerReadPins,
    postgres: ContainerSnapshot,
    operation: str,
    variables: Mapping[str, str],
    *,
    deadline: Deadline,
) -> PrivateProcessRequest | None:
    """Prepare one fixed stdin query to an exact already-captured container ID."""
    if (
        type(pins) is not DockerReadPins
        or type(postgres) is not ContainerSnapshot
        or type(operation) is not str
        or operation not in SQL_STATEMENTS
        or type(variables) is not dict
        or not _deadline_live(deadline)
    ):
        return None
    try:
        base = docker.prepare_daemon_read(pins, deadline=deadline)
        container_id = postgres.container_id
        expected_variables = _UUID_VARIABLES[operation]
        if (
            base is None
            or type(container_id) is not str
            or _CONTAINER_ID.fullmatch(container_id) is None
            or postgres.service != "postgres"
            or postgres.running is not True
            or postgres.status != "running"
            or postgres.health != "healthy"
            or type(variables) is not dict
            or set(variables) != set(expected_variables)
        ):
            return None
        arguments = [
            *base.argv[:5],
            "exec",
            "--interactive",
            container_id,
            "psql",
            "-X",
            "--no-password",
            "--quiet",
            "--no-align",
            "--tuples-only",
            "-U",
            "postgres",
            "-d",
            "university",
            "--set=ON_ERROR_STOP=1",
        ]
        for name in expected_variables:
            value = variables[name]
            if not _canonical_uuid(value):
                return None
            arguments.append(f"--set={name}={value}")
        request = PrivateProcessRequest(
            argv=tuple(arguments),
            cwd=base.cwd,
            env=dict(base.env),
            stdin=SQL_STATEMENTS[operation],
            stdout_limit=_SQL_STDOUT_LIMIT,
            stderr_limit=_SQL_STDERR_LIMIT,
            input_limit=len(SQL_STATEMENTS[operation]),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return request if _deadline_live(deadline) else None


def _user_row(value: object) -> UserRow | None:
    if not _mapping(value, {"id", "email", "role", "is_active", "demo_seed_key"}):
        return None
    user_id = value["id"]
    email = value["email"]
    role = value["role"]
    active = value["is_active"]
    seed_key = value["demo_seed_key"]
    if (
        not _canonical_uuid(user_id)
        or not _bounded_text(email, 254)
        or not _bounded_text(role, 64)
        or type(active) is not bool
        or (seed_key is not None and not _bounded_text(seed_key, 96))
    ):
        return None
    return UserRow(user_id, email, role, active, seed_key)


def _chat_row(value: object) -> ChatRow | None:
    if not _mapping(value, {"id", "chat_type", "demo_seed_key"}):
        return None
    chat_id = value["id"]
    chat_type = value["chat_type"]
    seed_key = value["demo_seed_key"]
    if (
        not _canonical_uuid(chat_id)
        or not _bounded_text(chat_type, 20)
        or (seed_key is not None and not _bounded_text(seed_key, 96))
    ):
        return None
    return ChatRow(chat_id, chat_type, seed_key)


def _participant_row(value: object) -> ChatParticipantRow | None:
    if not _mapping(value, {"chat_id", "user_id"}):
        return None
    chat_id = value["chat_id"]
    user_id = value["user_id"]
    if not _canonical_uuid(chat_id) or not _canonical_uuid(user_id):
        return None
    return ChatParticipantRow(chat_id, user_id)


def decode_admission(raw: bytes, *, deadline: Deadline) -> AdmissionEvidence | None:
    value = _decode_json(raw, deadline=deadline)
    if not _mapping(value, {"principal", "users", "chats", "participants"}):
        return None
    principal = value["principal"]
    if not _mapping(principal, {"session_user", "current_user", "rolname", "rolsuper"}):
        return None
    session_user = principal["session_user"]
    current_user = principal["current_user"]
    role_name = principal["rolname"]
    superuser = principal["rolsuper"]
    if (
        session_user != "postgres"
        or current_user != "postgres"
        or role_name != "postgres"
        or superuser is not True
    ):
        return None

    raw_users = value["users"]
    raw_chats = value["chats"]
    raw_participants = value["participants"]
    if (
        type(raw_users) is not list
        or len(raw_users) > 3
        or type(raw_chats) is not list
        or len(raw_chats) > 2
        or type(raw_participants) is not list
        or len(raw_participants) > 4
    ):
        return None
    users = tuple(_user_row(row) for row in raw_users)
    chats = tuple(_chat_row(row) for row in raw_chats)
    participants = tuple(_participant_row(row) for row in raw_participants)
    if (
        any(row is None for row in users)
        or any(row is None for row in chats)
        or any(row is None for row in participants)
        or not _deadline_live(deadline)
    ):
        return None
    return AdmissionEvidence(
        PrincipalEvidence(
            session_user,
            current_user,
            PgRoleRow(role_name, superuser),
        ),
        users,  # type: ignore[arg-type]
        chats,  # type: ignore[arg-type]
        participants,  # type: ignore[arg-type]
    )


def decode_read_dm(raw: bytes, *, deadline: Deadline) -> ChatRowsEvidence | None:
    value = _decode_json(raw, deadline=deadline)
    if not _mapping(value, {"chat_rows", "participants", "participant_overflow"}):
        return None
    raw_chats = value["chat_rows"]
    raw_participants = value["participants"]
    overflow = value["participant_overflow"]
    if (
        type(raw_chats) is not list
        or len(raw_chats) > 2
        or type(raw_participants) is not list
        or len(raw_participants) > 3
        or type(overflow) is not bool
        or overflow != (len(raw_participants) == 3)
    ):
        return None
    chats = tuple(_chat_row(row) for row in raw_chats)
    participants = tuple(_participant_row(row) for row in raw_participants)
    if (
        any(row is None for row in chats)
        or any(row is None for row in participants)
        or len(chats) > 1
        or not _deadline_live(deadline)
    ):
        return None
    return ChatRowsEvidence(
        chats[0] if chats else None,
        participants,  # type: ignore[arg-type]
    )


def decode_pending_count(raw: bytes, *, deadline: Deadline) -> int | None:
    value = _decode_json(raw, deadline=deadline)
    if not _mapping(value, {"count"}):
        return None
    count = value["count"]
    if type(count) is not int or not 0 <= count <= _MAX_COUNT:
        return None
    return count if _deadline_live(deadline) else None


def _message_evidence(value: object) -> MessageEvidence | None:
    if not _mapping(value, {"message_id", "chat_id", "sender_id", "content"}):
        return None
    message_id = value["message_id"]
    chat_id = value["chat_id"]
    sender_id = value["sender_id"]
    content = value["content"]
    if (
        not _canonical_uuid(message_id)
        or not _canonical_uuid(chat_id)
        or not _canonical_uuid(sender_id)
        or type(content) is not str
        or len(content) > _MAX_MESSAGE_CONTENT
    ):
        return None
    return MessageEvidence(message_id, chat_id, sender_id, content)


def _stored_message_event(value: object) -> StoredMessageEvent | None:
    if not _mapping(
        value,
        {"event_id", "event_type", "aggregate_type", "aggregate_id", "payload"},
    ):
        return None
    event_id = value["event_id"]
    event_type = value["event_type"]
    aggregate_type = value["aggregate_type"]
    aggregate_id = value["aggregate_id"]
    payload = value["payload"]
    if (
        not _canonical_uuid(event_id)
        or not _bounded_text(event_type, 100)
        or not _bounded_text(aggregate_type, 128)
        or not _bounded_text(aggregate_id, 100)
        or not _mapping(
            payload,
            {
                "_schema_version",
                "message_id",
                "chat_id",
                "sender_id",
                "content_preview",
            },
        )
        or (
            payload["_schema_version"] is not None
            and type(payload["_schema_version"]) is not int
        )
        or any(
            item is not None and not _bounded_text(item, 100)
            for item in (
                payload["message_id"],
                payload["chat_id"],
                payload["sender_id"],
            )
        )
        or (
            payload["content_preview"] is not None
            and (
                type(payload["content_preview"]) is not str
                or len(payload["content_preview"]) > 50
            )
        )
    ):
        return None
    return StoredMessageEvent(
        event_id,
        event_type,
        aggregate_type,
        aggregate_id,
        MappingProxyType(dict(payload)),
    )


def decode_correlation(raw: bytes, *, deadline: Deadline) -> CorrelationRows | None:
    value = _decode_json(raw, deadline=deadline)
    if not _mapping(value, {"database_message", "stored_events"}):
        return None
    raw_message = value["database_message"]
    message = None if raw_message is None else _message_evidence(raw_message)
    raw_events = value["stored_events"]
    if message is None and raw_message is not None:
        return None
    if type(raw_events) is not list or len(raw_events) > 2:
        return None
    events = tuple(_stored_message_event(row) for row in raw_events)
    if any(event is None for event in events) or not _deadline_live(deadline):
        return None
    return CorrelationRows(message, events)  # type: ignore[arg-type]


def decode_outbox_state(
    raw: bytes,
    *,
    expected_event_id: str,
    deadline: Deadline,
) -> StoredEventState | None:
    if not _canonical_uuid(expected_event_id):
        return None
    value = _decode_json(raw, deadline=deadline)
    if not _mapping(value, {"states", "dlq_count"}):
        return None
    raw_states = value["states"]
    dlq_count = value["dlq_count"]
    if (
        type(raw_states) is not list
        or len(raw_states) > 2
        or type(dlq_count) is not int
        or not 0 <= dlq_count <= _MAX_COUNT
        or len(raw_states) != 1
    ):
        return None
    state = raw_states[0]
    if not _mapping(state, {"stored_event_id", "processed_at_present", "error_count"}):
        return None
    event_id = state["stored_event_id"]
    processed = state["processed_at_present"]
    error_count = state["error_count"]
    if (
        not _canonical_uuid(event_id)
        or event_id != expected_event_id
        or type(processed) is not bool
        or type(error_count) is not int
        or not 0 <= error_count <= _MAX_COUNT
        or not _deadline_live(deadline)
    ):
        return None
    return StoredEventState(event_id, processed, error_count, dlq_count)


class OwnedNatsSqlAdapter:
    """Preparatory adapter for exact read-only SQL observations under one lease."""

    __slots__ = (
        "_closed",
        "_compose_evidence",
        "_compose_pins",
        "_docker_pins",
        "_metadata",
        "_owner",
        "_owner_port",
        "_postgres",
    )

    def __init__(
        self,
        owner_port: SignedOwnerLeasePort,
        docker_pins: DockerReadPins,
        compose_pins: ComposeConfigPins,
    ) -> None:
        if (
            type(owner_port) is not SignedOwnerLeasePort
            or type(docker_pins) is not DockerReadPins
            or type(compose_pins) is not ComposeConfigPins
        ):
            raise ValueError("invalid owner-scoped SQL adapter pins")
        try:
            self._owner_port = owner_port
            self._docker_pins = replace(docker_pins)
            self._compose_pins = replace(compose_pins)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid owner-scoped SQL adapter pins") from None
        self._owner: OwnerEvidence | None = None
        self._metadata: CoordinatorMetadataPair | None = None
        self._compose_evidence: object | None = None
        self._postgres: ContainerSnapshot | None = None
        self._closed = False

    def __repr__(self) -> str:
        return "<OwnedNatsSqlAdapter>"

    def _raise_not_ready(self) -> NoReturn:
        self._closed = True
        raise SqlReadNotReady() from None

    def _observe_daemon(self, deadline: Deadline) -> DaemonMetadataResult:
        if self._owner is None:
            self._raise_not_ready()
        try:
            result = docker.observe_daemon_metadata(
                self._docker_pins, deadline=deadline
            )
            if (
                type(result) is not DaemonMetadataResult
                or result.status is not DaemonMetadataStatus.MATCHED_METADATA
                or result.fingerprint != self._owner.daemon_fingerprint
                or not _deadline_live(deadline)
            ):
                self._raise_not_ready()
            return result
        except SqlReadNotReady:
            raise
        except Exception:
            self._raise_not_ready()
        raise AssertionError("unreachable")

    def _observe_owner(self, deadline: Deadline) -> OwnerEvidence:
        if self._owner is None:
            self._raise_not_ready()
        try:
            current = self._owner_port.read_signed_owner(deadline=deadline)
            validated = docker._compose_owner(current)
            if (
                validated is None
                or validated != self._owner
                or not _deadline_live(deadline)
            ):
                self._raise_not_ready()
            return validated
        except SqlReadNotReady:
            raise
        except Exception:
            self._raise_not_ready()
        raise AssertionError("unreachable")

    def _capture_compose(self, deadline: Deadline) -> None:
        owner = self._owner
        if owner is None:
            self._raise_not_ready()
        self._observe_daemon(deadline)
        try:
            request = docker.prepare_compose_config(
                owner,
                self._docker_pins,
                self._compose_pins,
                deadline=deadline,
            )
            if request is None or not _deadline_live(deadline):
                self._raise_not_ready()
            result = process.run_private_process(request, deadline=deadline)
            raw = docker._compose_stdout(result)
            settings = _effective_postgres_settings(raw)
            if settings != ("postgres", "university") or not _deadline_live(deadline):
                self._raise_not_ready()
            compose = docker.decode_compose_config(
                result, owner=owner, deadline=deadline
            )
            daemon = self._observe_daemon(deadline)
            metadata = docker.compose_coordinator_metadata(owner, daemon, compose)
            if (
                type(compose) is not docker.ComposeMetadataResult
                or compose.status is not ComposeMetadataStatus.MATCHED_METADATA
                or metadata is None
                or type(compose.evidence)
                is not docker.live_stand.ComposeResourceEvidence
                or not _deadline_live(deadline)
            ):
                self._raise_not_ready()
            self._metadata = metadata
            self._compose_evidence = replace(compose.evidence)
        except SqlReadNotReady:
            raise
        except Exception:
            self._raise_not_ready()

    def _inspect_postgres(self, deadline: Deadline) -> ContainerSnapshot:
        metadata = self._metadata
        evidence = self._compose_evidence
        postgres = self._postgres
        if (
            metadata is None
            or type(evidence) is not docker.live_stand.ComposeResourceEvidence
            or postgres is None
        ):
            self._raise_not_ready()
        try:
            requests = docker.prepare_container_inspect_reads(
                metadata,
                self._docker_pins,
                (postgres.container_id,),
                deadline=deadline,
            )
            if type(requests) is not tuple or len(requests) != 1:
                self._raise_not_ready()
            self._observe_daemon(deadline)
            result = process.run_private_process(requests[0], deadline=deadline)
            self._observe_daemon(deadline)
            snapshots = docker.decode_container_inspect_reads(
                metadata,
                evidence,
                (postgres.container_id,),
                (result,),
                deadline=deadline,
            )
            if (
                type(snapshots) is not tuple
                or len(snapshots) != 1
                or type(snapshots[0]) is not ContainerSnapshot
                or snapshots[0] != postgres
                or not _deadline_live(deadline)
            ):
                self._raise_not_ready()
            return snapshots[0]
        except SqlReadNotReady:
            raise
        except Exception:
            self._raise_not_ready()
        raise AssertionError("unreachable")

    def _bind_or_check(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        deadline: Deadline,
    ) -> None:
        if self._closed:
            raise SqlReadNotReady() from None
        if type(owner) is not OwnerEvidence or type(postgres) is not ContainerSnapshot:
            self._raise_not_ready()
        if self._owner is None:
            admitted = docker._compose_owner(owner)
            if admitted is None or admitted != owner:
                self._raise_not_ready()
            # Retain the first caller-supplied, signed-owner expectation before
            # external reads. A failed first admission permanently closes this
            # adapter; later calls cannot bind a replacement owner or target.
            self._owner = admitted
            self._postgres = replace(postgres)
        elif owner != self._owner or postgres != self._postgres:
            self._raise_not_ready()
        try:
            self._observe_owner(deadline)
            if self._metadata is None:
                self._capture_compose(deadline)
                current = self._inspect_postgres(deadline)
                if current != self._postgres:
                    self._raise_not_ready()
            else:
                current = self._inspect_postgres(deadline)
                if current != self._postgres:
                    self._raise_not_ready()
        except SqlReadNotReady:
            self._closed = True
            raise
        except Exception:
            self._raise_not_ready()

    def _read[T](
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        operation: str,
        variables: Mapping[str, str],
        deadline: Deadline,
        decoder: Callable[..., T | None],
    ) -> T:
        if not _deadline_live(deadline):
            self._raise_not_ready()
        operation_deadline = deadline.child(_SQL_OPERATION_CAP_SECONDS)
        if not _deadline_live(operation_deadline):
            self._raise_not_ready()
        try:
            self._bind_or_check(owner, postgres, operation_deadline)
            captured = self._postgres
            metadata = self._metadata
            if captured is None or metadata is None:
                self._raise_not_ready()
            request = prepare_psql_request(
                self._docker_pins,
                captured,
                operation,
                variables,
                deadline=operation_deadline,
            )
            if request is None:
                self._raise_not_ready()
            self._observe_owner(operation_deadline)
            result = process.run_private_process(request, deadline=operation_deadline)
            if (
                type(result) is not PrivateProcessResult
                or result.outcome is not process.ProcessOutcome.EXITED
                or type(result.returncode) is not int
                or result.returncode != 0
                or result.local_cleanup is not process.LocalCleanup.CONFIRMED
                or type(result.stdout) is not bytes
                or len(result.stdout) > _SQL_STDOUT_LIMIT
                or type(result.stderr) is not bytes
                or len(result.stderr) > _SQL_STDERR_LIMIT
                or result.stderr != b""
                or not _deadline_live(operation_deadline)
            ):
                self._raise_not_ready()
            self._inspect_postgres(operation_deadline)
            self._observe_owner(operation_deadline)
            evidence = decoder(result.stdout, deadline=operation_deadline)
            if evidence is None or not _deadline_live(operation_deadline):
                self._raise_not_ready()
            return evidence
        except SqlReadNotReady:
            self._closed = True
            raise
        except Exception:
            self._raise_not_ready()
        raise AssertionError("unreachable")

    def read_admission(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> AdmissionEvidence:
        return self._read(owner, postgres, "admission", {}, deadline, decode_admission)

    def read_dm(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        chat_id: str,
        *,
        deadline: Deadline,
    ) -> ChatRowsEvidence:
        return self._read(
            owner,
            postgres,
            "read_dm",
            {"chat_id": chat_id},
            deadline,
            decode_read_dm,
        )

    def pending_count(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> int:
        return self._read(
            owner, postgres, "pending_count", {}, deadline, decode_pending_count
        )

    def read_correlation(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        message_id: str,
        *,
        deadline: Deadline,
    ) -> CorrelationRows:
        return self._read(
            owner,
            postgres,
            "correlation",
            {"message_id": message_id},
            deadline,
            decode_correlation,
        )

    def outbox_state(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        stored_event_id: str,
        *,
        deadline: Deadline,
    ) -> StoredEventState | None:
        return self._read(
            owner,
            postgres,
            "outbox_state",
            {"event_id": stored_event_id},
            deadline,
            lambda raw, *, deadline: decode_outbox_state(
                raw,
                expected_event_id=stored_event_id,
                deadline=deadline,
            ),
        )
