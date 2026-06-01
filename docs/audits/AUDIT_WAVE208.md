# AUDIT — Wave 208

**Date:** 2026-06-01
**Branch:** `egorribun`
**Theme:** Messenger feature completion in DEV — reply notifications (B, Supersede-in-DMs) + dead-code cleanup (D) + message-list polish (E: scroll-to-bottom FAB + date dividers + sender grouping). Voice messages + prod deploy explicitly deferred.
**Wave streak:** 68th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 anti-pattern discipline.

---

## Scope (user-chosen)

User mandate: *"продолжаем работу на мессенджером согласно нашей roadmap"* + AskUserQuestion answer **"B+D+E"** with the explicit framing: *"пока деплой не нужен, в первую очередь нужно полностью завершить работу на всей платформой; пока о деплое даже думать не стоит"*. Candidate **A (prod ws-hub + NATS deploy)** deferred entirely; the `live-in-DEV-only` caveat across W203–W207 stays a deliberate, documented non-goal.

Second AskUserQuestion locked the sub-scope:
- **E features:** Scroll-to-bottom FAB + Date dividers + Message grouping. **Voice messages DEFERRED** (M-L: MediaRecorder + permissions + playback + attachment-type — its own focused wave). Message **search is already functional** (W184 SW1 — ground-truthed; the opening-prompt "may be UI-only" flag was stale).
- **B reply-notification UX:** **Supersede in DMs** (the quoted author is dropped from the generic `chat.message` and gets a specific `chat.reply` instead — no double-notify) over Additive.

**6 code commits + this SW6 close.**

---

## SW1 — B: reply-notification SUPERSEDE (`d2ecd069e`)

`feat(wave208-sw1-reply-notify-supersede)` — `app/services/chat/notification_service.py` + `tests/services/test_chat_helpers.py`.

`ChatNotificationService.notify_new_message`'s push block: when `replied is not None and replied.sender_id != sender.id`, drop `replied.sender_id` from the generic `other_participants` recipients, then fire a **second** `create_notifications_for_users(type="chat.reply", title=sender_name, body=body_preview, url=f"/messenger/{chat_id}", tag=f"chat-reply:{replied.id}", dedupe_key=f"chat-reply:{message.id}", user_ids=[replied.sender_id], topic="chat", payload_data={chatId, repliedToMessageId, replyingMessageId, senderId}` (str-wrapped)`)`. The shared `sender_name`/`body_preview` computation is hoisted behind `if other_participants or is_reply_to_other:` so a 2-person DM (generic list empties after exclusion) still sends the reply notification while preserving the W205 `test_notify_new_message_skips_push_when_only_sender` behavior.

- **Verify-before-write:** `MessageDTO.sender_id` + `.id` confirmed at `app/schemas/dtos/chat.py:45,47`; `create_notifications_for_users` accepts `dedupe_key` at `app/services/notifications/delivery.py:76`. Both read from source before depending on them (W141 #3).
- **The live WS `new_message` frame is UNTOUCHED** — only the persistent bell/push entry upgrades from generic to specific. **FE needs zero changes** (NotificationsBell renders generically by `type`; no new FE i18n key).
- **Edge cases asserted:** 3-person → quoted author excluded from generic + gets `chat.reply`; 2-person DM → 0 `chat.message` + 1 `chat.reply`; self-reply → no exclusion, no `chat.reply`; replied hard-deleted → `reply_to_message_id` already NULL → `replied is None` → no `chat.reply` (verified-by-construction at `event_handlers.py:207-211`).
- **4 tests** (test_chat_helpers.py 14 → 18): 3-person supersede, DM-only-reply, self-reply-keeps-generic, handler-wiring (`get_message_by_id` threaded into `notify_new_message` as `replied`).

---

## SW2 — D-1: drop dead WS `typing` dispatch (`a1555b1b2`)

`feat(wave208-sw2-drop-dead-ws-typing-dispatch)` — `app/api/ws/dispatcher.py` (delete the `elif msg_type == "typing":` branch, lines 59-99) + `tests/test_ws_dispatcher_full.py` (delete `TestDispatchTyping`, 5 methods) + `app/api/websocket.py` (remove the stale from-client typing comment `:90`).

The inbound WS typing handler died in W207 SW8 (frontend now POSTs the REST `/typing` endpoint; the Go ws-hub drops `"typing"` at its `allowedMessageTypes` boundary). An inbound `"typing"` now correctly falls to the `else` → "Unknown message type". The `ping`/`read`/`get_online`/`else` branches + the shared `async_session`/`ChatRepository`/`check_participant` imports (used by `read`) all stay → no import churn.

- **Verify-before-write deviation from plan:** the plan said remove **both** `websocket.py` typing comments (`:90` + `:96`), but the **outbound** typing frame is still alive (emitted via the W207 `broadcast_typing` path → `broadcast_to_chat` → connected clients + the NATS bridge). So `:96` (to-client typing) **still accurately documents the endpoint's output contract** and is **KEPT**; only `:90` (from-client typing, which the dispatcher no longer accepts) is removed.
- `tests/contracts/test_ws_message_contract.py` is **unchanged** — `"typing"` remains a valid server→client type, and `test_backend_dispatcher_uses_known_types` greps the dispatcher source for *unknown* types, so removing a *known* type cannot break it. No OpenAPI snapshot regen (WS handler, removes no routes).

---

## SW3 — D-2: drop dead `mark_single_message_read` (`35c5d654d`)

`feat(wave208-sw3-drop-dead-mark-single-read)` — `app/repositories/chat_repository.py` (delete `mark_single_message_read`, lines 600-605).

Dead since W203 SW4 switched read receipts to the chat-level `mark_messages_read`. Re-grep across `app/` + `tests/` reconfirmed **0 callers / 0 tests / 0 routes** (every other hit is docs/audit prose). `update(Message)` stays imported (used by `mark_messages_read`) → no import churn. No OpenAPI regen.

### ▶ Backend batch gate (W203 §H#5)

After SW3, the **single full backend pytest** run (B is on the shared `notify_new_message` hot path → a slice is not a substitute):
```
uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py
→ 2952 passed, 25 skipped, 0 failed (3m12s)
```
Reconciles exactly: W207 baseline **2953** + 4 SW1 tests − 5 SW2 typing tests = **2952**. (pact-python ws-hub contract test ignored — Windows DLL load failure, per W204 §Honesty.) The matching arithmetic is itself a no-cascade signal (W205 §H#5).

---

## SW4 — E1: scroll-to-bottom FAB (`39a5b800c`)

`feat(wave208-sw4-scroll-to-bottom-fab)` — `frontend/src/components/messenger/ChatWindow.tsx` + `messenger:aria.jumpToLatest` (en + ru).

A floating "jump to latest" button appears once the user scrolls > `SCROLL_FAB_THRESHOLD` (240px) up from the bottom; clicking it smooth-scrolls to the newest message via the existing `virtualizer.scrollToIndex()`. The scroll `<div>` is wrapped in a `relative flex flex-1 min-h-0 flex-col` so the FAB anchors as an `absolute` sibling; the `flex-1 min-h-0 overflow-y-auto` chain (virtualizer height + auto-scroll) is preserved.

- **React-Compiler-safe by design:** visibility is driven by `useState` (read in render); scroll metrics are read only inside the listener handler (ref access in a handler, never during render — the same discipline as `animateFromIndex`). The effect's guard reads `isLoading`/`isError`/`filteredMessages.length` so they're genuine deps → the listener re-binds to the live scroll element on branch changes + the FAB stays hidden in the loading/error/empty states.
- **The build is the gate** (W199/W207 SW9): `npm run build` ran `@rolldown/plugin-babel` (the React Compiler transform) cleanly — **no `"use no memo"` needed** (unlike ReactionPill, which merges floating-ui refs).
- Verified via the 131 messenger component tests (no regression) + the build gate; the FAB's *scroll-visibility* is jsdom-untestable (no real scroll metrics) — see §Honesty.

---

## SW5 — E2+E3: message-list annotations (`bc13723e6`) + SW5-followup render tests (`06a91b7f3`)

`feat(wave208-sw5-message-list-annotations)` — `frontend/src/components/messenger/types.ts` + `frontend/src/hooks/features/useMessengerController.ts` + `ChatWindow.tsx` + `messenger:dateDivider.{today,yesterday}` (en + ru) + `useMessengerController.test.tsx` (+3).

`useMessengerController`'s `transformedMessages` useMemo annotates each message:
- `showDateDivider` (first message of a new calendar day) + `dateLabel` (Today / Yesterday / absolute localized date). ChatWindow renders the divider **inside** the `measureElement` virtual-item (auto-measured) — **NOT** a separate virtual row → the W184 SW1 `filteredMessages` count/index alignment stays intact.
- `isGroupStart` (first of a sender-run: different sender, > 5min gap, or a new day). When explicitly `false`, ChatWindow swaps the avatar for a same-size `aria-hidden` spacer + tightens row padding (Telegram-style). `undefined` (optimistic/standalone) keeps the avatar.

- **Locale gotcha closed:** `formatMessageTime` is locale-less (always en-US); the absolute date label passes `i18n.language` to `formatDate(presets.chatGroup, locale)`. `now`/`yesterdayStart` are per-render snapshots, intentionally not in the memo deps (they'd defeat memoization); `t` + `i18n.language` added (used for labels). Annotation fields are optional → the optimistic builder is unchanged.
- The `react-i18next` test mock gained `i18n: { language: "en" }` (the transform now reads `i18n.language`).
- **3 transform tests** (useMessengerController.test.tsx 24 → 27): per-day divider + label; sender/gap group boundaries within a day; absolute-date label for older messages.
- **SW5-followup** (`06a91b7f3`, `test(wave208-sw5-followup-chatwindow-render)`): the *render* half SW5's plan had delegated to a visual smoke. Since the dev Docker stack is cold (full bring-up is the W137 Windows-wall risk) and the LHCI-mock-user preview can't exercise message data, the stronger reliable verification is **4 deterministic ChatWindow render tests** (ChatWindow.test.tsx 36 → 40): divider renders its label verbatim above a `showDateDivider` message + nowhere else; no divider when absent; avatar `<img>` for a group-start message vs an `aria-hidden` spacer when `isGroupStart===false`; avatar shown when `isGroupStart` is undefined (backward-compat).

---

## SW6 — Close (this commit)

Audit doc + CLAUDE.md row + 3 NEW Gotchas + INDEX.md + N+3 rotation (`git mv docs/audits/AUDIT_WAVE205.md docs/audits/archive/`) + MEMORY.md trim + memory files.

---

## Gates (end of wave)

| Gate | Result |
|------|--------|
| Backend `uv run pytest --ignore=...test_ws_hub_contract` | **2952 passed / 25 skipped / 0 failed** (W207 2953 + 4 − 5 = 2952) |
| Frontend `npm run test:ci` (coverage gate) | **1371 passed / 12 skipped / 0 failed**; functions **70.27%** ≥ 70%, branches 72.85% ≥ 65%, statements/lines 79.27% ≥ 70% |
| `npx tsc --noEmit` | 0 errors |
| `npm run lint -- --max-warnings=0` | 0 |
| translationParity | 18/18 (new `dateDivider.*` + `aria.jumpToLatest` synced en↔ru) |
| `npm run build` (React-Compiler Babel gate) | clean — FAB + transform compile without `"use no memo"` |
| **Build × 3 BYTE-IDENTICAL** | main JS `index-DBZkEBwc.js` **180,268 b** sha `002d7c1a9902f18ea027def6bff07590c03f38e9270b4f882be59f92cd69cb1b` × 3 + server.js **24,024 b** sha `323604b14e9c3a6a60e3fc469261cffbc7bf2ab047fd8b2606858dd029543506` × 3 |
| husky pre-commit chain | clean on all 6 commits (lint-staged + detect-secrets + ruff/Python-2-except where applicable); NO `--no-verify` |

### Bundle baseline (honest framing)

The main-entry chunk is **the same SIZE as W207** (180,268 b) but **hash-shifted** (`Dm-a9dmU` → `DBZkEBwc`) — the W193 SW5 / W202 module-graph behavior: SW4 FAB + SW5 dividers/grouping land in the **route-lazy `Messenger-BJ7NGYkr.js` chunk (108,590 b)**, so the entry chunk that ships on every page is size-stable while its content hash flips (it embeds the rehashed messenger-chunk filename). server.js is also size-identical + hash-shifted (the SSR module graph references the messenger code). **NOT byte-identical to W207** — real E client-tree changes; the W134-SW3-era cross-wave content-sha invariant does not apply (E touched the FE). Build × 3 reproducible establishes the new W208 baseline.

---

## §Honesty probe (0-3 OPEN)

Carry-forward structural non-goals (unchanged):
1. **`live-in-DEV-only`** — prod has no ws-hub/NATS deployed (candidate A, explicitly deferred by the user). Every messenger live feature self-heals via refetch in prod. The W208 reply-notification supersede rides the established outbox rail (W205 SW-A) which works in dev; in prod the persistent notification is created the same way (the outbox runs).
2. **W134 §H#2** — bundle-delta recording-only.
3. **W134 §H#10** — /messenger Phase 5 SSR is by-design (`ssr: 'data-only'`, W180 SW3 / W161 SW2).

NEW W208 caveats (honest deferrals, not defects):
4. **B supersede end-to-end NOT live-verified in dev.** The supersede logic is unit-tested precisely (4 tests incl. handler-wiring) + the full backend pytest passed (no regression on the shared hot path). An end-to-end "reply → quoted author's `GET /notifications` shows `chat.reply` not `chat.message`" check was **not** run because the dev Docker stack was cold (full bring-up = the W137 rust-crypto WASM Windows-wall risk). Per `feedback_perfectionism.md` "if you can't measure, defer honestly".
5. **E FAB scroll-visibility is jsdom-untestable** (no real scroll metrics) — covered by the React-Compiler build gate + the 131 messenger tests (no regression) + the straightforward state-driven logic. The plan acknowledged this; the dev-chain visual smoke is deferred (cold stack, matching the W183 SW14 precedent).
6. **E dividers/grouping render** is verified by **4 deterministic SW5-followup ChatWindow tests** (substituting the impractical cold-Docker visual smoke) rather than a live visual capture.

**0 NEW (z) discoveries** — Phase 1 Explore + Phase 3 verify-before-write resolved the load-bearing unknowns (MessageDTO `.sender_id`, `create_notifications_for_users` `dedupe_key`, the `:96` to-client-typing-still-alive deviation, the locale-less `formatMessageTime`, the coverage-excluded `src/hooks/**`) before any edit. Extends the low-(z) streak.

**0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

---

## W141 anti-pattern compliance

- **#1 (STRICT 1-iter/SW):** each of SW1-SW6 landed in one iteration; the SW5-followup render tests are a within-SW5-mechanism completion (verifying SW5's render), not a pivot (W138 L#1). The duplicate-lucide-import in SW4 was a within-iter SAME-mechanism correction.
- **#3 (verify-before-write):** read `MessageDTO`, `create_notifications_for_users`, `dispatcher.py`, `chat_repository.py:600-605`, `vitest.config.ts`, `date.ts`, `formatMessageTime`, the contract test + the test fixtures from source before depending on them; caught the plan's "remove both typing comments" overreach (`:96` is still accurate) + the locale-less `formatDate` trap + the coverage-excluded-hooks fact (the W207 lesson was right, the Explore agent was wrong).
- **#4 (no premature claims):** "GREEN" attributed only after captured gate output (pytest 2952, test:ci 1371 + coverage, Build × 3 sha); B's live-end-to-end is honestly NOT claimed (deferred §Honesty #4); "complete" waits for CI green post-push.
- **#15 (ARCHIVED W159 SW4):** every commit fired the husky pre-commit chain cleanly; NO `--no-verify`.

---

## Messenger arc

W203 read receipts → W204 live bridge → W205 new_message + edit/delete → W206 reactions → W207 reply/quote + reactor-list + live typing → **W208 reply notifications (supersede) + dead-code cleanup + message-list polish (FAB / date dividers / grouping)**.

**W209+ candidates:** prod ws-hub + NATS deploy (candidate A — closes `live-in-DEV-only` across W203-W208; infra-authoring wave per the W208 opening-prompt §3 scope-check) · voice messages (E, deferred) · group-chat creation path (candidate C — makes the W207 reactor-list high-value) · reply-notification live end-to-end verify (closes §Honesty #4 if a warm stack is available) · B supersede group-chat behavior once groups exist.

Memory references (`.claude` profile only): `memory/wave208_backlog.md`, `memory/wave209_opening_prompt.md`.
