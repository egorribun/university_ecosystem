# Wave 205 — `new_message` LIVE (A) + message edit/soft-delete LIVE (B)

**Date:** 2026-05-31 · **Branch:** `egorribun` (PR #1126) · **Status:** ✅ CLOSED — both deliverables verified LIVE in the dev Docker chain · **65th consecutive wave** (brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 anti-pattern discipline)

## Headline

User chose **A + B(edit/delete)** (2 AskUserQuestion rounds): **A** = fix the dev outbox so `new_message` goes live (closing W204 §Honesty); **B** = ship message **edit + soft-delete** as a synchronous-broadcast feature (the `mark_read` pattern) that flips live via the W204 bridge. For the A-fix scope the user chose **B — Central fix** (repair the capture mechanism in `app/core/events.py` to restore the ENTIRE domain-event subsystem, which was systemically broken — `stored_events` empty for ALL aggregate types in W204).

**Both delivered + PROVEN LIVE cross-user in the dev Docker chain** (real Caddy → SSR → backend → NATS → ws-hub → browser; userA in a real Chrome session via chrome-devtools-mcp, userB via curl):

- **new_message LIVE** ✅ — userB sends → userA's chat goes **9 → 10 bubbles** with the new message appearing instantly, **NO refetch** (exactly one initial `GET /messages` in the network trace). **Closes the W204 §Honesty new_message-live gap.**
- **edit LIVE** ✅ — userB edits → userA's received bubble flips to the edited content + the **"(изменено)"** label, no refetch.
- **delete LIVE** ✅ — userB soft-deletes → userA's bubble becomes the **"Сообщение удалено"** tombstone (content + label dropped), no refetch.

The A goal was NOT a one-line capture fix: the SW-A central fix **restored the domain-event subsystem and thereby ran the full producer→broadcast→browser chain end-to-end for the first time in many waves**, which surfaced a cascade of **dormant downstream bugs** — each fixed in SW9 as live verification exposed it (the W203 §H#5 "central change surfaces a latent bug" class, repeatedly).

## SW breakdown (12 commits)

| SW | Commit | What |
|----|--------|------|
| SW-A | `465587cf1` | **Central capture fix** — `capture_on_commit` before_commit catch-all in `app/core/events.py` + `_event_emitters` tracking in `record_event`. Restores domain-event capture: `stored_events` was systemically EMPTY (W204); now `chat.message_sent` is captured + the reactive OutboxWorker processes it (`processed_at` set). |
| SW2 | `0339fc116` | `Message.edited_at` + `Message.deleted_at` nullable columns + alembic `202605300002` (idempotent `_table_exists`/`_column_exists` guards, down_revision `202605300001`). |
| SW3 | `32b01ac5d` | Repo `edit_message`/`soft_delete_message` (author-only WHERE, `utc_now()`, soft-delete clears `content=""` — D1) + `ChatMaintenanceService` synchronous broadcast (mark_read pattern: participant check → commit → gated `affected>0` `broadcast_to_chat` of `message_edited`/`message_deleted`; 404-before-commit on `affected==0`). |
| SW4 | `06409e993` | `MessageResponse`/`MessageDTO`/`serialize_message` `edited_at`/`deleted_at` + every field-by-field `MessageResponse(...)` site (W203 SW8 gotcha) + PATCH/DELETE `/chats/{id}/messages/{mid}` routes + `tests/test_wave205_edit_delete.py` (8). |
| SW5 | `7395e3eb3` | FE API `Message` + `types.gen.ts` + Valibot `MessageEditedSchema`/`MessageDeletedSchema` (+5 tests) + `useChatWebSocket` `applyMessageEditedFrame`/`applyMessageDeletedFrame` + cases. Preserved the W202 SW2 `as Message` cast. |
| SW6 | `8c9b184a2` | Controller `editMessageMutation`/`deleteMessageMutation` (optimistic onMutate/onError/onSettled) + handlers + transform (editedAt/editedAtLabel/deletedAt) + ChatWindow 3-state bubble (tombstone / inline editor / normal + own-message affordance + "(edited)" label) + ChatArea/MessengerFeature threading + i18n EN+RU (7 keys, no defaultValue). PRESERVED W202 SW6b `animateFromIndex` + W202 polish-v1 `key={selectedChatId}`. |
| SW7 | `7d67623ab` | ChatWindow.test.tsx +11 (affordance/tombstone/editor) + useMessengerController.test.tsx +8 (optimistic snapshot/rollback for edit + delete). |
| SW9 | `63009476d` `f00e6cc16` `555bca22f` `42b137794` `38671416c` | Close — full-suite gates + **the 4-bug cascade the A-fix exposed** (below) + live verification + audit/rotation/memory. |

### The SW9 cascade — 4 latent bugs the SW-A central fix exposed end-to-end (all FIXED, none deferred)

1. **`63009476d` serialize_message test stand-in** (test-only) — the full backend suite (W203 §H#5: NOT a slice) caught `test_chat_helpers.py` failing: SW4's `serialize_message` reads `message.edited_at`/`.deleted_at`, but the `_serializable_message` SimpleNamespace stand-in lacked them → AttributeError. Added the 2 fields.
2. **`f00e6cc16` `handle_message_sent` sender=None** (product, blocked new_message broadcast) — surfaced by live verification: the OutboxWorker handler passed `sender=message.sender`, but `message` came from `db.get(Message, id)` and `Message.sender` is `lazy="noload"` (N+1 guard) → `message.sender` is None → `notify_new_message` crashed on `sender.id`. Dormant for waves (the W204 outbox produced zero events). Fix: fetch sender via `db.get(models.User, message.sender_id)` + None-guard + a NEW regression test (the handler was previously UNTESTED — why it stayed dormant).
3. **`555bca22f` `MessageResponse.content` min_length** (product, blocked GET /messages) — surfaced by live verification: GET /messages 500'd (pydantic `string_too_short`) the moment a chat held a soft-deleted message, because `MessageResponse` inherited `MessageBase.content`'s `min_length=1` but the D1 tombstone has `content=""`. Fix: override `content: str = Field(..., max_length=2000)` (keeps content REQUIRED, drops only the min floor; `MessageCreate` + the Form `min_length=1` keep input strict) + 2 NEW tombstone tests (the SW4 serialize tests used SimpleNamespace, never the real pydantic model).
4. **`38671416c` `sender: null` frontend schema** (product, the FINAL new_message-live blocker) — surfaced by live verification (`[ws] Invalid frame dropped`, size 578): the new_message frame REACHED the browser (the bridge works for new_message too) but `parseWsMessage` Valibot REJECTED it. `serialize_message` emits `"sender": null` (noload), and `MessageSchema.sender` was `v.optional(v.record(...))` which accepts `undefined` but **rejects `null`**. Fix (frontend, critical): `sender: v.optional(v.nullable(v.record(...)))` + declared `edited_at`/`deleted_at` optional+nullable (the frame carries them) + 3 NEW tests. Fix (backend, UX): `handle_message_sent` reassigns `message.sender = sender` so the live bubble shows the sender's name/avatar.
   - **`42b137794` OpenAPI snapshot regen** — the W205 contract additions (read_at W203 + edited_at/deleted_at + edit/delete routes) passed the superset check as additions, but the `MessageResponse.content` min_length REMOVAL broke the superset → regenerated `tests/contracts/snapshots/api_openapi_v1.json` (net 185 insertions + 1 deletion = the minLength). The 24K-line first attempt was a Windows CRLF-vs-LF write artifact; the real diff is W205-scoped.

## Live verification matrix (dev Docker chain, final fully-fixed stack)

| Item | Method | Result |
|------|--------|--------|
| SW-A outbox capture | curl send → `psql stored_events` | `Message\|chat.message_sent` **processed=t** (was EMPTY all-types in W204) |
| `handle_message_sent` no-crash | backend logs | `Domain event: chat.message_sent` fires with **NO error** (vs the earlier NoneType crash) |
| MessageResponse content="" | reload → GET /messages | **200**, deleted message renders as "Сообщение удалено" tombstone (was 500) |
| **new_message LIVE** | userB curl send → userA DOM + network | **9→10 bubbles**, "W205-LIVE-PROOF" appears live, **exactly 1 `GET /messages`** (no refetch) |
| **edit LIVE** | userB curl PATCH → userA DOM | content flips to "W205-EDITED-FINAL" + "(изменено)" label, no refetch |
| **delete LIVE** | userB curl DELETE → userA DOM | "Сообщение удалено" tombstone, content+label dropped, no refetch |
| WS isolation | edit-probe vs new_message | the synchronous edit-probe reached userA's same WS connection live → isolated the new_message gap to the frame SCHEMA (not WS/join/bridge/handler) |

Creds: `test@university.dev` (userA, browser) + `w203reader@university.dev` (userB, curl), both `TestPass@2024x`. Temp cookie jar deleted post-verification.

## Gates (end-of-wave)

- tsc 0 · `npm run lint` 0 · i18n parity 18/18 · `npm audit --omit=dev` **0** (raw 4 high = the documented dev-only `@lhci/cli` cascade, allowlisted since W191, exp 2026-08-31)
- frontend vitest **1335 passed / 12 skipped / 0 failed** (serial — Windows IPC flake W187)
- backend pytest **FULL suite 2920 → 2923 passed / 25 skipped / 0 failed** (W203 §H#5 — not a slice; `--ignore=tests/contracts/test_ws_hub_contract.py` for the pact-python Windows DLL; +3 from the polish-pass SW-A capture regression below)
- alembic up/down/up idempotent (`202605300002` ↔ `202605300001`)
- **Build × 3 BYTE-IDENTICAL** — main JS `index-D517gUte.js` **180,273 b** sha `db4af26258816356e2caf0a0a52687bd13d6d328a5af789fd40582e91a6dcafe` × 3 + server.js **24,024 b** sha `7b0dfc08958596826fe680aa92d974218d822913c7f2710f9945b1a813d808c4` × 3. **Size UNCHANGED from W204; content-sha CHANGED** (SW5/SW6/SW9 edit-delete + sender:null code lives in the route-lazy `Messenger-*.js` chunk — the W193 SW5/W202 module-graph behavior). NEW W205 baseline; the W134-SW3→W204 content-sha invariant retired at W202.
- tree-shake ✓ (0 `lhci-mock-user` in PROD) · SW IIFE ✓ · React Compiler Babel build-gate ✓ (the SW6 ChatWindow animate boundary compiles)

## §Honesty (0-3 OPEN)

- **CLOSED**: W204 §Honesty new_message-live gap (the headline) — new_message now flips live in dev.
- **OPEN (carry-forward, structural / by-design)**:
  1. **Live in DEV only** — ws-hub is absent from the prod compose + k8s manifests; prod self-heals via refetch. A prod ws-hub deploy is a separate infra wave. (W204 carry, now more prominent since new_message is the feature.)
  2. **W134 §H#2** bundle-delta recording-only + **W134 §H#10** /messenger Phase 5 SSR by-design (W161 SW2).
  3. **typing** deferred (the plan recommended deferring it — ws-hub's relay does no send-side room-membership check; a focused secure follow-up).
- **Characterization-only caveats (not product issues)**: the `navigate_page initScript` WS-frame capturer (`window.__wsFrames`) captured 0 frames — this app's WS frame-read path isn't intercepted by the prototype `addEventListener`/`onmessage` wrap — so the live verification used **DOM + network-trace** evidence (which is the user-visible ground truth) instead of raw-frame capture; multi-tab same-user self-echo is user-level (a 2nd tab of the author won't live-show its own edit; self-heals).

## (z) discoveries — 4 NEW, ALL FIXED (none deferred)

The SW-A central fix's value: it ran the producer→broadcast→browser chain end-to-end for the first time in many waves, surfacing 4 dormant downstream bugs — (z)#1 serialize_message test stand-in (test-only), (z)#2 `handle_message_sent` noload-sender crash, (z)#3 `MessageResponse.content` min_length vs the empty tombstone, (z)#4 frontend `MessageSchema.sender` rejecting `null`. Each was caught by the discipline (full-suite gate + live verification) and FIXED in SW9 — a textbook W203 §H#5 cascade. **0 NEW anti-patterns.**

## W141 anti-pattern compliance

- **#1** (each SW landed 1-iter; the 4 SW9 fixes are within-SW9 SAME-mechanism sub-fixes per W138 L#1 — making the chosen A deliverable actually work end-to-end, NOT mechanism pivots; new_message-live was NOT deferred — the cascade was followed to completion because each bug was bounded ≤1 fix).
- **#3** (verify-before-write: the noload-sender root cause, the content min_length, and the sender:null Valibot rejection were each diagnosed from logs/source BEFORE the fix; the OpenAPI 24K diff was disproved as a CRLF artifact before regenerating).
- **#4** ("PROVEN live" attributed ONLY after the captured DOM + network evidence — `9→10 bubbles` + exactly-1 GET /messages; new_message-live was NOT claimed until the W205-LIVE-PROOF frame rendered; "wave complete" waits for CI green).
- **#15** (all 12 commits fired the husky chain cleanly; the ruff-format reformat re-stage on `f00e6cc16` followed the documented re-stage pattern, NO `--no-verify`).

## Polish-pass (post «безупречно?» self-audit)

Commit `8600ef58d` `test(wave205-polish-sw-a-capture-regression)`. The self-audit cross-checked every audit claim against source/git and **all substantive claims held** — test counts accurate (`test_wave205_edit_delete.py` = 10 = SW4 8 + SW9 2), design decisions honored (**D1** query_service passes `deleted_at` through but never filters `WHERE deleted_at IS NULL` → tombstones returned; **D3** new_message/read have self-echo guards at useChatWebSocket.ts:390/490, message_edited/message_deleted at 506/522 deliberately do NOT — idempotent cache update absorbs the echo; **D5** PATCH+DELETE both `return {"status": "ok"}`), no leaked SW1 temp diagnostic logging in `events.py`, and tsc 0 / lint 0 / i18n 18/18 re-verified fresh.

It surfaced **one genuine gap**: the wave's HEADLINE fix (SW-A `capture_on_commit` + `_event_emitters` tracking) had a regression test for its DOWNSTREAM consumer (`handle_message_sent`, `test_chat_helpers.py`) but **NONE for the PRODUCER** — the capture mechanism that writes the StoredEvent. A future refactor dropping the `before_commit` listener / the `_event_emitters` scan / `record_event`'s session tracking would silently re-break the entire outbox (the exact W204 state — `stored_events` empty for all aggregate types) with no test failing. The plan's SW8 said "add a regression test if tractable"; the cascade chase landed the consumer test but not the producer test.

**Closed** with NEW `tests/test_wave205_outbox_capture_regression.py` (3 tests): (1) **gold integration** — reproduces the exact production trigger end-to-end via `db_session` + the minimal `News` aggregate (flush → record `MessageSent` AFTER flush → commit with no further flush) through the real `record_event` `_event_emitters` tracking + the `before_commit` listener + real StoredEvent persistence; asserts exactly 1 `chat.message_sent` outbox row; (2) **wiring guard** via `sa_event.contains` for all 3 listeners; (3) **idempotency** unit test (FakeSession: after_flush capture then before_commit catch-all → exactly one StoredEvent). **DISPROVE-verified** (the gold-standard rigor): neutering the `before_commit` registration turns BOTH the integration + wiring tests RED → genuine guard, not a tautology; `events.py` reverted clean afterward. FULL backend suite **2923 passed / 25 skipped / 0 failed** (the global `register_event_listeners()` call causes zero test-ordering pollution — W203 §H#5 full-suite verification). No production code change.

## Messenger arc

W203 read receipts (self-heal) → W204 live WS bridge (read proven live; new_message verified-by-construction) → **W205: new_message LIVE (gap closed) + edit/delete LIVE**. W206+ candidates: prod ws-hub deploy (lifts the live-in-DEV-only caveat); live typing (secure send-side membership follow-up); reactions / voice messages; `mark_single_message_read` dead-code cleanup (W203 carry).
