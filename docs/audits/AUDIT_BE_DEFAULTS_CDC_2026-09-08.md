# Backend defaults and CDC worker audit

Date: 2026-09-08 (Europe/Moscow)  
Repository: `egorribun/university_ecosystem`  
Audited source: `e94da6d32` (`git rev-parse HEAD` at audit time)  
Finding scope: BE-02, BE-03 and BE-08 from the independent platform audit

This is a deterministic, read-only architecture audit. It is not a release
certificate and it does not replace fresh PostgreSQL, CI, mutation or staging
evidence. The user-owned `docs/audits/AUDIT_PLATFORM_FULL.md` remains
untracked and was not modified.

## Method and reproducibility

The effective model inventory was collected after importing the canonical
`app.models` package, so inherited SQLAlchemy columns and server/computed
defaults are included (a source-only grep would miss inherited `id` columns).

```text
uv run python - <<'PY'
from app.core.database import Base
import app.models

all_rows = []
for table in Base.metadata.tables.values():
    for column in table.columns:
        if column.default is not None or column.server_default is not None:
            all_rows.append(column)

both = [c for c in all_rows if c.default is not None and c.server_default is not None]
python_only = [c for c in all_rows if c.default is not None and c.server_default is None]
server_only = [c for c in all_rows if c.default is None and c.server_default is not None]
print(len(Base.metadata.tables), len(all_rows), len(both), len(python_only), len(server_only))
PY
```

The output at the audited source was:

```text
45 tables, 135 effective defaulted columns, 15 BOTH, 91 PYTHON_ONLY, 29 SERVER_ONLY
```

The `PYTHON_ONLY` total includes the UUID7 primary-key default inherited from
`UUID7PrimaryKeyMixin` on the mapped entities. The exact number of explicit
`mapped_column(...)` declarations with one-sided defaults is 93 in the source
tree; the remaining inherited identity declarations are listed separately
below. `default=None` on nullable optional fields is not an effective
SQLAlchemy `ColumnDefault` and is intentionally not counted by the runtime
inventory.

## BE-02 — dual-default inventory

The backend standard requires a Python-side default and a DDL
`server_default` for a persisted default. The following table is the complete
effective source-level inventory of explicit one-sided declarations. It omits
source spellings of `default=None` that SQLAlchemy does not materialize as a
`ColumnDefault`, and the generated `events.search_vector` expression; both are
called out below. `field@line` points to the `mapped_column` declaration in the
named model file. The table is an inventory, not permission to apply a
mechanical rewrite.

| Source | Model | Python-only declarations | Server-only declarations | Both (control set) |
|---|---|---|---|---|
| `app/models/auth.py` | `ActiveSession` | `signing_key@83`, `mfa_required@86` | `created_at@64` | `mfa_epoch@96` |
| `app/models/auth.py` | `MfaTotpEnrollment` | `is_active@121` | `created_at@130` | - |
| `app/models/auth.py` | `MfaChallenge` | - | `created_at@188` | `revision@166`, `trust_device_requested@169`, `attempt_count@192`, `state@199` |
| `app/models/auth.py` | `FailedLoginAttempt` | - | `attempted_at@272` | - |
| `app/models/auth.py` | `PasswordResetToken` | `used@310` | `created_at@313` | - |
| `app/models/auth.py` | `EmailChangeToken` | `used@337` | `created_at@340` | - |
| `app/models/auth.py` | `TrustedDevice` | - | `created_at@379` | `mfa_epoch@376` |
| `app/models/auth.py` | `MfaEmailDelivery` | - | - | `status@410`, `attempt_count@413`, `created_at@420` |
| `app/models/auth.py` | `RecoveryCode` | `is_used@470` | `created_at@473` | - |
| `app/models/auth.py` | `LoginHistory` | `is_suspicious@506` | `created_at@500` | - |
| `app/models/chat.py` | `Chat` | `created_at@51`, `updated_at@54` | - | `chat_type@77` |
| `app/models/chat.py` | `Message` | `created_at@135`, `read_status@138` | - | - |
| `app/models/chat.py` | `Attachment` | `created_at@284` | - | - |
| `app/models/chat.py` | `MessageReaction` | `created_at@326` | - | - |
| `app/models/cwv.py` | `CwvObservation` | - | - | `created_at@49` |
| `app/models/dead_letter.py` | `DeadLetterJob` | `retry_count@41`, `max_retries@42`, `status@43`, `created_at@49`, `updated_at@52` | - | - |
| `app/models/domain_events.py` | `StoredEvent` | `version@27`, `status@35`, `created_at@40`, `error_count@46` | - | - |
| `app/models/events.py` | `Event` | `is_active@78` | `created_at@75` | - |
| `app/models/events.py` | `EventAttendance` | - | `registered_at@135` | - |
| `app/models/failed_outbox_events.py` | `FailedOutboxEvent` | `retry_count@35`, `failed_at@36` | - | - |
| `app/models/grade.py` | `Grade` | `assessment_type@27`, `created_at@36`, `updated_at@39` | - | - |
| `app/models/logs.py` | `DataAccessLog` | - | `created_at@42` | - |
| `app/models/news.py` | `News` | - | `created_at@47` | - |
| `app/models/news.py` | `NewsLike` | - | `created_at@96` | - |
| `app/models/news.py` | `NewsComment` | - | `created_at@120` | - |
| `app/models/notifications.py` | `Notification` | `read@43` | `created_at@47` | - |
| `app/models/notifications.py` | `NotificationQueueJob` | - | `enqueued_at@90`, `attempts@98`, `dead_lettered@105` | - |
| `app/models/notifications.py` | `NotificationDelivery` | `channel@152`, `status@165` | `attempted_at@171` | - |
| `app/models/notifications.py` | `PushSubscription` | `topics@242` | `created_at@232` | - |
| `app/models/notifications.py` | `UserPushTopic` | `topics@266` | `updated_at@267` | - |
| `app/models/schedule.py` | `Schedule` | `parity@70` | - | - |
| `app/models/spotify.py` | `SpotifyIntegration` | `is_connected@33`, `is_playing@34` | - | - |
| `app/models/tenant.py` | `Tenant` | - | `is_active@24`, `created_at@27` | - |
| `app/models/users.py` | `User` | `role@50`, `is_active@67`, `mfa_required@68` | `created_at@78` | `mfa_epoch@75` |
| `app/models/users.py` | `UserPreferences` | `dnd_enabled@323` | - | - |
| `app/models/users.py` | `InviteCode` | `is_active@392`, `is_used@393` | `created_at@394` | - |
| `app/models/users.py` | `UserStats` | `attendance_percent@429`, `attendance_present@430`, `attendance_total@431`, `attendance_trend@432`, `grades_average@435`, `grades_trend@436`, `participation_events@439`, `participation_hours@440`, `participation_groups@441`, `participation_trend@442` | `last_computed_at@445` | - |
| `app/models/vector_shard.py` | `VectorChunk` | `chunk_index@37`, `is_active@41` | `created_at@42` | - |

### Inherited identity declarations

`UUID7PrimaryKeyMixin.id` is declared once at
`app/models/mixins.py:15` with the application-side `generate_uuid7`
callable. It is inherited by these 37 mapped entities and therefore appears
as a Python-only effective default in the runtime inventory:

```text
active_sessions, attachments, chat_read_receipts, chats, cwv_observations,
data_access_logs, email_change_tokens, event_attendance, event_files, events,
failed_login_attempts, failed_outbox_events, grades, groups, invite_codes,
login_history, message_reactions, messages, mfa_challenges,
mfa_email_deliveries, mfa_totp_enrollments, news, news_comments, news_likes,
notification_deliveries, notification_queue_jobs, notifications,
password_reset_tokens, push_subscriptions, recovery_codes, schedule,
stored_events, stories, tenants, trusted_devices, users, vector_chunks
```

Adding a generic PostgreSQL UUID server default here would not be equivalent:
the application contract is UUIDv7 (time ordered), while PostgreSQL clusters
may only provide UUIDv4 or an extension-specific implementation. This is an
identity-generation decision, not a safe default backfill; it remains an
explicit architecture item.

### Effective control set

The 15 declarations already satisfying both sides are:

```text
active_sessions.mfa_epoch
chats.chat_type
cwv_observations.created_at
mfa_challenges.revision
mfa_challenges.trust_device_requested
mfa_challenges.attempt_count
mfa_challenges.state
mfa_email_deliveries.status
mfa_email_deliveries.attempt_count
mfa_email_deliveries.created_at
stories.published_at
stories.is_active
stories.created_at
trusted_devices.mfa_epoch
users.mfa_epoch
```

The `events.search_vector` generated column is a server-side `Computed`
expression, not a user-supplied default. It must not be assigned a Python
default or included in a default-backfill migration. Nullable optional fields
whose source declaration says `default=None` (`Chat.name` and `created_by`,
message tombstone/reply/forward fields, and `Schedule.lesson_type`) are not
effective defaults and likewise require no `DEFAULT NULL` DDL churn.

## BE-02 disposition and safe follow-up

Status: **BACKLOG / P2-P1 ARCHITECTURE**, with the required deterministic
inventory now recorded. A 92-column count from the external report is stale
relative to this source: it did not account for the current inherited identity
surface and runtime metadata. No mass rewrite was made because the one-sided
entries have materially different semantics:

| Category | Safe treatment | Required evidence before changing code |
|---|---|---|
| Non-null scalar flags/counters/enums (`is_active`, `read`, retry counters, statuses) | Add a matching SQL literal only in a dedicated phased migration; add a Python default if the server is authoritative. | PostgreSQL inventory of existing NULLs, backfill/check-constraint plan, upgrade/downgrade and ORM/Pydantic serialization tests. |
| Timestamp columns | Choose one UTC contract (`datetime.now(UTC)` vs `CURRENT_TIMESTAMP`) and make both sides semantically equivalent. | Time-zone and clock-skew tests plus online-migration lock/latency review. |
| JSON/list defaults (`topics`) | Do not use a guessed SQL literal; use the column's actual JSON/array type and immutable expression. | PostgreSQL type-specific DDL, existing-row backfill and round-trip tests. |
| Secret material (`ActiveSession.signing_key`) | Keep CSPRNG generation in application code; never introduce a predictable SQL fallback. | Security review and a separately designed database-side secret mechanism, if ever required. |
| UUID7 identity (`UUID7PrimaryKeyMixin.id`) | Keep application-generated UUID7. Do not replace with UUIDv4 or an unverified extension. | Explicit identity ADR, extension/version support matrix and migration rollback plan. |
| Computed/nullable optional fields | Exclude from the default contract. | Schema-diff test proving no generated/nullable field is changed. |

The next implementation slice should be one bounded owner group (for example,
non-null auth flags), with a preflight query, nullable backfill, validation,
`SET DEFAULT`/`SET NOT NULL` only after clean data, and PostgreSQL integration
coverage. A generated inventory must be rerun after each slice; the target is
not to turn security-sensitive callables into SQL defaults.

## BE-03 — relationship verification

Status: **CODE-FIXED / FRESH-EVIDENCE-PENDING**.

- `app/models/chat.py:100-106` uses `Chat.participants` with
  `back_populates="chats"` and `lazy="noload"`.
- `app/models/users.py:181-187` declares the matching `User.chats` relation
  with `back_populates="participants"` and `lazy="noload"`.
- No dynamic `backref="chats"` remains in the mapped relationship.
- `uv run python` metadata inspection confirms both relationships are mapped
  explicitly; the source-level relationship gate has no implicit backref for
  this pair.

The remaining evidence is an async PostgreSQL/SQLite serialization suite that
loads a user and chat without relationship IO, then explicitly uses
`selectinload` at call sites that need participants. Existing focused chat and
repository tests cover the call-site behavior; a fresh aggregate must still
prove there is no `MissingGreenlet` regression on the audited source.

## BE-08 — CDC worker lifecycle audit

Status: **BACKLOG / ARCHITECTURE**. The worker is intentionally not wired into
the application lifecycle; this is not a one-line import fix.

### Current lifecycle graph

1. `app/core/di/infrastructure.py:32-44` provides only the polling/
   LISTEN-NOTIFY `OutboxWorker` as an APP-scoped service.
2. `app/core/lifespan.py:249-265` starts that worker only when
   `settings.embedded_outbox_worker_enabled` is true. Testing disables the
   background task.
3. `app/workers/outbox.py:420-468` is the standalone worker entry point used by
   the outbox-worker container and starts exactly that polling worker.
4. `app/workers/cdc_outbox.py:434-772` defines `CdcOutboxWorker`, but there is
   no `cdc_outbox_enabled` setting, no Dishka provider, and no lifespan task
   that starts it.
5. The existing `tests/test_cdc_outbox.py` and
   `tests/test_cdc_outbox_closure.py` exercise decoder/dispatch/fallback
   behavior hermetically. They do not claim that a production process owns a
   CDC slot. `tests/test_outbox_closure.py` explicitly verifies that the old
   `ENABLE_CDC_OUTBOX` environment variable does not instantiate the CDC worker,
   and the Docker startup contract asserts that the variable is absent.

### Why wiring now is unsafe

- Starting CDC beside the polling worker creates two consumers of
  `stored_events`. NATS message IDs may deduplicate some publishes, but the
  polling path and CDC path have different acknowledgement and retry state;
  duplicate or reordered delivery is not proven absent.
- `_run_fallback_worker()` constructs a raw `OutboxWorker` instead of resolving
  the APP-scoped Dishka instance. If CDC and the embedded worker were enabled,
  fallback would create a second uncoordinated poller with different tuning
  and no lifecycle ownership.
- Replication provisioning creates a publication and logical replication slot
  and requires PostgreSQL replication privileges. There is no migration,
  preflight, slot-retention alarm or operator rollback path in the current
  deployment contract.
- `run_forever()` receives a private asyncpg `_copy_out` stream and
  `stop()` only flips `_is_running`; it does not retain/close the active
  replication connection. A lifecycle integration therefore needs an explicit
  cancellation/connection-shutdown design before production use.
- A silent fallback from CDC to polling would make the active transport
  ambiguous and would invalidate delivery-latency and replay evidence.

### Required ADR and acceptance contract

Before any wiring change, create an ADR and implement it in a bounded RED →
GREEN → REFACTOR slice with PostgreSQL/NATS integration tests:

1. Add an explicit `cdc_outbox_enabled`/transport setting whose default is
   false and which rejects simultaneous CDC and polling ownership.
2. Provide one Dishka APP-scoped transport and start exactly one worker in the
   lifespan. The task must be in the shutdown `TaskGroup`, close the
   replication connection, and expose readiness/lag/slot ownership metrics.
3. Define idempotency and ordering across CDC and polling, including restart,
   replay, NATS outage, malformed WAL and publication/slot loss. Prove that a
   fallback cannot create a second poller.
4. Add migration/preflight checks for PostgreSQL logical-replication support,
   publication/slot ownership and least-privilege credentials; document
   downgrade/remediation behavior.
5. Keep the current polling worker as the default until the full integration,
   race/cancellation, upgrade/downgrade and observability gates are green.

## Audit conclusion

BE-03 is already fixed in code and awaits fresh serialization evidence. BE-02
now has a reproducible, source-anchored inventory, but it is not safe to
declare closed until phased owner migrations address the actionable scalar and
timestamp groups. BE-08 remains an explicit architecture backlog: preserving
the single polling transport is safer than introducing an uncoordinated CDC
consumer without an ownership, idempotency and shutdown contract.
