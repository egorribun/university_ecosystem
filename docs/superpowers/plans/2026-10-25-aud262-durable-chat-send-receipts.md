# AUD-262 Durable Chat Send Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the assigned implementation and a fresh whole-change reviewer before publication. Steps use checkbox syntax.

**Goal:** Preserve a committed keyed chat send across Redis completion failure, state loss, lease expiry, and overlapping writers without duplicating its Message or MessageSent outbox event.

**Architecture:** Store a private completed-send receipt atomically with Message, Attachment rows, and MessageSent in the existing request-owned primary UOW. Authorize first, consult that receipt before Redis, and let an exact named database uniqueness conflict adjudicate overlapping Redis admissions. Redis remains optional admission/cache, not durability authority.

**Tech Stack:** Python 3.14, SQLAlchemy 2 async sessions, PostgreSQL/asyncpg, Alembic, existing Redis cache, pytest/FakeRedis.

**Spec:** The approved AUD-262 design is captured in Global Constraints below. Repository authorities are `AGENTS.md`, `app/AGENTS.md`, ADR-033, and the AUD-262 audit finding; no new deployment or credentials are authorized.

## Verified starting evidence

- Source HEAD `6ba0de220b497126f51d31b84653a2d1b5d35cb8`; tested PR merge `3c11b7bfe95aeaf720b445765c5a39b5894582bb`.
- CI run 40169040139, PostgreSQL job 121096797464: prior AUD-262/343 cohort **13 passed**, full integration **322 passed / 9 existing skips**, then the separate required durable cohort **3 failed / 2 passed / zero skips or errors**, at 2026-10-25 06:41:48 UTC.
- Deleted-cache, expired-cache, and overlapping-admission tests each observed **2 Messages + 2 MessageSent**, expected **1 + 1**. Live uncommitted lease and precommit rollback controls passed.
- The tested merge and source HEAD both bind `tests/test_aud262_durable_replay_postgres.py` to blob `799f6a53401041ca8578d90e297e9fef2a0cd38b`, `command_service.py` to `cdf46f56a3537c475c7f5838f592cababd0dd912`, and the reusable backend workflow to `00d11f3c7aada02fc78f6947a118913f8269d94a`.
- The legacy PowerShell downgrade step masked a real quarantine-ledger refusal. Its green status is not downgrade evidence.
- Full `app/models` inventory has no reusable completed-command receipt model.

## Global Constraints

- One private receipt per `(chat_id, user_id, key_digest)`; no raw client key, message body, response payload, or payload fingerprint in the receipt.
- Stable versioned domain-separated SHA-256 digest; never derive durable identity from optional rotating `IDEMPOTENCY_HMAC_SECRET`.
- First successful payload wins; retries may change text/reply metadata or omit files.
- A fixed 24-hour DB-clock window starts when the completed receipt is staged immediately before commit; replay never refreshes it. Eligibility uses the primary database clock, not Redis TTL or application wall time.
- Chat existence 404, then current membership 403, then receipt lookup, then Redis. No read replica, new session owner, RLS bypass, or privileged role/function.
- Active receipt plus existing scoped/RLS-visible message returns its current response. Soft deletion returns the existing tombstone. Hard deletion/history clear retains a nullable-message receipt and returns existing 409 `idempotency_in_progress` plus `Retry-After: 1` until expiry; no 410 or resurrection.
- Chat/user deletion cascades receipt deletion; message hard deletion sets only receipt `message_id` to NULL.
- Only the exact receipt uniqueness violation is recoverable as a replay. Roll back the whole losing UOW, preserve reference-aware upload cleanup, reapply request RLS and re-authorize before loading the winner. Capture immutable user UUID before any rollback.
- Preserve unrelated IntegrityError, transport/commit error, and cancellation propagation. Never perform a second insert after unknown commit outcome; a later request may recover the durable receipt.
- New sends need not work during Redis outage. A committed receipt must replay before touching unavailable Redis.
- Preserve live uncommitted Redis lease 409. New durable cache values are hints only; cap completed TTL to the DB window remaining and do not refresh on replay.
- Legacy completed cache entries retain bounded existing scoped hydration only when no receipt exists. An observed expired receipt overrides legacy cache. Durable-v1 entries with missing/expired receipt are compare-deleted only if unchanged before normal admission. Historical sends cannot be backfilled, and mixed old/new writers are outside the durability guarantee.
- No threshold, warning, scanner, required-context, or migration-baseline waiver. New migration and changed Tier-0 source require 100% policy coverage; final-source required checks remain mandatory.

## Review Focus

1. Lost acknowledgement after real COMMIT must leave one receipt/message/event and referenced uploaded object; same-key retry returns the winner.
2. Ineffective Redis admission must yield one DB winner and clean only the losing request's unreferenced uploads, including rollback-expired ORM user state.
3. Exact expiry, stale completed cache, and concurrent expired-key replacement must permit one new send without extending the old window.
4. Membership removal and hard/soft deletion between first send and replay must preserve authorization/deletion semantics rather than reveal or recreate content.
5. Unrelated uniqueness errors, cancellation, and cleanup failures must not be mistaken for receipt conflicts or replace the original failure.

## Task 1: Extend behavioral acceptance before implementation

**Files**
- Preserve initial five cases in `tests/test_aud262_durable_replay_postgres.py`.
- Create `tests/test_aud262_receipt_lifecycle.py` for real-session lifecycle and exact clock-boundary coverage.
- Create `tests/integration/test_aud262_receipt_schema_postgres.py` for production migration/schema/RLS semantics.
- Create `tests/test_aud262_receipt_migration.py` for all migration branches.
- Modify the bounded committed-retry assertion in `tests/test_aud262_postcommit_redis_failure.py` only with implementation.
- Adapt real receipt dependencies in owned mock fixtures in `tests/test_chat_idempotency_ownership.py`, `tests/test_chat_command_branch_closure.py`, `tests/test_chat_command_failure_paths.py`, and `tests/test_chat_command_service.py`; do not weaken existing behavioral assertions.

**Interfaces:** real `ChatMessageDispatcher.send_message`, `uow_from_session`, `ChatRepository`, independent primary `AsyncSession` connections, and an owned FakeRedis boundary.

- [x] Observe the initial three semantic REDs and two passing controls above.
- [ ] Add independent-session tests: actual COMMIT followed by injected lost acknowledgement; Redis unavailable on committed retry; two real uploads under ineffective Redis admission; rollback removes receipt/message/attachments/outbox; unrelated integrity failure and cancellation propagate.
- [ ] Assert one committed Message, one MessageSent, one receipt, same returned message ID, no extra uploads on replay, and exact referenced-versus-unreferenced storage survival.
- [ ] Add DB-boundary tests for just-before/equal/after expiry, no extension after repeated replay, stale durable cache after receipt deletion, observed-expired receipt against legacy cache, and concurrent expired-key reuse.
- [ ] Add scope/HMAC-rotation, changed-payload/omitted-files, missing-chat, removed-membership, soft-delete, hard-delete, and clear-history cases.
- [ ] Publish test-only evidence where an additional failing boundary is needed before its production branch. Observe semantic failure, not fixture/import/format failure.

## Task 2: Private receipt schema and repository ownership

**Files**
- Create `app/models/chat_send_receipt.py`.
- Modify `app/models/__init__.py` to register the private model only.
- Create `alembic/versions/202610250001_add_chat_send_receipts.py`, parent `202610200001` after the current Alembic head is rechecked.
- Modify `app/repositories/chat_repository.py`; use existing `uow.chats` and `uow.session`. No UOW lifecycle/provider change.

**Exact schema**
- `ChatSendReceipt(Base, UUID7PrimaryKeyMixin)`, table `chat_send_receipts`.
- Required `chat_id UUID REFERENCES chats(id) ON DELETE CASCADE`, `user_id UUID REFERENCES users(id) ON DELETE CASCADE`, `key_digest VARCHAR(64)`, `completed_at TIMESTAMPTZ`, `expires_at TIMESTAMPTZ`.
- Nullable `message_id UUID REFERENCES messages(id) ON DELETE SET NULL`.
- Named unique constraint `uq_chat_send_receipts_chat_user_key` on `chat_id,user_id,key_digest`.
- Named indexes `ix_chat_send_receipts_message_id`, `ix_chat_send_receipts_user_id`, and `ix_chat_send_receipts_expires_at` (expiry plus id).
- Required timestamps are explicitly supplied from one DB-clock sample; no incomplete model defaults. No ORM relationships or public DTO fields.
- FORCE + ENABLE RLS. Policy USING/WITH CHECK requires the transaction's nonempty `app.current_user_id` to equal `user_id`, current chat participation, and a visible parent chat (retaining parent tenant policy). No global expired-row visibility.

**Interfaces**
- Private immutable `SendReceiptState(message_id: UUID | None, expires_at: datetime, observed_at: datetime)`.
- `ChatRepository.get_send_receipt(chat_id: UUID, user_id: UUID, key_digest: str) -> SendReceiptState | None`: establish request RLS, use the primary DB clock, return an expired state too so cache cannot override it.
- `ChatRepository.create_send_receipt(chat_id: UUID, user_id: UUID, key_digest: str, message_id: UUID) -> datetime`: current DB clock; conditional DELETE of only this expired key; INSERT completed receipt; explicit flush; return immutable expiry. No commit.
- `ChatRepository.prune_expired_send_receipts(chat_id: UUID, user_id: UUID, *, limit: int = 100) -> int`: scoped, ordered bounded candidate selection and expiry-rechecked DELETE, no commit; cap each invocation at 100.
- `ChatRepository.send_receipt_remaining_seconds(expires_at: datetime) -> int`: nonnegative floored remaining seconds from primary DB time, used only for cache TTL.

- [ ] Test schema privacy, exact named uniqueness, both cascades, nullable SET NULL, expiry index, atomic rollback, and fail-closed non-superuser RLS.
- [ ] Implement model and online PostgreSQL migration with 10-second lock timeout and 60-second statement timeout, rejecting unexpected existing table state before writes.
- [ ] Implement receipt methods in existing primary request UOW. Conditional expired replacement and unique conflict must be before chat `updated_at` UPDATE to avoid lock-order inversion.
- [ ] Exercise actual migration operations in owned isolated PostgreSQL schema; separately cover online/non-PG/offline/existing-table/current-schema guards and the approved downgrade branch to 100%.
- [ ] Verify ordinary SQLite repository tests remain meaningful without pretending SQLite proves PostgreSQL concurrency/RLS.

## Task 3: Dispatcher replay and exact conflict recovery

**Files:** `app/services/chat/command_service.py`, owned tests listed above, and `contracts/redis-keys.md` if cache-value documentation requires updating.

**Interfaces**
- `_make_send_receipt_digest(chat_id: UUID, user_id: UUID, client_key: str) -> str`: SHA-256 of fixed versioned domain bytes, UUID bytes, and UTF-8 key; independent of Redis HMAC configuration.
- `_is_send_receipt_conflict(error: IntegrityError) -> bool`: require PostgreSQL SQLSTATE 23505 and exact constraint `uq_chat_send_receipts_chat_user_key` from supported driver diagnostic/cause, not message substring.
- Private replay helper consumes captured UUID, `SendReceiptState`, and existing scoped `get_message_by_id`; returns existing MessageResponse or the unchanged 409 contract.

- [ ] Capture `user_id = user.id` once before rollback can expire ORM state.
- [ ] Keep chat 404 and membership 403 ordering; lookup receipt before any Redis access or payload/upload validation.
- [ ] Active receipt replays without touching Redis. Expired state is remembered to suppress legacy cache replay.
- [ ] Retain owner-token Redis admission/renewal. Compare-delete stale durable completed values only; preserve another owner's pending value.
- [ ] In the existing atomic write, create Message, record MessageSent, stage attachments, create/flush receipt, update chat timestamp, and commit once.
- [ ] On exact receipt conflict only: roll back all loser SQL; re-establish RLS; perform reference-aware upload cleanup; re-authorize on primary; reload winning active receipt; replay or return existing bounded conflict if no active usable winner. Never blindly reinsert.
- [ ] Existing error path still retains lease for unknown commit outcome and preserves errors. Do not broaden cancellation swallowing.
- [ ] Promote cache only for owned token with `status=completed`, `receipt_version=1`, `message_id`, and fixed expiry; TTL is floor(DB remaining), at most 86400. If no whole second remains, clear only own pending value instead.
- [ ] Update only the already-committed retry assertions in the prior seven-case regression to replay. Preserve transport/unexpected-error/cancellation first-call behavior, no-key path, and live uncommitted lease 409.
- [ ] Run initial five, lifecycle/schema tests, prior 13-case cohort, complete backend suite, Ruff/types, policy/migration checks, and full required final-source CI. Integration follows the existing pull-request workflow.

## Task 4: Bounded cleanup, limitations, and final review

- [ ] Invoke scoped expired cleanup only for an authorized keyed new send in its existing UOW; exact-key conditional replacement remains independent of the pruning batch. Cleanup must not refresh or shorten a live receipt.
- [ ] Verify more than 100 expired receipts remove at most 100 per prune; unrelated user/chat rows and active rows remain; repeated calls progress; retained expired rows do not prevent same-key reuse.
- [ ] Document logical 24-hour retention separately from physical storage. Current runtime maintenance uses ordinary sessions and offers no existing narrow global receipt-purge authority. Inactive scopes can retain non-content receipt metadata until their chat/user is deleted; no finite global physical-retention claim is made.
- [ ] Leave automatic inactive-scope purge/physical-retention readiness explicitly open for a separate reviewed design. Do not add bypass GUCs, new roles, security-definer functions, global SELECT visibility, or deployment configuration.
- [ ] Record exclusion of legacy sends/backfill/mixed writers and Redis-outage availability for new sends.
- [ ] Obtain fresh whole-change review covering the five Review Focus items and re-run all affected final-source checks after fixes. Do not close AUD-262 from the initial five tests alone or claim global retention readiness.

## Downgrade safety decision

**Recommended:** explicit protective refusal with `downgrade_policy = "irreversible"` and exact reason:

> Dropping chat send receipts can discard committed idempotency history and permit duplicate messages

The downgrade must raise before any schema/data mutation. Tests prove refusal leaves table, active receipts, messages, and outbox untouched; all migration branches retain 100% coverage. This is a new protective design boundary, not an extension of historical migration dispositions or a coverage waiver.

**Alternative considered:** ACCESS EXCLUSIVE lock, check for active receipts against DB time, permit drop only when none remain. This preserves windows if implemented correctly, but needs a new reviewed guarded-preflight policy path and deployment coordination; existing generic policy accepts only the specifically reviewed BE-02 guard. Do not silently expand that allowlist.

**Shared workflow:** maintainers separately coordinate exact failure/refusal checks for the masked legacy PowerShell step and the canonical migration-policy gate. The migration workflow and its validation belong to the same reviewed change.

## Implementation status

The initial semantic regression proof is established. Implementation, expanded acceptance, migration coverage, independent review, and final-source CI remain pending. The inactive-scope physical-retention decision remains open.
