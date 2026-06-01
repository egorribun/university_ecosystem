# AUDIT — Wave 206: Message Reactions (👍❤️😂😮😢)

**Date:** 2026-05-31
**Branch:** `egorribun`
**Status:** ✅ CLOSED — PROVEN live cross-user (add + remove of a real 👍) in the dev Docker chain
**Wave discipline:** 66th consecutive wave with brainstorm → AskUserQuestion → Phase 1 Explore → STRICT 1-iter/SW → per-SW gates → single push at wave-close → CI-green poll → audit + N+3 rotation.

---

## Headline

W206 ships **message reactions** — the next backend-wired messenger feature on the W203/W204/W205 rail
(model → migration → repo → schema → service → ws-hub frame → synchronous broadcast → FE optimistic UI),
**PROVEN live cross-user** in the dev Docker chain.

Reactions are the **first messenger feature that needs a CHILD table** — they're per-`(user, message, emoji)`,
many-per-message — so `MessageReaction` mirrors the existing `Attachment` child-of-`Message`, NOT a JSON column
on `Message`. Everything else mirrors the W205 edit/delete rail.

**The headline finding (SW7):** live verification **overturned my own root-cause attribution** (W141 #4 in action,
the W203 §H#5 cascade pattern). The mid-wave path→query route switch was first blamed on a "Caddy path mis-decode";
live two-browser verification showed the earlier "failed remove" was a **corrupt stored value** — curl on Windows
Git-Bash mangles a literal multi-byte emoji in a request **body** to `??` (`3f3f`), so the curl-added reaction was
stored as `??` and no remove (path *or* query) could ever match the correctly-encoded 👍. The docstrings + commit
message were re-attributed honestly **before** commit (no git-history lie).

**User-chosen scope** (AskUserQuestion): message reactions feature · **delta + self-echo** WS frame · **fixed emoji
quick-set** `["👍","❤️","😂","😮","😢"]`.

---

## Per-SW

### SW1 — model + migration  `b09af536f`
`feat(wave206-sw1-message-reactions-model-migration)`
- `app/models/chat.py`: `MessageReaction(Base, UUID7PrimaryKeyMixin)` — `message_id` FK→messages CASCADE
  (`index=True`), `user_id` FK→users CASCADE, `emoji: String(16)` (holds multi-codepoint emoji), `created_at`,
  `UniqueConstraint("user_id","message_id","emoji", name="uq_message_reactions_user_message_emoji")`. `Message.reactions`
  relationship `lazy="noload"` (MOD-30-01 CI gate) + `message` back-relationship `lazy="noload"`. **NO** `EventEmitterMixin`
  — reactions broadcast synchronously (mark_read pattern), NOT via the outbox.
- `app/models/__init__.py`: re-export `MessageReaction`.
- NEW `alembic/versions/202605300003_create_message_reactions.py` — `down_revision="202605300002"` (W205 head),
  `_table_exists` guard, `op.create_table` + `UniqueConstraint` + `op.create_index("ix_message_reactions_message_id")`.
- **Gate:** `py_compile` + `ruff` + alembic **up→down→up idempotent verified live** (single-file `-v` mount into a
  one-off `docker compose run --no-deps migrations` against the running postgres, `MSYS_NO_PATHCONV=1` — the runtime
  image has no `alembic`/`uv` console script and a local `alembic/` dir shadows the package at CWD=/app).

### SW2 — repo + schema  `22fed0705`
`feat(wave206-sw2-reactions-repo-schema)`
- `app/repositories/chat_repository.py`: `message_exists_in_chat(message_id, chat_id) -> bool` (SELECT EXISTS);
  `add_reaction(...) -> bool` (`pg_insert(MessageReaction).on_conflict_do_nothing(index_elements=["user_id","message_id","emoji"])`,
  return `rowcount > 0` = is_new); `remove_reaction(...) -> int` (delete, affected).
- `app/schemas/chat.py`: `ReactionAggregate(SecureBaseModel){emoji, count, reacted_by_me=False}` +
  `MessageResponse.reactions: list[ReactionAggregate] = Field(default_factory=list, ...)`.
- `app/schemas/dtos/chat.py`: `MessageReactionDTO(SecureBaseModel){user_id, emoji}` + `MessageDTO.reactions`.
- **Gate:** `ruff` + `mypy` slice (the 16 mypy errors are PRE-EXISTING in transitively-imported `redis_session.py`/
  `presence.py` Redis type-args; my 3 files clean via `--follow-imports=silent`). One within-SW ruff-format re-stage
  (documented W141 #15 exception).

### SW3 — service + query aggregation  `07d6c3e5b`
`feat(wave206-sw3-reactions-service-aggregation)`
- `app/services/chat/command_service.py` `ChatMaintenanceService`: `add_reaction` (get_by_id → ensure_exists →
  participant check → `message_exists_in_chat` else 404 → `repo.add_reaction` → `async with self.uow: commit()` →
  `if is_new:` `broadcast_to_chat({type:"reaction_changed", chat_id, message_id, user_id, emoji, action:"added"}, exclude_user_id=user.id)`)
  + `remove_reaction` (participant check → `repo.remove_reaction` → commit → `if affected:` broadcast `action:"removed"`).
  `exclude_user_id` mirrors the read-frame: the in-process path skips the actor; the NATS mirror doesn't, so the FE
  self-echo guard is the real protection (W204 SW4).
- `app/repositories/chat_repository.py` `get_messages`: add `selectinload(Message.reactions)` (no N+1).
- `app/services/chat/query_service.py`: module helper `_aggregate_reactions(rows, current_user_id)` (group by emoji,
  count, per-viewer `reacted_by_me`, first-seen order); `get_messages` site adds `reactions=_aggregate_reactions(...)`
  (**W203-SW8 site #1**); `get_chats` last-message site adds `reactions=[]` (lightweight projection — **W203-SW8 site #2**).
- **Gate:** `ruff` + `mypy` slice. (Full pytest at SW4 — this SW adds a NEW `broadcast_to_chat` caller + new selectinload,
  the W203 §H#5 dormant-bug surface.)

### SW4 — API routes + tests + OpenAPI  `cb6003beb`
`feat(wave206-sw4-reactions-api-tests)`
- `app/api/chat.py`: POST `/{chat_id}/messages/{message_id}/reactions` (`emoji: str = Form(min_length=1, max_length=16)`)
  + DELETE (path-segment emoji at SW4; **changed to query param in SW7**).
- NEW `tests/test_wave206_reactions.py` (10 tests: TestAddReaction 4, TestRemoveReaction 3, TestAggregateReactions 3) —
  mirrors the W205 mock pattern (`_mock_uow`/`_mock_user`/`_mock_chat`/`_svc`, BROADCAST patch).
- OpenAPI snapshot regenerated (`newline='\n'` — W205 CRLF gotcha; add-only superset-safe).
- **Gate:** FULL backend pytest **2933 passed** (W203 §H#5 — full suite, not a slice) + OpenAPI contract + `py_compile`.

### SW5 — FE schema + hook  `d8cf87c64`
`feat(wave206-sw5-reactions-fe-schema-hook)`
- `frontend/src/api/schemas/wsMessage.ts`: `ReactionChangedSchema{type:"reaction_changed", chat_id, message_id,
  user_id, emoji: NonEmptyString, action: v.picklist(["added","removed"])}` appended to the `WsServerMessageSchema` variant.
- `frontend/src/hooks/useChatWebSocket.ts`: `applyReactionChangedFrame(old, frame)` pure helper (match `message_id`;
  added → count+1 / push `{emoji,count:1,reacted_by_me:false}`; removed → count-1 / drop-if-0; `reacted_by_me` untouched;
  `noUncheckedIndexedAccess`-safe) + `case "reaction_changed"` (self-echo guard `if (validated.user_id ===
  currentUserIdRef.current) break` + `setQueryData(applyReactionChangedFrame)` + invalidate `refetchType:"none"`) +
  `WebSocketMessageType` += `"reaction_changed"`.
- `frontend/src/api/chat.ts`: `Message.reactions?: {emoji, count, reacted_by_me}[]` + `chatApi.addReaction` (POST Form)
  + `chatApi.removeReaction` (DELETE; query param post-SW7).
- **Gate:** `tsc` 0 + `eslint --max-warnings=0` 0.

### SW6 — controller + ChatWindow + i18n + tests  `078b25007`
`feat(wave206-sw6-reactions-ui-optimistic)`
- `frontend/src/hooks/features/useMessengerController.ts`: `toggleReactionAggregate(reactions, emoji, currentlyReacted)`
  (actor's optimistic patch — flips `reactedByMe` + count±1 + push/drop) + transform `reactions: m.reactions?.map(...)` →
  UI `{emoji,count,reactedByMe}` + `toggleReactionMutation` (mirror `editMessageMutation`: optimistic onMutate on
  `["messages",chatId]`, rollback onError, invalidate onSettled) + `handleToggleReaction` (reads `currentlyReacted` from
  the LIVE cache via `queryClient.getQueryData`, depends on the stable `.mutate` per W203 SW8).
- `frontend/src/components/messenger/types.ts`: UI `Message.reactions?: {emoji, count, reactedByMe}[]`.
- `frontend/src/components/messenger/ChatWindow.tsx`: module-level `REACTION_EMOJIS = ["👍","❤️","😂","😮","😢"] as const`;
  reaction-pill footer (pills `aria-pressed` + violet tint for `reactedByMe` + click toggles; "+react" `SmilePlus` opens
  inline fixed-emoji picker; click-outside/Escape via `data-reaction-ui` exemption). Gated `!message.deletedAt &&
  editingMessageId !== message.id && (reactions.length>0 || onToggleReaction)`. **PRESERVES** `animateFromIndex` +
  virtualizer + `key={selectedChatId}` + theme tokens (no `text-white`).
- `ChatArea.tsx` + `MessengerFeature.tsx`: thread `onToggleReaction` (preserves `key={selectedChatId}`).
- `frontend/src/i18n/locales/{en,ru}/messenger.json`: NEW `reactions{add, react, tally}` × EN+RU (NO `defaultValue` —
  translationParity gate).
- Tests: `ChatWindow.test.tsx` +6 (pill render/aria-pressed/toggle/+react gate/picker open+select+close/deleted-suppression);
  `useMessengerController.test.tsx` +3 (optimistic add/remove/rollback).
- **Gate:** `tsc` + `eslint` + vitest serial + `i18n:check`.

### SW7 — live verify + honest re-attribution + audit + push  `08f778652`
`fix(wave206-sw7-reaction-remove-query-param)` (the route + rationale fix) → then `docs(wave206-sw7-audit)`.
- **Route:** emoji selector is a **query param** (`DELETE .../reactions?emoji=`), not a URL-path segment. Query params
  decode unambiguously (`parse_qs`) — the robust shape for an arbitrary multi-codepoint sub-resource selector; multi-byte
  content in a path segment is a known fragility class. `app/api/chat.py` uses `Query(...)` (removed unused `Path`);
  `chatApi.removeReaction` builds `?emoji=${encodeURIComponent(emoji)}`; OpenAPI snapshot regenerated (LF).
- **Honest re-attribution (W141 #4):** the path→query switch was FIRST blamed on a Caddy path mis-decode. Live
  verification overturned that — the earlier "failed remove" was a corrupt curl-stored `??`. Docstrings + commit
  re-attributed honestly **before** commit (the SW7 fix was uncommitted working-tree state, so no git-history correction
  was needed).

---

## LIVE PROOF (dev Docker chain, two browser contexts)

The frame mechanics were already exercised in earlier interim verification; SW7 added the **definitive real-emoji
two-browser proof through the actual frontend**:

| Step | Actor (real browser) | userA observes | Refetch? | DB |
|------|------|------|------|------|
| ADD real 👍 on msg `019e7a31` | userB (browser picker) | new 👍 pill appears (`pressed=false`) | **0 GET /messages** | `f09f918d` stored ✓ |
| REMOVE real 👍 (toggle off) | userB (browser pill) → query-param DELETE | 👍 pill vanishes (5→4) | **0 GET /messages** | row deleted ✓ |
| REMOVE corrupt `??` (earlier) | userB curl `?emoji=%3F%3F` | `??` pill vanishes | **0 GET /messages** | row deleted ✓ |

- `getMessagesResourceCount: 0` across userA's *entire* page lifetime (initial render from the W149 persisted React
  Query cache; all reaction updates via the WS `reaction_changed` frame — no refetch).
- userB's optimistic state: the 👍 pill flipped `pressed=true`/`pressed=false` on add/remove via `toggleReactionMutation`.
- `reacted_by_me` is correctly per-viewer: userB sees its own 👍 `pressed=true`; userA sees userB's 👍 `pressed=false`.
- DB byte-check confirmed browser-added 👍 = `f09f918d` (real), vs the curl-added `3f3f` (`??`).
- Security constraints honored: no DB credential edits; two-account verification via `POST /auth/login/json`; temp cookie
  jars deleted; userB browser context closed after the proof.

---

## Verification matrix (wave-close)

| Gate | Result |
|------|--------|
| `tsc --noEmit` | 0 errors |
| `eslint --max-warnings=0` (chat.ts) | clean |
| Frontend vitest (serial) | **1344 passed / 12 skipped / 0 failed** (W205 baseline 1335 + 9 new) |
| Backend `uv run pytest` (full) | **2933 passed** (SW4; W203 §H#5 — full suite) |
| OpenAPI contract test | pass (snapshot regenerated LF for query-param route + corrected description) |
| W206 reaction tests | 10 passed |
| alembic up→down→up | idempotent (verified live) |
| Build × 3 | **BYTE-IDENTICAL** — main `index-BVE-wSwF.js` 180,274 b sha `fc669f19fb7a1ed8` × 3 + server.js 24,024 b sha `a792d2cecb814dbe` × 3 |
| husky pre-commit (every commit) | clean — lint-staged + ruff + detect-secrets + bandit + mypy + Python-2-except all Passed; NO `--no-verify` (W141 #15) |

**Bundle:** NEW W206 baseline. Delta vs W205 (`index-D517gUte.js` 180,273 b): **+1 byte** main (reactions code lives in the
route-lazy `Messenger-*.js` chunk per W193 SW5; the main entry only shifts by import-bookkeeping); server.js SIZE identical
(24,024 b) but content sha changed (SSR module graph references reaction code). **NOT byte-identical to W205** — expected for
new client-tree code (honest framing).

---

## §Honesty probe — 0-3 OPEN

1. **Live works in DEV only** — prod ws-hub + nats are absent (W205 carry; the prod ws-hub deploy is a separate infra wave).
2. **Delta-frame count drift self-heals via refetch** — the broadcast carries a non-idempotent delta; accepted project-wide
   (same as new_message + read).
3. **W134 §H#2 (bundle delta recording-only) + §H#10 (/messenger Phase 5 SSR by-design)** — unchanged carry-forward.
4. **NEW: curl-on-Windows-Git-Bash can't ADD a real emoji** — it mangles a literal multi-byte emoji in a request *body* to
   `??` (`3f3f`). Live ADD verification must use the **browser** (correct UTF-8); curl is fine for percent-encoded
   URL/query values (ASCII). Tooling caveat, not a product bug.
5. **NEW: the path-segment reaction route was never verified for a real emoji** — the SW4 path route was confounded by the
   corrupt `??` fixture, so I have no empirical evidence it works for a real multi-byte emoji. The query-param route is
   retained (more robust + proven live), so this is a documented non-finding, not a defect.

---

## (z) discoveries — 1 NEW (FIXED)

- **(z) #1 — curl on Windows Git-Bash mangles a literal multi-byte emoji in a request BODY to `??` (`3f3f`).** The
  curl-added userB 👍 was stored as `??`, which masked itself as a "remove route bug" (DELETE 200 but 0 rows). Root-caused
  via a DB byte-check (`encode(emoji::bytea,'hex')`): browser-added reactions stored correctly (😢=`f09f98a2` etc.) while
  the curl-added 👍 stored `3f3f`. **Fix (methodology):** drive real-emoji actions through the browser; reserve curl for
  percent-encoded URL/query values. This overturned the SW7 "Caddy path mis-decode" attribution (W141 #4) and is the only
  NEW (z) of the wave.

---

## W141 anti-pattern compliance

- **#1 STRICT 1-iter per SW** — each SW landed in one iteration. SW7's route + rationale correction is a within-SW
  SAME-mechanism sub-fix (W138 L#1: making the shipped feature correct + honest), NOT a mechanism pivot.
- **#3 verify-before-write** — re-verified the model template (`Attachment`), alembic head (`202605300002`), the
  `MessageResponse(...)` two construction sites (W203-SW8), the frame schemas + hook helpers before writing. The SW7
  attribution error is exactly the failure this pattern guards against — caught + corrected via live verification before
  the claim shipped (#4 below).
- **#4 no "PROVEN live" before evidence; no "wave complete" before CI green** — "PROVEN live" attributed only after the
  captured two-browser DOM + `getMessagesResourceCount: 0` evidence; the SW7 honest re-attribution is the textbook #4
  application (the wrong "Caddy mis-decode" claim was disproven by live verification before it was committed). "Wave
  complete" waits for CI green (poll after the single wave-close push).
- **#15 every commit fires husky cleanly** — all 7 SW commits + the SW7 fix passed the husky chain (lint-staged + ruff +
  detect-secrets + bandit + mypy + Python-2-except). Ruff-format / `.secrets.baseline` re-stage is the documented
  exception; NO `--no-verify`.

**0 NEW anti-patterns.**

---

## NEW Gotchas (added to CLAUDE.md)

1. **Emoji selector as a query param, not a URL-path segment** — query params decode unambiguously (`parse_qs`); multi-byte
   content in a path segment is a known fragility class. The earlier "failed remove" was a corrupt curl-stored `??`, NOT a
   Caddy mis-decode (honest re-attribution).
2. **curl on Windows Git-Bash mangles a literal multi-byte emoji in a request BODY to `??`** — live-verify emoji ADD via the
   browser; curl is fine for percent-encoded URL/query values.
3. **Reaction delta-frame self-echo + drift-self-heals** — broadcast carries the actor's `user_id` + `{action}` delta; FE
   self-echo-guards the actor (already patched optimistically), other clients patch count ±1; `reacted_by_me` is per-viewer
   (server-computed on REST, never broadcast); drift self-heals on the next `GET /messages`.
4. **`pg_insert on_conflict_do_nothing` idempotency + `selectinload` aggregation + the W203-SW8 two-site rule** — the
   `message_reactions` child table aggregates via `selectinload(Message.reactions)` + a `_aggregate_reactions` helper; both
   `MessageResponse(...)` construction sites must set `reactions` (`get_messages` aggregates, `get_chats` last-message `=[]`).
5. **`MessageDTO.reactions` field** — `get_messages` returns `MessageDTO` (not raw ORM), so reactions flow as a DTO field
   (like attachments), aggregated in `query_service`, NOT via an ORM relationship at the response layer.

---

## W207+ candidates

- **prod ws-hub deploy infra** — closes the "live works in DEV only" carry across W203-W206 (the headline infra gap).
- **live typing indicator** — ws-hub relay does no send-side room-membership check; a focused secure follow-up.
- **`mark_single_message_read` dead-code cleanup** (W203 carry).
- **reaction notifications** + **reactor-list hover** (who reacted) — natural reaction follow-ons.
