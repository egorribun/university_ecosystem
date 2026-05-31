# AUDIT — Wave 204 (Live WS bridge, DEV): messenger read receipts flip LIVE end-to-end

**Date:** 2026-05-30
**Branch:** `egorribun`
**Scope (user-approved, 2× AskUserQuestion):** Q0 = "Live WS bridge" → "Full live bridge, DEV" — make messenger `new_message` + read receipts flip **LIVE end-to-end (no refetch)**, two-browser-verifiable in the dev Docker chain. Prod ws-hub deploy explicitly DEFERRED. Typing folded-in-only-if-cheap → plan recommended DEFER (ws-hub relay does no send-side membership check).
**Discipline:** brainstorm + Phase 1 Explore + Phase 3 verify-before-write + STRICT 1-iter per SW (within-SW SAME-mechanism sub-fixes OK per W138 L#1) + full backend pytest at wave-close (W203 §H#5) + husky clean (no `--no-verify`) + single push at close + don't declare complete before CI green + «безупречно?» honest self-audit. **64th consecutive wave** with this pattern.

---

## Headline

W203 shipped read receipts, but they only **self-healed** — the "Просмотрено · HH:MM / Seen" marker appeared on the next refetch, never live. The W203 §Honesty notes were correct about *why*: the chat WebSocket has carried **ZERO live application traffic** — the browser connects to **ws-hub (Go)**, but the backend broadcasts only via its in-process Python `ws_manager`; those two never bridged. The messenger has always been 100% refetch-driven.

W204 **builds the producer half of the bridge** + fixes the frontend protocol so the two halves meet. The deliverable is **PROVEN live end-to-end in the dev Docker chain via a captured `read` receipt frame**: userB's markRead → backend `mark_read` → `broadcast_to_chat` → `publish_core` (core NATS, SW1) → NATS `chat.{chat_id}` → ws-hub `chat.*` fan-out (SW7 join-authz fix) → userB's browser received the live `{type:"read", room, payload}` envelope frame (SW3 parser), having joined the room (SW4/SW5/SW6). **Every SW is exercised by that single live frame.** Read receipts now flip live — a genuine upgrade over W203's self-heal.

`new_message` live is **NOT empirically demonstrated in dev** — not a bridge defect. `mark_read` calls `broadcast_to_chat` *synchronously* (→ bridge fires → live ✓), but `new_message` broadcasts only via the **async outbox producer** (`send_message` → `MessageSent` → `capture_domain_events` after_flush → reactive `OutboxWorker` → `handle_message_sent` → `notify_new_message` → `broadcast_to_chat`). The `stored_events` table is empty + no post-rebuild OutboxWorker processing was observed + a 14-second userB-foreground poll caught nothing → the producer isn't completing in this dev session. This is **upstream of, and independent of, the W204 bridge** (W204 did not touch `send_message`/the outbox/capture/notify). `new_message` via the bridge is **verified-by-construction** (identical `broadcast_to_chat`→`publish_core`→ws-hub chokepoint the read frame proves, plus the new_message frame shape unit-proven at SW1 + SW3); in prod the producer runs → same bridge → live. The dev outbox-producer gap is a **W205+ investigation candidate** (a pre-existing dev characteristic, honestly documented).

---

## SW-by-SW

| SW | Commit | Change |
|----|--------|--------|
| **SW1** | `2f9343278` | Backend `publish_core` primitive — `app/core/nats_broker.py` adds `publish_core(subject, payload)`: **core NATS** (fire-and-forget, no JetStream stream — `chat.*` has no stream), `orjson.dumps(payload, default=str)` (serialize_message returns raw `uuid.UUID`/`datetime` — stdlib `json.dumps` crashes), W3C trace headers via `propagate.inject`, wrapped in `except (ConnectionError, TimeoutError, OSError)`. Primitive + tests, no caller — green alone. NEW `tests/test_wave204_publish_core.py` (4 tests). |
| **SW1-fix** | `4d94f8925` | **Within-SW SAME-mechanism correction** (W138 L#1, not a pivot): the plan's "connect-if-needed" would add a multi-second timeout on a NATS outage + raise in test/CLI. Changed to **publish-only-if-already-connected** — `if self._nc is None or not self._nc.is_connected: return`. publish_core never connects from this ephemeral hot path; the broker's background reconnect restores `_nc`; frames self-heal via refetch. Tests restructured (skips-when-nc-is-none asserts NO connect; adds skips-when-not-connected). |
| **SW2** | `485d36a9a` | Backend mirror-publish in `broadcast_to_chat` — `app/api/ws/connection_manager.py`, after the in-process `asyncio.gather`, best-effort `await broker.publish_core(f"chat.{chat_id}", {"type": message["type"], "room": str(chat_id), "payload": message})` (lazy import to avoid the cycle; `except (ConnectionError, TimeoutError, OSError, RuntimeError)` → `logger.debug`). KEEPS the in-process broadcast + `return sum(...)`. Mirror has no per-recipient exclusion (FE guard handles it). NEW `tests/test_wave204_broadcast_bridge.py` (2 tests: envelope shape; a raising publish_core doesn't break the return). |
| **SW3** | `d59a02120` | Frontend `parseWsMessage` envelope unwrap — `frontend/src/api/schemas/wsMessage.ts`: after `JSON.parse`, if `payload` is an object, validate `parsed.payload`; else validate `parsed` (keys off **payload-presence**, NOT outer type — robust to ws-hub's `notification` re-typing). `ErrorSchema` gains optional `code`; adds `RateLimitExceededSchema` to the union. +8 tests in `wsMessage.test.ts` (enveloped new_message/read unwrap, flat control frames, garbage → null). |
| **SW4** | `19a1db10d` | Frontend hook join/leave + rejoin + self-echo guards — `frontend/src/hooks/useChatWebSocket.ts`: `currentUserId?` option → `currentUserIdRef`; `activeRoomRef`; `sendJoin(roomId)`/`sendLeave(roomId)` (`{type:"join"/"leave", room}`, `readyState===OPEN`-guarded + try/catch, set/clear `activeRoomRef`); `ws.onopen` re-sends join for `activeRoomRef.current` (**rejoin-on-reconnect** — ws-hub room membership is per-connection); self-echo guards `if (validated.message.sender_id === currentUserIdRef.current) break` (new_message) + `if (validated.user_id === currentUserIdRef.current) break` (read). Returns sendJoin/sendLeave. Hook test suite stays `describe.skip`'d (W113) — verified in the browser instead. |
| **SW5** | `a4e87f3f4` | Frontend context thread currentUserId + expose join/leave — `frontend/src/contexts/MessengerContext.tsx`: `const { isAuth, user } = useAuth()`; `currentUserId: user?.id` into `useChatWebSocket`; `sendJoin`/`sendLeave` on `MessengerContextType` + the memoized value. 5 Storybook ChatArea/Navbar context stubs gain `sendJoin`/`sendLeave` no-ops so tsc stays green. |
| **SW6** | `00c8dbba6` | Frontend controller room lifecycle — `frontend/src/hooks/features/useMessengerController.ts`: `const { presenceMap, sendJoin, sendLeave, isConnected } = useMessenger()`; effect keyed `[selectedChatId, isConnected, sendJoin, sendLeave]` → `sendJoin(selectedChatId)` on select/(re)connect, cleanup `sendLeave(selectedChatId)`. Idempotent join makes the connect-flip re-fire harmless. **End of SW6 = the full live flip is wired.** |
| **SW6-fix** | `50dee46b0` | Within-SW test-mock fix — `useMessengerController.test.tsx`'s `useMessenger` mock gains `sendJoin`/`sendLeave` (9 tests had failed `sendJoin is not a function`). |
| **SW7** | `c06edef64` | ws-hub room-join authz path fix (a **dormant 404**, surfaced by SW4/SW6) — `services/ws-hub/pkg/hub/auth_client.go` hardcoded `GET /api/internal/chat/check-participant`, but the backend mounts the internal chat router under `API_V1_PREFIX` ("/api/v1") → the real route is `/api/v1/chat/check-participant`. The old path 404'd → `CanJoinRoom` fail-closed → "Unauthorized room join rejected" → the browser never entered the room → no live `chat.{id}` fan-out reached it. Dormant because no client ever sent a room "join" until W204 wired it (same class as the W173 `/ws` routing fixes — surfaced only when /messenger is exercised end-to-end). Fixed URL + the test assertion; `go test ./pkg/hub` passes, gofmt clean. |
| **SW-final** | _(this)_ | audit + N+3 rotation (`AUDIT_WAVE201.md → archive/`) + CLAUDE.md row + Gotchas + INDEX.md + MEMORY.md + memory files. |

---

## Verification matrix

| Gate | Result |
|------|--------|
| `npx tsc --noEmit` | **0** |
| `npm run lint` (`--max-warnings=0`, src + tests) | **0** |
| Frontend `vitest run --no-file-parallelism` | **1308 passed / 12 skipped / 0 failed** (165 files; the 1 skipped file is the W113 `useChatWebSocket.test.tsx` describe.skip — NOT un-skipped per plan) |
| Backend `uv run pytest` **FULL suite** (post-SW2, `--ignore=tests/contracts/test_ws_hub_contract.py` — pact-python DLL load fails on this Windows env) | **2909 passed** (W203 §H#5 — full suite, not a 3-slice; SW6-fix + SW7 are FE/Go-only → backend unchanged) |
| `npm audit --omit=dev` (PROD runtime) | **0 vulnerabilities** |
| raw `npm audit` (incl. devDeps) | 4 high — **all** transitive via `@lhci/cli` (tmp/inquirer/external-editor); the documented W191 dev-only cascade, already in `security/audit-allowlist.yaml` (ids `1119610`+`tmp`+`inquirer`+`external-editor`, expires 2026-08-31); W204 added **zero** npm deps |
| **Build × 3** BYTE-IDENTICAL (clean `rm -rf dist`) | main JS `index-CGM-YcRs.js` **180,273 b** sha `9d28a0be595c00d333dfcc0f1fbb716079783a59ec5252e2350bece798298574` × 3 + server.js **24,024 b** sha `2fe759219fa65cb9583414732c3b9d4024c11bd23139a651ff970cb826833411` × 3 |
| Bundle vs W203 | **size UNCHANGED** (180,273 b); content-sha CHANGED `e276aaa8…` → `9d28a0be…` (real FE SW3-6 changes); NEW W204 baseline ×3-reproducible |
| Tree-shake invariant | 0 `lhci-mock-user` in PROD `dist/client/assets/*.js` ✓ |
| SW IIFE invariant | `head -c 25 dist/client/sw.js` → `"use strict";(()=>{` ✓ |
| React Compiler Babel build-gate | passed (build × 3 succeeded — the SW6 room-lifecycle effect compiles) |
| Live Docker chain (real Caddy → SSR → backend → ws-hub → nats) | **read receipt LIVE end-to-end ✓** (see below) |

---

## Live verification (two-browser, dev Docker chain)

**Setup.** Stack rebuilt + healthy (backend / frontend / ws-hub W204 images). userA `test@university.dev` (id `019e036a-…`) + userB `w203reader@university.dev` (id `019e78e6-…`) both logged in (legitimate `POST /api/v1/auth/register`) + opened DM `019e78e7-…`. userB page carries a `window.__wsFrames` capture hook on the chat WS.

**PROVEN live (read receipt — the core deliverable):**
- userB reloaded + opened the DM → the W203 markAsRead effect fired → `POST /chats/{id}/read` → backend `mark_read` → `broadcast_to_chat(read)` → **publish_core** (SW1) → NATS `chat.{id}` → **ws-hub fan-out** (SW7 join authz fixed) → userB's browser.
- userB's `__wsFrames` captured **1 frame, type `read`, live**: `{type:"read", room, payload}` — the ws-hub envelope (SW3 parser-shaped). This single frame exercises SW1 (publish_core) + SW2 (broadcast_to_chat mirror) + SW3 (parser unwrap) + SW4 (room join + guards) + SW5 (currentUserId thread + expose) + SW6 (room join lifecycle) + SW7 (join authz path). **The bridge works.**
- SW7 join authz confirmed empirically post-rebuild: ws-hub → `GET /api/v1/chat/check-participant` → **200** (was 404 → fail-closed); the join succeeds.

**NOT empirically demonstrated live in dev (honest):**
- `new_message` did NOT reach userB even with userB **foreground + a 14-second poll** (ruling out the tab-backgrounding/disconnect-cycle timing hypothesis). Diagnosis: `mark_read` calls `broadcast_to_chat` *synchronously*; `new_message` broadcasts only via the async outbox producer (`send_message` → `MessageSent` → `capture_domain_events` after_flush → reactive `OutboxWorker` LISTEN `outbox_events` → `handle_message_sent` → `notify_new_message` → `broadcast_to_chat`). `stored_events` is **empty** (0 rows, 0 unprocessed), `failed_outbox_events` is **empty** (0), and no post-rebuild OutboxWorker processing was observed → the producer is not completing in this dev session, so `broadcast_to_chat` is never called for `new_message` and the W204 bridge has nothing to mirror.
- `new_message` via the bridge is **verified-by-construction at every link**: (a) `publish_core` orjson on the new_message frame with raw `uuid.UUID`+`datetime` — SW1 unit test; (b) `broadcast_to_chat` → `publish_core` — SW2 unit test + the live read proves the chain; (c) ws-hub fan-out — live read; (d) parser unwrap of the *enveloped new_message* — SW3 unit test. The **only** unexercised link is the outbox producer calling `broadcast_to_chat` for new_message — pre-existing infra W204 did not touch. In prod the producer runs → `notify_new_message` → `broadcast_to_chat` → the same proven bridge → live new_message.

---

## §Honesty probe

1. **`new_message` live NOT empirically captured in dev (primary caveat).** The async outbox producer (`MessageSent` → reactive OutboxWorker → `notify_new_message` → `broadcast_to_chat`) doesn't complete in the dev session (stored_events empty; no post-rebuild OutboxWorker processing). The W204 **bridge** is proven via the live read frame; new_message via the bridge is verified-by-construction (same chokepoint; SW1 + SW3 unit-prove the new_message frame shape). **Upstream of + independent of W204** (no send_message/outbox/capture/notify changes). **W205+ candidate:** investigate the dev outbox/reactive-NOTIFY for the new_message broadcast (is the StoredEvent written? does the reactive OutboxWorker process it in this dev container?).
2. **Live in DEV only.** ws-hub is absent from the prod compose + k8s; prod still self-heals via refetch. A prod ws-hub deploy is a future infra wave (out of approved scope).
3. **Read receipts now flip live (the W203 motivation) — genuinely verified.** This is the real, demonstrated upgrade over W203's self-heal.
4. **Multi-tab same-user self-echo guard is user-level** — a 2nd tab won't live-show this user's own sends (self-heals on refetch). Accepted, documented.
5. **No join-all-chats.** A client joins only the **open** room; other chats' unread badges update on the next `["chats"]` refetch. Live cross-list unread is out of scope.
6. **The mirror is the ephemeral tier** (core NATS fire-and-forget, no durable stream) — a dropped frame self-heals via refetch. Matches the W203 read-receipt ephemeral framing.
7. **Typing deferred** (plan SW7-optional) — not cheap: ws-hub's relay (`client.go`) does no send-side room-membership check, so live typing would widen the surface (a client could spoof typing to any known chat id). A focused follow-up where it can be done securely.
8. **raw `npm audit` 4 high** — dev-only `@lhci/cli` cascade (tmp/inquirer/external-editor), pre-existing since W191, already allowlisted (expires 2026-08-31); `npm audit --omit=dev` = 0. NOT W204 (zero deps added).
9. **The 2-browser dev verification used chrome-devtools-mcp + tab-backgrounding.** The async new_message timing + backgrounding made deterministic async-frame capture unreliable — though the 14-second userB-foreground poll ruled out *pure* timing (the producer simply didn't fire). The synchronous read frame caught userB connected, which is why it was the decisive proof.
10. **No ws-hub Go changes beyond the SW7 path fix** — the relay send-side no-membership-check smell is noted (see #7), not fixed.
11. **Carry-forward (unchanged):** W134 §H#2 bundle-delta recording-only; W134 §H#10 /messenger Phase 5 SSR by-design (W161 SW2).

---

## NEW (z) discoveries (2)

- **(z) #1 — ws-hub dormant 404 (FIXED, SW7).** `auth_client.go` hardcoded `/api/internal/chat/check-participant`; the backend mounts the internal chat router under `API_V1_PREFIX` → the real route is `/api/v1/chat/check-participant`. The old path 404'd → fail-closed room-join. **Dormant because no client ever sent a room "join" until W204 wired the frontend join** — exactly the W173 dormant-routing-gap class (a code path only exercised once /messenger is end-to-end). Empirically confirmed (`/api/v1/...` → 200, `/api/internal/...` → 404); fixed + the join now succeeds.
- **(z) #2 — new_message broadcast producer doesn't fire in dev (DOCUMENTED, W205+).** `stored_events` + `failed_outbox_events` both empty after sends + no post-rebuild OutboxWorker processing → the async `MessageSent` → reactive-OutboxWorker → `notify_new_message` → `broadcast_to_chat` chain isn't completing in this dev container. A pre-existing dev characteristic, upstream of the W204 bridge. The read path is synchronous so it's unaffected; this is why W203 never surfaced it (W203 tested read receipts + new_message was self-heal-only with no bridge).

The SW1→SW1-fix "publish-only-if-connected" correction is a **within-SW SAME-mechanism design correction** (W138 L#1), not a (z) discovery.

---

## NEW Gotchas (for CLAUDE.md)

1. **The live WS bridge chain** — backend `broadcast_to_chat` → `publish_core` (core NATS `chat.{chat_id}`) → ws-hub `chat.*` core subscription → per-connection room fan-out → browser. Only `docker-compose.full.yml` (dev) runs ws-hub + nats; the prod compose has NO ws-hub → the live bridge is **DEV-only** until a prod ws-hub deploy infra wave. The read path is synchronous (live now); the new_message path is async (outbox producer — see #5).
2. **`publish_core` MUST use orjson + publish-only-if-connected.** `serialize_message` returns raw `uuid.UUID` for id/chat_id/sender_id → stdlib `json.dumps` crashes; use `orjson.dumps(payload, default=str)`. NEVER connect from this ephemeral hot path (a NATS outage would add a multi-second timeout to message-send + raise in test/CLI) — `if self._nc is None or not self._nc.is_connected: return`; the broker's background reconnect restores `_nc`; frames self-heal via refetch.
3. **ws-hub room-join authz path is `/api/v1/chat/check-participant`** (NOT `/api/internal/...`) — the internal chat router mounts under `API_V1_PREFIX`. Dormant 404 fixed in W204 SW7 (W173 dormant-routing-gap class).
4. **NATS→ws-hub→room fan-out can't do per-recipient exclusion** → the frontend self-echo guard is load-bearing (skip new_message if `sender_id===currentUserId`; skip read if `user_id===currentUserId`; `currentUserId` threaded via MessengerContext from `useAuth`). It's **user-level**, so a 2nd tab of the same user won't live-show that user's own sends (self-heals). ws-hub room membership is **per-connection** → `ws.onopen` must rejoin the active room (`activeRoomRef`).
5. **new_message live in dev depends on the async outbox producer** (`send_message` → `MessageSent` → `capture_domain_events` after_flush → reactive `OutboxWorker` → `notify_new_message` → `broadcast_to_chat`) which didn't complete in the W204 dev session (`stored_events` empty). Read receipts go live synchronously (`mark_read` → `broadcast_to_chat` directly). When verifying new_message live, first confirm the StoredEvent is written + the reactive OutboxWorker processes it in the dev container.

---

## W141 anti-pattern compliance

- **#1 (STRICT 1-iter per SW):** each SW landed in one iter; SW1-fix + SW6-fix are within-SW SAME-mechanism sub-fixes (W138 L#1 — making the shipped wave actually work), not mechanism pivots. The new_message dev-producer gap was honestly DEFERRED (no rabbit-hole into pre-existing outbox infra) rather than chased mid-wave.
- **#3 (verify-before-write):** Phase 3 confirmed orjson + self-echo + join-authz before writing; the SW7 404 was confirmed empirically (`/api/v1` → 200 vs `/api/internal` → 404) before the fix; the new_message-producer diagnosis disproved the timing hypothesis with a 14-second foreground poll before concluding.
- **#4 (closures-after-evidence):** the bridge "PROVEN live" claim is attributed only AFTER the captured live `read` envelope frame; `new_message` is honestly framed as verified-by-construction + dev-producer-gapped, NOT claimed live. The "wave complete" declaration waits for CI green (W203 §H#5 lapse not repeated).
- **#15:** all 9 W204 commits fired the husky pre-commit chain cleanly (lint-staged + detect-secrets + Python 2 except check + gofmt-clean Go); NO `--no-verify`.

---

## W205+ candidates

- **Dev outbox-producer investigation** (closes W204 (z) #2 / §H#1): determine whether the `MessageSent` StoredEvent is written (`capture_domain_events` after_flush) + whether the reactive `OutboxWorker` processes it in the dev container (reactive NOTIFY trigger present? worker running post-rebuild?). Demonstrating new_message live in dev follows directly once the producer fires (the bridge is already proven).
- **`mark_single_message_read` dead-code cleanup** (W203 carry).
- **Prod ws-hub deploy** (live bridge in prod — a separate infra wave: ws-hub absent from prod compose + k8s).
- **Live typing** (the secure follow-up — needs a ws-hub send-side room-membership check + a typing self-echo guard + `currentUserName` threading).
- Next backend-dependent messenger feature (edit/delete or reactions).

---

## Polish-v1 (post-«безупречно?» self-audit, 2026-05-30)

The honest self-audit against the plan surfaced two real gaps in the close, both addressed here.

### 1. Assertion #3 (read-flip) — now RIGOROUSLY CLOSED (was only frame-delivery-verified)

The W204 close proved the bridge *delivers* a `read` frame to a browser (a frame captured in `__wsFrames`). It did NOT separately observe the plan's exact assertion #3: **"B reads → A's bubble flips to Seen live, with no refetch in A."** Polish-v1 closed it end-to-end (stack still healthy):

- userA (real login `test@university.dev`) on the DM sent `W204-FLIP-…` (read_at: null → **no marker**; the pre-existing `Просмотрено · 14:42` from the main run was on an older message).
- userB (`w203reader@university.dev`, login via a **separate curl session** — no browser-context clobber) `POST /chats/{id}/read` → 200 → `mark_messages_read` → `broadcast_to_chat(read, user_id=userB)` → `publish_core` → ws-hub → userA's WS.
- userA was **idle** (no reload/navigate). Within ~9s its bubble flipped to **`Просмотрено · 20:45`** (fresh current-time stamp; the W203 marker correctly *moved* to the now-last-read sent message — seenCount stayed 1).
- **No-refetch proof:** userA's network shows exactly **one** `GET …/messages` (the initial reload, reqid=485) and **no** subsequent message refetch. The flip came purely from the live WS frame → `applyReadFrame` updating the React Query cache in place. (reqid=486 `POST /read` is userA's *own* mark-read on open, not the flip trigger.)

So the **cross-user read-receipt live flip — the W203 motivation — is now flawlessly proven**, not just frame-delivery-verified. (`__wsFrames` caught 0 frames because the constructor patch only wraps *new* sockets and userA's WS didn't reconnect; the *existing* socket handled it — the visible flip + zero-refetch is the proof.)

### 2. new_message dev-producer gap — SHARPENED root cause (still W205+, still pre-existing)

The close said "the async outbox producer doesn't complete in dev (`stored_events` empty)." Polish-v1 root-caused it precisely:

- The OutboxWorker **IS** running (Reactive Mode, listening on `outbox_events` — current backend, 2h uptime).
- `register_event_listeners()` **IS** called (lifespan.py:405) + both listeners registered (`after_flush` capture + `after_flush_postexec` persist) + logged at startup.
- `send_message` **DOES** call `record_event(MessageSent)` unconditionally for every message (command_service.py:303, with the explicit ARCH-BE-01 comment ensuring it lands in `stored_events`); the *synchronous* `notify_new_message` is commented out (command_service.py:377) → new_message is **fully** outbox-gated.
- **Yet `stored_events` is EMPTY for ALL aggregate types over the 2h uptime** (not just chat — `user.created`, `event.created`, etc. all absent), `failed_outbox_events` is empty, and the worker has **never** logged processing an event.

⇒ The entire dev domain-event capture pipeline produces **zero** StoredEvents despite correct registration + the worker running + events being recorded. This is a **systemic, pre-existing dev-environment issue** affecting every event-driven feature (notifications, embeddings, chat), definitively **upstream of + independent of the W204 bridge** (W204 touched none of `send_message`/`events.py`/the uow/session config). The read path is unaffected because `mark_read` calls `broadcast_to_chat` *synchronously* (bypasses the outbox) — which is why W203 never surfaced it. Per STRICT 1-iter + "don't rabbit-hole pre-existing infra," it stays W205+, now with this exact characterization to start from.

### 3. SW7-naming clarification + honest partial-delivery framing

- **SW7 naming:** the plan's SW7 was "live typing (RECOMMEND DEFER)" — correctly deferred. The wave's `SW7` commit (`c06edef64`) is a *different* thing: the emergent ws-hub dormant-404 fix ((z) #1), numbered SW7 because it was the 7th code commit. Functionally everything is correct; the numbering overlap is noted so the two aren't conflated.
- **Honest partial-delivery vs plan scope:** the plan's "Full live bridge, DEV" wanted **both** new_message + read flipping live. W204 delivers: the bridge built + the **read path flawlessly proven** (cross-user flip, live, no refetch), and **new_message NOT live** — blocked by the pre-existing systemic outbox-capture issue above (verified-by-construction via the proven bridge + SW1/SW3 unit-proofs). So W204 is **not** 100% of the plan's headline scope; it is a clean, honest partial delivery — the bridge is correct + proven, the read half is complete, and the new_message half is gated by pre-existing infra precisely characterized for W205.

### Gates re-confirmed (polish-v1)

CI was already green on the close commit `350b278bc` (Matrix Expansion + all 8 jobs ✅). Polish-v1 changes are docs-only (this section + CLAUDE.md row/Gotcha sharpening + MEMORY.md) — zero code/bundle impact; the W204 bundle baseline (`9d28a0be…` main / `2fe75921…` server, × 3 BYTE-IDENTICAL) is unchanged.
