# AUDIT — Wave 210

**Date:** 2026-06-01
**Branch:** `egorribun`
**Theme:** Group-message **backend completion** (Track G) — **G2** per-recipient read receipts (the live group unread-count bug fix) + **G3** group notification re-tiering + **B** reply-notification live e2e verify (closes W208 §Honesty #4). All three **proven live** end-to-end through the real backend chain.
**Wave streak:** 70th consecutive wave with brainstorming + Phase 1 Explore + Plan-agent design + Phase 3 verify-before-write + W141 anti-pattern discipline.

---

## Scope (user-chosen)

User mandate: *"продолжаем работу на мессенджером согласно нашей roadmap"* → Q0 (AskUserQuestion) → **G2 + G3 combined** (finish the group-message backend in one wave) + the carry-over **B reply-notification live e2e verify**. Two follow-up scope questions → **G2 = backend-complete + FE-api-surface only** (the "Seen by N" group marker UI defers to the G4 group-UI wave; DMs stay 100% unchanged) + **G3 = tests + group-name re-tiering** (not "wire fan-out from scratch" — see the pivotal Phase-1 discovery).

**Two pivotal Phase-1 / Plan discoveries (W141 #3 verify-before-write):**

1. **G3 was already working — the opening-prompt premise was stale.** The handoff said "group push won't fire today," but `get_by_id` (chat_repository.py:64) does `selectinload(Chat.participants)`, returns a `ChatDTO` whose `.participants` is the full N-member list; `handle_message_sent` passes it to `notify_new_message`, whose `[p.id for p in chat_participants if p.id != sender.id]` fans out to any N; and the outbox is live since W205 SW-A. So group push *already fires*. The "won't fire" claim was true *pre-W205* (when the dev outbox was empty). Building "wire fan-out from scratch" would have been dead-on-arrival code. G3 was re-aimed at the *genuine* gap: a group push titled "Alice" with no group context is indistinguishable from a DM → thread the group name in.

2. **The DM-byte-identical landmine has a clean escape.** The unread `msg_stats_cte` scans `Message` only, but the *outer* `get_chats_for_user` query already joins `Chat` (line 139). So instead of branching the existing CTE filter (high DM-regression risk), G2 leaves `msg_stats_cte` **byte-identical** and adds an *additive* `group_unread_cte` + a `CASE WHEN Chat.chat_type='group'` in the outer query. DMs execute the same SQL as yesterday — the landmine is sidestepped, not navigated.

**Plan-agent catch:** `mark_messages_read` has **TWO** callers (the WS dispatcher AND `ChatMaintenanceService.mark_read`, command_service.py — the REST `POST /chats/{id}/read` path). Both must thread `chat_type`.

**6 code SW commits + SW8 live verify + this SW9 close.**

---

## Design decisions (Option A — deliberate blast-radius minimization)

1. **Two mechanisms, NOT one (Option A).** Groups use a NEW `ChatReadReceipt` high-water-mark; DMs keep `Message.read_status`/`read_at` on the **byte-identical** W203 path. Unifying both onto one model is cleaner long-term but would re-route every DM unread count + the entire W203 read marker through new code → high blast radius under W203 §H#5. Option A shrinks the regression surface to "group rows only."
2. **Timestamp high-water-mark, NOT a message-id UUID comparison.** `ChatReadReceipt(chat_id, user_id, last_read_at)`. Group unread = `COUNT(messages WHERE sender_id != me AND (no receipt OR created_at > last_read_at))`. `Message.id > last_read_message_id` would rely on UUID7 byte-lexicographic ordering — fragile across SQLite vs PG, broken for legacy ids. `created_at > last_read_at` is a plain timestamp compare already proven SQLite-safe (cursor pagination, chat_repository.py:386). `last_read_at` alone — no `last_read_message_id` (the count needs only the timestamp; "read up to here" is derivable in G4 without a schema change).
3. **Additive `group_unread_cte` + `CASE`** keeps `msg_stats_cte` + the `ORDER BY` byte-identical (Trap: `msg_stats_cte` must keep scanning ALL chats so its `last_message_at` ordering column stays valid for groups — only the *count* is branched, never the ordering).
4. **Dialect-agnostic check-then-(INSERT|UPDATE) upsert** for the receipt (the W209 `add_participant` precedent, NOT `pg_insert.on_conflict` — PG-only, won't compile on SQLite). The `(chat_id, user_id)` UNIQUE is the idempotency backstop.
5. **`read_receipts` is a defaulted `ChatResponse` field**, populated ONLY by `get_chat_details` (for groups). Defaulted `[]` → the W209 5-site fan-out is untouched; it's service-computed, NOT a `ChatDTO` field → the gatekeeper is irrelevant.
6. **G3 group push** titles by `chat_name` + prefixes the body with the sender (`"Alice: hi"`) so the recipient learns which group AND who; DMs unchanged (`title=sender_name`). The `chat.reply` type still distinguishes a reply for the FE.

---

## SW1 — `ChatReadReceipt` model + migration (`dc182b3c7`)

`feat(wave210-sw1-chat-read-receipt-model)` — `app/models/chat.py` + `app/models/__init__.py` + NEW `alembic/versions/202605300006_create_chat_read_receipts.py`.

`ChatReadReceipt(Base, UUID7PrimaryKeyMixin)` mirrors `MessageReaction` (the child-table precedent): `chat_id`/`user_id` FK CASCADE, `last_read_at` DateTime nullable=False, `UNIQUE(chat_id,user_id)`, `lazy`-free (no relationship), **NO `EventEmitterMixin`** (synchronous broadcast like reactions). **NO standalone `chat_id` index** — the `(chat_id,user_id)` unique key is chat_id-leading, so it serves both `get_read_receipts` (WHERE chat_id) and the CTE join (opposite of `MessageReaction`, whose unique key was user_id-leading). Migration mirrors `202605300003`, `down_revision="202605300005"`. **Risk #2 resolved at impl:** `UUID7PrimaryKeyMixin.id` has a **column-level** `default=generate_uuid7` (mixins.py:18) → the Core `insert(ChatReadReceipt)` populates the PK with no explicit `id=`. **Gate:** the up/down/up cycle ran **live against the real dev PostgreSQL** (`bash scripts/dc.sh run --build --rm --no-deps migrations …`): `202605300005 → 006` upgrade ✓ downgrade ✓ idempotent re-upgrade ✓ single head `202605300006`.

---

## SW2 + SW3 — Repository read + write paths (`c538e15c1`)

`feat(wave210-sw2-sw3-repo-read-write-paths)` — `app/repositories/chat_repository.py` (+ `case`, `ChatReadReceipt` imports).

- **SW2 reads — `_get_chats_for_user_impl`:** `msg_stats_cte` (DM unread, `read_status`) + `last_msg_cte` left **byte-identical**. NEW `group_unread_cte` joins `Chat (chat_type='group')` + outerjoins `ChatReadReceipt` on (chat_id, user_id), counts `sender_id != user_id AND (last_read_at IS NULL OR created_at > last_read_at)`. The outer query's unread column becomes `case((Chat.chat_type=='group', coalesce(group_unread_cte…,0)), else_=coalesce(msg_stats_cte…,0))` + an `.outerjoin(group_unread_cte)`. ORDER BY untouched.
- **`get_unread_count`** gains `chat_type: str = "dm"` + a group branch (the same outerjoin/`or_` predicate). `_set_rls_user` stays (PG-only; the group branch is DB-tested via `get_chats_for_user`, not here — SQLite rejects `SET LOCAL`).
- NEW **`get_read_receipts(chat_id) -> list[(user_id, last_read_at)]`** + **`get_chat_type(chat_id) -> str | None`** (cheap PK lookup for the WS dispatcher).
- **SW3 write — `mark_messages_read`** gains `chat_type`. DM path **byte-identical** to W203. Group path: (a) read `old_last_read_at`; `affected` = COUNT(other-sender messages, `created_at > old_last_read_at` if a receipt existed) so the broadcast gate keeps DM semantics; (b) check-then-(INSERT|UPDATE) upsert `last_read_at = utc_now()`; (c) return `(read_at, affected)`. WS frame shape UNCHANGED (`{type:"read", chat_id, user_id, read_at}`).
- **mypy Passed** (repo is in the pre-commit mypy scope).

---

## SW4 + SW5-schema — Wiring + schema (`d3ef5e856`)

`feat(wave210-sw4-sw5-wiring-schema)` — `app/schemas/chat.py` + `app/api/ws/dispatcher.py` + `app/services/chat/command_service.py` + `app/services/chat/query_service.py`. (Schema + wiring committed together — `query_service` imports `ReadReceiptInfo`, so a self-consistent commit.)

- **Schema:** NEW `ReadReceiptInfo{user_id, last_read_at}` + defaulted `ChatResponse.read_receipts: list[ReadReceiptInfo] = Field(default_factory=list)`.
- **`ChatMaintenanceService.mark_read`** (the REST path — the Plan-agent's "second caller") passes `chat.chat_type`. **WS `dispatcher`** read handler fetches `get_chat_type(chat_uuid)` after the participant check + passes `chat_type or "dm"`. **`get_chat_details`** passes `chat.chat_type` to `get_unread_count` + populates `read_receipts` (gated on group). **mypy Passed.**

---

## SW5-FE — FE api-surface (`f2175c101`)

`feat(wave210-sw5-fe-api-surface)` — `frontend/src/api/chat.ts`. Optional `read_receipts?: {user_id, last_read_at}[]` on the `Chat` interface. **API-surface only** — no marker UI, no `applyReadFrame` change (DMs unchanged; the group "Seen by N" marker is G4). **Type-only → zero bundle delta** (the interface field erases at compile time — verified byte-identical to W209, §SW8).

---

## SW7 — G3 group notification re-tiering (`452e3bdee`)

`feat(wave210-sw7-g3-group-notification-retiering)` — `app/services/chat/notification_service.py` + `app/services/event_handlers.py`.

`notify_new_message` gains `chat_type`/`chat_name` params (defaulted "dm"/None → existing callers/tests tolerant). For a group: `title = chat_name or "Group"`, `body = f"{sender_name}: {preview}"` (empty-body guard avoids a dangling "Alice: "). DMs unchanged. Applied to BOTH the generic `chat.message` + the `chat.reply` paths. `handle_message_sent` threads `chat_type=chat.chat_type, chat_name=chat.name` (it already holds the chat DTO). **mypy Passed.** The fan-out itself is unchanged — it was already participant-count-agnostic.

---

## SW6 + SW7 tests (`557139245`)

`test(wave210-sw6-sw7-g2-g3-tests)` — NEW `tests/test_chat_read_receipts.py` (8) + updates to `test_chat_command_service.py`, `test_ws_dispatcher_full.py`, `test_chat_query_service.py`, `tests/services/test_chat_helpers.py`.

- **G2 (8 real-DB tests, SQLite `db_session`)** — driven through **`get_chats_for_user`** NOT `get_unread_count` (the latter trips `SET LOCAL` RLS on SQLite): (1) group unread counts other-sender messages, 0 for the sender; (2) **per-user, not global** — A marks read → A=0 BUT B still unread (**the headline bug fix**); (3) HWM advances after read + new message; (4) upsert idempotent (one row, second mark `affected==0`); (5) `affected` gates broadcast; (6) **DM byte-identical** + `read_status` still flips + NO `ChatReadReceipt` row for a DM (the regression guard); (7) `get_read_receipts` rows for group / `[]` for DM; (8) mixed DM+group in one list (the CASE picks the branch per row). Determinism: "already-read" messages get an explicit past `created_at`; the "new" message reads the receipt's actual `last_read_at` back + stamps `+1s` (guarantee, not a wall-clock race).
- **Service/dispatcher updates:** the two `mark_messages_read.assert_called_once_with(chat.id, user.id)` → 3-arg (`"dm"`/`chat.chat_type`) + `get_chat_type` AsyncMock on both dispatcher tests (else `await` on a plain MagicMock fails) + a new `test_mark_read_group_passes_chat_type` + a new `test_group_populates_read_receipts`.
- **G3 (3 new + 2 stand-in updates):** group message titles by group name + fans out to all N-1; group reply-supersede carries the group name; `handle_message_sent` threads chat identity; the 2 existing handler stand-ins get `chat_type="dm", name=None` (else `chat.chat_type` AttributeErrors on the bare `SimpleNamespace`).

---

## SW8 — Live verification (B + G2 + G3, all PROVEN LIVE) + gates

**Rebuilt the backend with W210 code** (`bash scripts/dc.sh up -d --build backend`; the `chat_read_receipts` table already existed from SW1's migration cycle) and drove the real backend through the CSRF dance (`GET /auth/csrf-cookie` → token from the cookie jar → `X-CSRF-Token` header) with two seeded accounts (`test@university.dev` userA, `anna.petrova@` userB, `ivan.sokolov@` third member).

- **B — reply-notification (closes W208 §Honesty #4):** anna sent a DM message → test@ **replied** (`reply_to_message_id`; REST response `reply_to` set ✓) → within ~2 s anna's `GET /api/v1/notifications` showed **`chat.reply`=1, `chat.message`=0** (`title='User' body='Test replying to Anna'`). The W208 reply-supersede works end-to-end through the live outbox: the quoted author gets a specific `chat.reply`, NOT a generic `chat.message`. ✓
- **G2 — per-recipient unread (the headline bug fix):** test@ created a group `W210 Test Group` with [anna, ivan] (`chat_type=group` ✓) + sent a message. anna's group `unread_count = 1` (via the new `group_unread_cte` branch); the sender sees 0. Then **BEFORE anna marks read: anna=1, ivan=1; anna marks the group read (`POST /chats/{id}/read` 200); AFTER: anna=0, ivan=1 (UNCHANGED).** Pre-W210, the global `read_status` flip would have zeroed ivan too — the per-recipient `ChatReadReceipt` makes each member's unread independent. ✓
- **G3 — group-name re-tiering:** anna's notification for the group message = **`type=chat.message title='W210 Test Group' body='User: Group hello from test'`** — group-name title + sender-prefixed body, distinguishable from a DM push. ✓
- Temp cookie jars deleted (security).

**Backend full suite (W203 §H#5 — broadcast/unread hot path → single full run):** `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py` → **2988 passed / 25 skipped / 0 failed (3m07s)**. Reconciles exactly: W209 baseline **2975** + 13 new (8 read-receipt + 1 command + 1 query + 3 notification) = **2988** (the matching arithmetic is a no-cascade signal). The **OpenAPI contract** test is in this suite and **passed** — `read_receipts` is a pure ADDITION → the superset matcher holds, no snapshot regen (W205 gotcha).

**FE:** `ruff check` clean; `npx tsc --noEmit` 0; `npm run test:ci` **EXIT=0, functions ≥ 70%** (the FE change is type-only → no new functions, coverage unchanged); `npm run build` × 3 **BYTE-IDENTICAL** — main `index-BNy-Fnph.js` **180,268 b** sha `c4eabf25fc0b90f77ffdec1b9e8094e5542df92ac0d1a3b9ab1d84c7b146f4a6` × 3 + server.js sha `d4911fbebcd46ddce101eeb20025e1181cbb7f1278f12be6f13a9ebb92a8e65f` × 3.

**Bundle framing (honest, stronger than the plan anticipated):** the main JS is **BYTE-IDENTICAL to the W209 close** (same filename `index-BNy-Fnph.js`, same 180,268 b, same sha). W210's entire client-bundle delta is **zero** — the only FE change is a TypeScript `interface` field, which erases at compile time. (Unlike W209, which added runtime `chatApi` functions and shifted the hash.) Tree-shake + SW-IIFE invariants preserved by construction. server.js also byte-identical to W209 — all W210 backend changes are in the route-lazy / non-SSR-emitting paths.

---

## Gates (end-of-wave)

| Gate | Result |
|------|--------|
| `python -m py_compile` (each SW) | OK |
| `uv run alembic` up/down/up + heads (live PG) | single head `202605300006`, reversible, idempotent |
| `uv run ruff check` (app + tests) | All checks passed |
| Backend full `uv run pytest --ignore=…ws_hub_contract` | **2988 passed / 25 skipped / 0 failed** (2975 + 13) |
| OpenAPI contract | passed (superset, no regen) |
| `npx tsc --noEmit` (FE) | 0 |
| `npm run test:ci` (coverage) | EXIT=0, functions ≥ 70% |
| `npm run build` × 3 | BYTE-IDENTICAL (main `c4eabf25…` + server `d4911fbe…`) — **= W209** |
| Tree-shake / SW IIFE | preserved by construction (byte-identical to W209) |
| **Live verify** (rebuilt backend, real chain) | B ✓ (chat.reply) · G2 ✓ (anna=0, ivan=1) · G3 ✓ (group-name title) |
| husky pre-commit (every commit) | clean — NO `--no-verify` |

---

## §Honesty (0-2 OPEN — one closure, carry-forward only)

- **CLOSED — W208 §Honesty #4** (reply-notification live e2e): verified live (SW8) — userA replies to userB → outbox → `GET /notifications` for userB shows `chat.reply`, not `chat.message`.
- **Carry-forward (unchanged):** `live-in-DEV-only` (prod has no ws-hub/NATS — user-deferred; live WS features self-heal via refetch in prod) + W134 §H#2 (bundle-delta recording-only — moot this wave, bundle is byte-identical to W209) + W134 §H#10 (/messenger Phase 5 SSR `ssr: 'data-only'` by-design).
- **NEW G2 by-design deferrals (not defects):** the "Seen by N / all" group **marker UI** is G4 (no group chat *view* polish exists yet; the backend + the `read_receipts` api-surface ship now so G4 is pure-FE). The DM «Просмотрено» marker + `applyReadFrame` are unchanged — W210 introduces no FE regression for DMs; a group's live `read` frame still (cosmetically) flips the DM-shaped marker when ≥1 member reads, but that surfaces only in G4's group view.
- **NEW finding (CI-infra, pre-existing, not introduced by W210):** the "Verify OpenAPI Types" CI gate (ci.yml:716) diffs `frontend/src/api/generated/schema.ts` — a file the codegen (`@hey-api/openapi-ts` → `types.gen.ts`) doesn't produce, so `git diff --quiet -- <nonexistent>` always returns 0 → the gate is a **no-op** (explains why W209's `ChatResponse` field additions never needed a regen either). The chat domain uses hand-written types in `chat.ts`, not the generated dir, so the `read_receipts` api-surface rides on the hand type; `types.gen.ts` was deliberately NOT regenerated (regenerating the 125 KB artifact risks unrelated cross-endpoint drift for zero benefit). W211+ housekeeping candidate: fix the gate's stale diff path.

---

## (z) discoveries & anti-patterns

**0 NEW (z) discoveries.** The two pivotal findings (G3-already-works; the additive-CTE DM-byte-identical escape) + the Plan-agent's `mark_messages_read`-has-two-callers catch + the `UUID7PrimaryKeyMixin` column-default verification were all surfaced by Phase 1 Explore + Phase 3 verify-before-write + the Plan agent *before* any edit (W141 #3). The within-iter sub-fixes (the `get_chat_type` dispatcher mock, the 2 handler stand-in updates, the unused-`Chat`-import removal, the ruff-format re-stages) are SAME-mechanism corrections per W138 L#1, not (z) cascades. Extends the low-(z) streak (W145-W210).

**0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

**W141 compliance:** #1 — every SW landed 1-iter; the within-iter sub-fixes are SAME-mechanism (W138 L#1), no mechanism pivots. #3 — Phase 1 + the Plan agent caught the stale "G3 won't fire" premise, the additive-CTE escape, the two `mark_messages_read` callers, the timestamp-vs-UUID HWM, the `_set_rls_user`-on-SQLite constraint, and the `read_receipts`-defaulted-field safety before each edit. #4 — every "passed/GREEN" attributed only after captured gate output (live migration cycle, 2988 pytest, test:ci EXIT=0, Build × 3 sha); B/G2/G3 attributed only after the captured live network + DB evidence (chat.reply=1, anna=0/ivan=1, group-name title). #15 — all 6 code commits fired the husky chain cleanly (the SW1/SW2 ruff-format re-stages are the documented flow; the rest pre-formatted via the pinned hook), NO `--no-verify`.

---

## NEW Gotchas (added to CLAUDE.md)

1. **Additive `group_unread_cte` + `CASE` keeps the DM unread path byte-identical** — leave `msg_stats_cte` + the ORDER BY untouched (it must keep scanning ALL chats for `last_message_at`); branch only the *count* column via a `CASE` on `Chat.chat_type` in the outer query (which already joins `Chat`).
2. **Per-recipient read = timestamp high-water-mark, NOT a message-id UUID compare** — `created_at > last_read_at` is dialect-safe (proven SQLite + PG); `Message.id > last_read_message_id` relies on fragile UUID7 byte ordering.
3. **G3-already-works was a stale-handoff premise** — the outbox + a participant-count-agnostic `notify_new_message` already fan out to N members since W205; the real gap was group *context* in the push (group-name title), not the fan-out. Verify-before-write re-aimed the wave.
4. **`mark_messages_read` has two callers** — the WS dispatcher (which must fetch `get_chat_type`) AND `ChatMaintenanceService.mark_read` (REST, which already holds the chat). Any signature change touches both.
5. **The "Verify OpenAPI Types" CI gate is a no-op** — it diffs `frontend/src/api/generated/schema.ts`, which the current codegen doesn't emit (`types.gen.ts` instead). Adding a backend `ChatResponse` field needs no FE codegen regen; the chat domain uses hand-written `chat.ts` types.

---

## Messenger arc & next

W203 read receipts → W204 live bridge → W205 new_message + edit/delete → W206 reactions → W207 reply/quote + reactor-list + typing → W208 reply notifications + cleanup + message-list polish → W209 group-chat backend foundation (G1) → **W210 group-message backend completion (G2 read receipts + G3 notification re-tiering) + B live verify**.

**W211+ candidates:** **G4** group UI (create-group modal, member-management panel, group name/avatar rendering, the "Seen by N" group marker consuming `read_receipts`, name-fallback in `MessengerContext`/`useMessengerController`); then Track **A** (attachment perfection), **S** (pgvector message search), **F** (forwarding). Housekeeping: fix the no-op "Verify OpenAPI Types" gate's stale diff path. Prod ws-hub + NATS deploy (closes `live-in-DEV-only` across W203-W210) remains user-deferred.

Memory references (`.claude` profile): `memory/wave210_backlog.md`, `memory/wave211_opening_prompt.md`.
