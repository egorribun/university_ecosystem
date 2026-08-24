# AUDIT — Wave 209

**Date:** 2026-06-01
**Branch:** `egorribun`
**Theme:** Group-chat **backend foundation** (Track G, slice G1) — the first wave of the corporate-messenger program. Adds chat *identity* (`chat_type`/`name`/`created_by`) + a group create/membership flow + the FE API surface; the group **UI** + per-recipient read receipts + group notification re-tiering are deferred to G2-G4.
**Wave streak:** 69th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 anti-pattern discipline.

---

## Scope (user-chosen)

User mandate: *"продолжаем работу на мессенджером согласно нашей roadmap"* → 1st AskUserQuestion → **"1+3"** reframed in prose to a **corporate-messenger, backend-first program**: *"довести до уровня корпоративного мессенджера без излишек (групповые чаты, пересылка, вложения, поиск через pgvector); упор преимущественно в backend, нужен фундамент на котором можно строить frontend"*. 2nd AskUserQuestion → **Group chats G1 (Recommended)** — the user's stated #1, unblocking the most frontend.

**Key Phase-1 discovery:** the chat model is **already ~70% group-ready** — `chat_participants` is a plain many-to-many `Table` (no two-party columns), and `broadcast_to_chat` / `check_participant` / reactions / typing already iterate N participants generically. What was missing is **identity** + a **create/membership flow**.

**The program (4 tracks, ~7-11 waves):** **G** group chats (L-XL, ~3-4) → **A** attachment perfection (M-L, ~2-3) → **S** pgvector message search (M, ~1-2) → **F** forwarding (S, ~1). W209 = Track G slice **G1** (backend + FE API surface).

**Deferred (each its own future wave, §Honesty caveats):** **G2** per-recipient read receipts (`ChatReadReceipt` — the current per-message `read_status`/`read_at` is a documented group limitation), **G3** group notification re-tiering (the W208 reply-supersede assumes 2 parties) + live WS member-change frames, **G4** the create-group modal + group name/avatar rendering + member-management UI.

**7 code SW (SW1-SW7) + SW8 verification + this SW9 close.**

---

## Design decisions (grounded in existing patterns)

1. **`chat_type` = `String(20)` + `CheckConstraint("chat_type IN ('dm','group')")`, NOT a `StrEnum`** — mirrors `Attachment.file_type` (a closed display discriminator), not `UserRole` (a widely-used authz role). + a Python `default="dm"` *alongside* `server_default="dm"` (see SW2 landmine).
2. **`chat_participants` stays a plain `Table` — NO per-member role, NO association-object upgrade.** Roles are "излишек" for a foundation and would force touching every `selectinload(Chat.participants)` site. Owner = `Chat.created_by`. Roles → a later wave.
3. **Member authz:** any participant may **add** + **rename**; **remove** = `created_by` (owner kicks) OR self-leave; else 403. A DM rejects all four → 400 `not_a_group`. Authz-first (403 before 400 — a non-member must not learn a chat is a DM).
4. **Group size:** min **3** total (creator + ≥2), max **100**. Min-3 is load-bearing — avoids colliding with `find_existing_dm`'s `==2` participant lookup.
5. **Dedicated endpoints** (`POST /chats/groups`), not an overloaded `POST /chats` (the existing idempotent DM path stays untouched).
6. **`created_by` FK `ondelete="SET NULL"`** — deleting an owner account never cascade-deletes the group (it becomes ownerless; ownership-transfer is out of G1).

---

## SW1 — Model + migration (`f9dbdd846`)

`feat(wave209-sw1-group-chat-model-migration)` — `app/models/chat.py` + NEW `alembic/versions/202605300005_add_group_chat_fields.py`.

`Chat` += `chat_type` (String(20), `default="dm"`+`server_default="dm"`, CheckConstraint `ck_chats_chat_type`), `name` (nullable String(128)), `created_by` (FK→users SET NULL). Migration mirrors the W203/W205/W207 idempotent skeleton (`_table_exists`/`_column_exists` guards), `down_revision="202605300004"`. **Gate:** the up/down/up cycle ran **live against the real dev PostgreSQL** via `docker compose run --build --rm --no-deps migrations` (the `migrations` service `build: context: .` bakes source in; `--build` was load-bearing — without it the one-off container runs pre-edit code): `202605300004 → 005` upgrade ✓ clean `005 → 004` downgrade ✓ idempotent re-upgrade ✓ single head `202605300005`.

---

## SW2 — DTO + repository methods (`d1fda7036`)

`feat(wave209-sw2-group-repo-dto)` — `app/schemas/dtos/chat.py` + `app/repositories/chat_repository.py` + NEW `tests/test_chat_repository_groups.py` (5 real-DB tests).

- `ChatDTO` += `chat_type`/`name`/`created_by` — the **silent gatekeeper**: the repo returns `ChatDTO` via `model_validate`, so without these the columns load but Pydantic drops them and the query service has nothing to forward.
- Repo: `create_group` (ORM `Chat(chat_type="group", …)` + dedupe-append + flush + `_to_dto`, no Redis lock), `add_participant`, `remove_participant` (`delete`), `rename_chat` (`update`; `updated_at` onupdate re-sorts). `create_chat` + `find_existing_dm` (the `==2` DM lookup) **untouched**.
- **`add_participant` is a dialect-agnostic check-then-insert (NOT `pg_insert.on_conflict_do_nothing` like `add_reaction`):** the W206 reaction tests are mock-only because `pg_insert` can't compile on the SQLite test DB. For a *foundation* the user wants solid, the SELECT-then-INSERT (`check_participant` + a plain Core `insert`) runs identically on SQLite + PostgreSQL, so the full add-participant path is real-DB-testable end-to-end. The composite `(chat_id, user_id)` PK is the uniqueness backstop; the pre-check makes a re-add a clean no-op (returns False → caller skips broadcast). Only trade: atomicity against a concurrent *same-user* double-add — benign + rare for an admin action, PK-backstopped.
- **LANDMINE — the DM-regression trap:** adding `chat_type` to `ChatDTO` retro-activates a hidden break in the *untouched* `create_chat` DM path. `_to_dto(new_chat)` runs `ChatDTO.model_validate(new_chat)` right after `flush()`, and `chat_type` is a **server-default-only** column SQLAlchemy leaves *expired* post-INSERT → a synchronous pydantic read of an expired column in an async session → `MissingGreenlet`. Fix: belt-and-suspenders Python `default="dm"` *alongside* `server_default="dm"` (Python default populates the ORM object in-memory at flush; autogenerate compares only the DDL default → diff-clean). This 1-line model tweak shipped in the SW2 commit (logically part of "make the DTO/repo work"; W138 L#1 within-mechanism).
- **5 tests:** create_group identity+members, creator-dedup, add idempotency, remove idempotency, rename — all real `db_session` (SQLite, schema from models). Assertions use column-level SELECTs (fresh DB state, not the session identity map).

---

## SW3 — ChatResponse + query-service 5-site population (`281e3f213`)

`feat(wave209-sw3-chatresponse-query-service)` — `app/schemas/chat.py` + `app/services/chat/query_service.py` + `tests/test_chat_query_service.py`.

- `ChatResponse` += `chat_type`/`name`/`created_by`. New input schemas `GroupChatCreate{name, participant_ids}`, `AddParticipant{user_id}`, `RenameChat{name}`.
- **The W203-SW8 rule is a *5*-site fan-out for `ChatResponse`:** explicit-pass at `creation_service.py:112`/`:144` (SW4) + `query_service.py:117`/`:203`; the `query_service.py:168` `model_dump(...)` **spread** auto-carries them and must NOT be re-passed (duplicate-kwarg crash). A missed explicit site silently renders a group as a nameless DM — *no error*.
- `test_chat_query_service`: `_mock_chat` parameterized with `chat_type`/`name`/`created_by` (defaults "dm"/None/None keep existing DM tests green; explicit set avoids the MagicMock-auto-attr → `str`/`UUID`-field 500 trap — same class as the W207 `replied_to=None` fix) + a new `test_returns_group_identity` assertion. **13 passed.**

---

## SW4 — ChatCreationService.create_group (`d89dba6a9`)

`feat(wave209-sw4-create-group-service)` — `app/core/config/storage.py` + `app/core/localization/dictionary.py` + `app/services/chat/creation_service.py` + NEW `tests/test_chat_creation_service.py` (3 tests).

- `StorageSettings`: `chat_group_min_members=3` / `chat_group_max_members=100`.
- 5 i18n keys (ru+en): `group_name_required`, `group_too_few_members`, `group_too_many_members`, `not_a_group`, `remove_forbidden` — **static** messages (the `raise_validation_error(key, locale)` path takes a key, not format kwargs; the bound values live in config + the message text).
- `create_group(user, name, participant_ids, locale)`: strip+validate name → dedupe + drop creator → enforce 3..100 → load members → `repository.create_group` → commit → the exact `create_chat:132-149` cache-invalidation + presence-hydration block (with the 3 new fields). **No Redis lock** (a group has no DM find-or-create uniqueness invariant). The existing-DM (`:111`) + new-DM (`:140`) `ChatResponse` builds also pass the 3 fields explicitly (W203-SW8 5-site discipline — defaults would suffice for DMs, but explicit is audit-checkable).
- **3 tests** (mocked repo/uow/cache; `create_group` itself is real-DB-tested in SW2): too-few-members + blank-name rejected before the repo is touched; happy path returns `chat_type="group"`. (Within-iter test-assertion fix: `assert_not_awaited` → `assert_not_called` — the never-reached `create_group` is a plain MagicMock, not AsyncMock; W138 L#1.)

---

## SW5 — ChatMaintenanceService member management + authz (`40559045f`)

`feat(wave209-sw5-member-management)` — `app/services/chat/command_service.py` + `tests/test_chat_command_service.py` (7 tests).

- `_require_group_participant(chat, user, locale)`: **authz-first** (403 `not_participant` BEFORE 400 `not_a_group` — deliberate deviation from the plan's order; a non-member must not learn a chat is a DM, and every existing maintenance method checks participant-first). Returns the pre-change roster for cache invalidation.
- `add_participant` (any participant) / `remove_participant` (owner via `created_by` OR self-leave; else 403 `remove_forbidden`) / `rename_chat` (any participant). Each: get_by_id → ensure_exists → group-authz → repo → commit. add/remove invalidate the chat-participant + presence-audience caches **after commit, gated on the repo's added/affected** (mirrors how `add_reaction` gates its broadcast on `is_new`) — the **security invariant**: `broadcast_to_chat` AND the ws-hub join-gate both read `chat:{id}:participants`, so a stale cache would lock a new member out / keep a removed one in. No live roster frame (FE refetches; G3 adds member-change frames). `rename_chat` does not invalidate (display-only, roster unchanged).
- `_mock_chat` parameterized with `chat_type`/`created_by`/`name`; `TestGroupMemberManagement` (7 cases: add-by-member, add-non-participant-403, add-on-DM-400, self-leave, non-owner-remove-403, owner-remove, rename). **32 passed** (the pinned `ruff-format` hook reformatted the test → re-staged + re-committed, the standard flow; no `--no-verify`).

---

## SW6 — API routes (`b540854a1`)

`feat(wave209-sw6-group-api-routes)` — `app/api/chat.py` + `tests/test_chat_api.py` (7 integration tests).

- `POST /chats/groups` (create_group, placed before the dynamic `/{chat_id}` routes — idiomatic static-before-dynamic); `POST /chats/{chat_id}/participants` (add); `DELETE /chats/{chat_id}/participants/{user_id}` (remove/leave); `PATCH /chats/{chat_id}` (rename). JSON-body (the Pydantic models, like `create_chat`), `{"status":"ok"}` returns, all `sensitive_route_limit`. **Path-distinct** from existing routes: `/groups` is a literal 1-segment; `participants` ≠ `messages`; `PATCH /{chat_id}` ≠ `PATCH /{chat_id}/messages/{message_id}`.
- **7 integration tests** (async_client): group create too-few (400) + happy (200, asserts chat_type/name/created_by/`participants==3` from the create RESPONSE); rename (200); add (200); owner-remove (200); DM-rejects-rename (400); non-owner-remove (403) + self-leave (200). **16 passed** (9 existing + 7 new).
- **LANDMINE (test-infra, not a route bug):** the trailing `GET /chats/{id}` verification I first wrote failed with `OperationalError` — `get_chat_details → get_unread_count → _set_rls_user` issues PostgreSQL `SET LOCAL app.current_user_id`, which SQLite rejects (the writes themselves all returned 200 in the logs). Fix (W138 L#1 within-iter): scope the integration tests to the **endpoint contract** (status + routing + authz) and let the **SW2 repo tests** own the DB-effect/count assertions — `GET /chats/{id}` is PostgreSQL-RLS-only.

---

## SW7 — Frontend api-client surface + unit tests (`e0968831c`)

`feat(wave209-sw7-fe-group-api-surface)` — `frontend/src/api/chat.ts` + `frontend/src/api/__tests__/chat.test.ts`.

- `Chat` type += **optional** `chat_type?: "dm"|"group"`, `name?`, `created_by?` (optional → existing DM consumers compile unchanged; the group-rendering UI that reads these is G4).
- `chatApi`: `createGroup(name, participantIds)` → `POST /chats/groups`; `addParticipant` → `POST /chats/{id}/participants`; `removeParticipant` → `DELETE /chats/{id}/participants/{userId}`; `renameChat` → `PATCH /chats/{id}`.
- **4 unit tests** — `src/api` is coverage-*included* → they hold the `npm run test:ci` functions ≥70% gate (W198/W207 lesson). **19 passed** (15 existing + 4 new); tsc 0.

---

## SW8 — Full verification (W203 §H#5)

- **OpenAPI contract** `tests/contracts/test_openapi_contract.py` → **8 passed** (the new routes + ChatResponse fields are additions → superset holds, no snapshot regen — W205 gotcha).
- **SINGLE FULL** `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py` → **2975 passed / 25 skipped / 0 failed (3m01s)**. Reconciles exactly: W208 baseline **2952** + 23 new W209 tests (5 SW2 repo + 1 SW3 query + 3 SW4 creation + 7 SW5 command + 7 SW6 API) = **2975**. The matching arithmetic is itself a no-cascade signal (W205 §H#5). (pact-python ws-hub contract ignored — Windows DLL.)
- **FE:** `npm run lint` clean (`--max-warnings=0`); `npm run test:ci` **EXIT=0, functions 70.45% ≥ 70%**, lines 79.31%, 166 test files (1375 tests = 1371 W208 + 4 SW7); `npm run build` × 3 **BYTE-IDENTICAL** — main `index-BNy-Fnph.js` **180,268 b** sha `c4eabf25fc0b90f77ffdec1b9e8094e5542df92ac0d1a3b9ab1d84c7b146f4a6` × 3 + server.js **24,024 b** sha `d4911fbebcd46ddce101eeb20025e1181cbb7f1278f12be6f13a9ebb92a8e65f` × 3.
- **Bundle framing (honest):** main JS SIZE is **identical to W208** (180,268 b) but the content **hash shifted** (W208 `index-DBZkEBwc.js` `002d7c1a…` → W209 `index-BNy-Fnph.js` `c4eabf25…`); `chat.ts` lives in the messenger route-lazy chunk, so the main-entry size is stable while its content hash flips because it references the rehashed chunk (W193 SW5 / W202 module-graph behavior). server.js same size, different sha (SSR module graph references the new `chat.ts` surface). **NOT byte-identical to W208** — expected for real FE client-tree code, not a regression. Tree-shake invariant ✓ (0 `lhci-mock-user` in PROD); SW IIFE ✓ (`"use strict";(()=>{`).

---

## Gates (end-of-wave)

| Gate | Result |
|------|--------|
| `python -m py_compile` (model + migration) | OK |
| `uv run alembic` up/down/up + heads (live PG) | single head `202605300005`, reversible, idempotent |
| `uv run ruff check` (per-SW) | All checks passed |
| Backend full `uv run pytest --ignore=…ws_hub_contract` | **2975 passed / 25 skipped / 0 failed** (2952 + 23) |
| OpenAPI contract | 8 passed (superset, no regen) |
| `npx tsc --noEmit` (FE) | 0 |
| `npm run lint` (`--max-warnings=0`) | 0 |
| `npm run test:ci` (coverage) | EXIT=0, **functions 70.45% ≥ 70%**, lines 79.31%; 1375 tests |
| `npm run build` × 3 | BYTE-IDENTICAL (main `c4eabf25…` + server `d4911fbe…`) |
| Tree-shake / SW IIFE | 0 `lhci-mock-user` in PROD; `"use strict";(()=>{` |
| husky pre-commit (every commit) | clean — NO `--no-verify` |

---

## §Honesty (0-3 OPEN — carry-forward + new)

- **Carry-forward:** `live-in-DEV-only` (prod has no ws-hub/NATS — deferred by the user) + W134 §H#2 (bundle-delta recording-only) + W134 §H#10 (/messenger Phase 5 SSR `ssr: 'data-only'` by-design).
- **NEW G1 deferrals (honest, by-design — not defects):** per-recipient read receipts (G2) — groups inherit the per-message global read state as a documented limitation; the `get_chats` unread CTE will under-count for >2 parties. Group notification re-tiering (G3) — `notify_new_message` + the W208 reply-supersede assume 2 parties; also group push fan-out won't fire (the synchronous notify is commented out, push is outbox-driven). Live WS member-change frames + group UI (G4). Removing below min-3 via removes is allowed (min is create-time only) — an empty/1-person group just sits there (auto-delete-empty is a later refinement).
- **NEW G1 test-infra note:** `GET /chats/{id}` (get_unread_count → `SET LOCAL` RLS) is PostgreSQL-only → not integration-testable on the SQLite test DB; the SW6 integration tests assert endpoint contracts (status/routing/authz) and the SW2 repo tests own the DB-effect/count assertions.
- **Live Docker verification opportunistic:** the SW1 alembic cycle ran against the real dev PG; the SW6 pytest integration tests (`test_chat_api` via `async_client`) ARE the primary endpoint verification — no warm full stack needed. A two-account browser smoke of the create-group flow through the real Caddy → backend chain was NOT performed (the group UI is G4 — there's nothing user-facing to drive yet; per `feedback_perfectionism.md`, deferred honestly rather than faked).

---

## (z) discoveries & anti-patterns

**0 NEW (z) discoveries from SW execution proper.** Phase 1 Explore (3 parallel agents) + Phase 3 verify-before-write + the Plan agent resolved the load-bearing unknowns *before* any edit — the `chat_participants`-is-already-M2M finding, the 5-site `ChatResponse` fan-out, the `ChatDTO` gatekeeper, the MagicMock `extra="forbid"` trap, the `pg_insert`-can't-run-on-SQLite constraint, and the `_set_rls_user` RLS-on-SQLite constraint were all anticipated or caught at the gate (W141 #3). The within-iter sub-fixes (SW2 Python `default="dm"`, SW2 `add_participant` dialect-agnostic pivot, SW4 `assert_not_called`, SW6 GET-removal) are all SAME-mechanism corrections per W138 L#1, not (z) cascades. Extends the low-(z) streak (W145-W209).

**0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

**W141 compliance:** #1 — every SW landed 1-iter; the within-iter sub-fixes are SAME-mechanism (W138 L#1), no mechanism pivots. #3 — Phase 3 + the Plan agent caught the M2M-already-exists fact, the 5-site rule, the gatekeeper, the SQLite `pg_insert`/RLS constraints, and the `raise_forbidden(locale, key)` vs `raise_validation_error(key, locale)` opposite-arg-order before each edit. #4 — every "passed/GREEN" attributed only after captured gate output (alembic cycle, 2975 pytest, test:ci EXIT=0 + 70.45% functions, Build × 3 sha); the group-UI live smoke honestly NOT claimed (deferred to G4). #15 — all 8 commits fired the husky chain cleanly (SW5 ruff-format re-stage is the documented flow), NO `--no-verify`.

---

## NEW Gotchas (added to CLAUDE.md)

1. **`chat_type` String-not-StrEnum + dual default** — a closed display discriminator mirrors `Attachment.file_type`; the Python `default="dm"` alongside `server_default="dm"` is load-bearing for the DM `_to_dto` path (server-default-only column is expired post-INSERT → sync pydantic read → MissingGreenlet).
2. **`ChatResponse` is a 5-site fan-out** (the W203-SW8 rule generalized) — 4 explicit builds + 1 `model_dump` spread; `ChatDTO` is the silent gatekeeper; a missed site renders a group as a nameless DM with no error.
3. **`add_participant` dialect-agnostic check-then-insert** — `pg_insert.on_conflict_do_nothing` can't compile on the SQLite test DB (why W206 reaction tests are mock-only); the SELECT-then-INSERT makes the full path real-DB-testable. PK is the uniqueness backstop.
4. **Member-change cache invalidation is a security invariant** — `broadcast_to_chat` + the ws-hub join-gate both read `chat:{id}:participants`; add/remove must invalidate after commit (gated on added/affected).
5. **`GET /chats/{id}` is PostgreSQL-RLS-only** — `get_unread_count → _set_rls_user` issues `SET LOCAL`, which SQLite rejects; chat-detail read-backs aren't integration-testable on the SQLite test DB (assert endpoint contracts + own DB effects in repo tests).

---

## Messenger arc & next

W203 read receipts → W204 live bridge → W205 new_message + edit/delete → W206 reactions → W207 reply/quote + reactor-list + typing → W208 reply notifications + cleanup + message-list polish → **W209 group-chat backend foundation (G1)**.

**W210+ candidates:** **G2** per-recipient read receipts (`ChatReadReceipt` — fixes group unread + improves DMs) + group notification re-tiering; **G4** group UI (create-group modal, member management, group name/avatar rendering, name-fallback in `MessengerContext`/`useMessengerController`); then Track **A** (attachment perfection), **S** (pgvector message search), **F** (forwarding). Prod ws-hub + NATS deploy (closes `live-in-DEV-only` across W203-W209) remains user-deferred.

Memory references (`.claude` profile): `memory/wave209_backlog.md`, `memory/wave210_opening_prompt.md`.
