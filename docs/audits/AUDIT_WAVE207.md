# AUDIT — Wave 207: Reply/quote + Reactor-list ("who reacted") + Live typing

**Date:** 2026-05-31
**Branch:** `egorribun`
**Status:** ✅ CLOSED — all THREE features PROVEN live cross-user (both directions where applicable) in the dev Docker chain
**Wave discipline:** 67th consecutive wave with brainstorm → AskUserQuestion → Phase 1 Explore → Context7-verified unknowns → STRICT 1-iter/SW → per-SW gates → single push at wave-close → CI-green poll → audit + N+3 rotation.

---

## Headline

W207 adds the next **three** roadmap messenger features on the shared W204 live bridge
(`broadcast_to_chat` → `publish_core` core-NATS `chat.{id}` → ws-hub `chat.*` fan-out → browser), all
**PROVEN live cross-user** in the dev Docker chain:

1. **Reply/quote** — a message references an earlier one via a `reply_to_message_id` self-FK; the bubble
   renders a quoted preview of the target. The quote travels in the live `new_message` frame (SW3
   `serialize_message` extension) so the recipient sees it with **0 refetch**.
2. **Reactor-list "who reacted"** — a desktop-hover / keyboard-focus / mobile-long-press popover listing
   which users reacted with an emoji. Reactor identities are fetched **on-demand** (never bundled into
   `GET /messages` — only the W206 count aggregate is).
3. **Live typing** — the built-but-dormant `TypingIndicator` (W181 SW4) flips **live cross-user** for the
   first time, via a new `POST /chats/{id}/typing` REST endpoint that reuses the W204 bridge — **zero Go
   change, zero new Go security surface**.

**Three Context7-verified architecture unknowns resolved before any code** (plan §A/B/C):
- **Typing was DEAD cross-user** — ws-hub's `allowedMessageTypes = {join, leave, message}` drops `"typing"`
  at its parse boundary, so the WS `sendTyping()` went nowhere. Fix: a REST endpoint that does the
  dispatcher's participant-authz + `broadcast_to_chat` → bridge → the already-built `case "typing"` receive
  handler. The endpoint's `check_participant` **is** the secure send-side membership check.
- **Reply's live quote needs a `serialize_message` extension** — `replied_to` is `lazy="noload"`, so the
  recipient's live frame would miss the quote unless `send_message` loads the target + passes a **lean
  `ReplyPreview`** `{id, sender_id, sender_name, content, deleted_at}` (NOT a recursive nested
  `MessageResponse`) into the broadcast's `serialize_message`.
- **SQLAlchemy self-FK** is the canonical adjacency-list `relationship("Message", remote_side=[id])` —
  `Message` has exactly one self-FK so `remote_side=[id]` alone is unambiguous (no `foreign_keys=[...]`).
  `ondelete="SET NULL"` (a reply survives its target's deletion → FE renders "original deleted").

**User-chosen scope** (AskUserQuestion ×2): all three features · reactor-list **full** (desktop hover +
mobile long-press, forward-looking infra since chats are 1-on-1 DMs today).

---

## Per-SW

### SW1 — reply model + migration  `2adb7384c`
`feat(wave207-sw1-reply-model-migration)`
- `app/models/chat.py` `Message`: `reply_to_message_id: Mapped[uuid.UUID | None]`
  (`ForeignKey("messages.id", ondelete="SET NULL")`, `nullable=True`, `index=True`) +
  `replied_to: Mapped["Message | None"] = relationship("Message", remote_side="Message.id", lazy="noload")`
  (placed after the W206 `reactions` relationship). `remote_side` alone is unambiguous (single self-FK).
- NEW `alembic/versions/202605300004_add_reply_to_message_id.py` — `down_revision="202605300003"` (W206 head),
  `_table_exists`/`_column_exists` guards, `add_column` + `create_index` + SET NULL FK.
- **Gate:** `py_compile` + alembic **up→down→up idempotent verified** (the W206 one-off-`docker compose run`
  pattern — runtime image has no alembic console script + a local `alembic/` shadows the package at CWD).

### SW2 — reply backend rail  `4d85612d3`
`feat(wave207-sw2-reply-backend-rail)`
- `app/schemas/chat.py`: NEW `ReplyPreview(SecureBaseModel){id: UUID, sender_id: UUID, sender_name: str|None,
  content: str, deleted_at: datetime|None}`; `MessageResponse.reply_to: ReplyPreview | None = None`;
  `MessageCreate.reply_to_message_id: UUID | None = None`.
- `app/schemas/dtos/chat.py`: `MessageDTO.replied_to: "MessageDTO | None" = None` (forward ref).
- `app/repositories/chat_repository.py`: `selectinload(Message.replied_to).selectinload(Message.sender)`
  added to `get_messages` options **and** the `get_chats` last-message query (W203-SW8 two-site rule);
  `get_message_for_reply(message_id, chat_id) -> Message | None` (validation + preview in one query —
  None if the target isn't in this chat).
- `app/services/chat/command_service.py` `send_message`: `+ reply_to_message_id` param → `get_message_for_reply`
  → `raise_not_found("message", locale)` if None → set `message.reply_to_message_id`; keep `replied` for SW3's
  broadcast preview.
- `app/services/chat/query_service.py`: build `reply_to=ReplyPreview(...)` from `msg.replied_to` at BOTH the
  `get_messages` site and the `get_chats` last-message site.
- `app/api/chat.py` `send_message`: `reply_to_message_id: uuid.UUID | None = Form(None)` threaded to the dispatcher.

### SW3 — reply live frame + tests + cascade fixes  `01eade9c5`
`feat(wave207-sw3-reply-live-frame)`
- `app/api/ws/serializers.py` `serialize_message`: optional `reply_to: dict | None = None` param → emit
  `"reply_to": reply_to`. `send_message` builds the preview dict from `replied` (SW2) + passes it into the
  broadcast's `serialize_message(...)` so the recipient's **live `new_message` frame carries the quote**.
- NEW `tests/test_wave207_reply.py` (8 tests, W206 mock pattern): valid reply stores id; nonexistent target →
  404; cross-chat target → 404; no-reply → None; get_messages nests reply_to (both sites); orphaned reply
  (target soft-deleted) renders `deleted_at`; live-frame serialize includes reply_to.
- **OpenAPI superset holds for additions** — `reply_to` / `reply_to_message_id` are pure schema ADDITIONS;
  the `assert_openapi_superset` contract (snapshot keys ⊆ current) passes **without regen** (W205 gotcha:
  superset allows additions, not removals). No docstring edit → no description-mismatch.
- **Gate:** FULL backend `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py` (W203 §H#5 — the new
  self-FK + selectinload + new query is a cascade-risk).

### SW4 — reply frontend UI  `e8181aa52`
`feat(wave207-sw4-reply-frontend-ui)`
- `frontend/src/api/schemas/wsMessage.ts`: `reply_to: v.optional(v.nullable(v.object({...})))` on
  `MessageSchema` (W205 nullable pattern — `v.optional(v.nullable(...))`, since the backend emits `reply_to: null`).
- `frontend/src/api/chat.ts`: `Message.reply_to?` field; `sendMessage(chatId, content, files?, replyToMessageId?)`
  with conditional `formData.append("reply_to_message_id", ...)`.
- `frontend/src/components/messenger/types.ts`: UI `Message.replyTo?: {id, senderName, isMe, text, deletedAt}`.
- `frontend/src/hooks/features/useMessengerController.ts`: `replyingTo` state; transform maps `m.reply_to → replyTo`
  (`isMe = reply_to.sender_id === user.id`); the send mutation threads `replyToMessageId` + builds the optimistic
  `replyTo` + clears on send; `handleStartReply` (resolves from `transformedMessages`, skips deleted) +
  `handleCancelReply`. **PRESERVED** W202 SW6b `animateFromIndex` + `key={selectedChatId}`.
- `ChatWindow.tsx`: a `Reply` button on **all** bubbles (theme-aware focus ring) + a quoted-preview block above
  the content `<p>` (`replyTo.isMe ? t("you") : senderName`, line-clamped content, "original deleted" when
  `replyTo.deletedAt`).
- `MessageInput.tsx`: a "Replying to {name}" chip + cancel-X (`replyingTo` / `onCancelReply` props).
- `ChatArea.tsx` + `MessengerFeature.tsx`: thread `replyingTo` + handlers down.
- i18n EN+RU: `reply`, `replyingTo` (RU "Ответ: {{name}}"), `replyTo.{you, deletedOriginal, unknownSender}` —
  **NO `defaultValue`** (translationParity gate).

### SW5 — reactor-list backend  `a0f3917c1`
`feat(wave207-sw5-reactor-list-backend)`
- `app/repositories/chat_repository.py`: `get_reactors(message_id, emoji) -> list[User]` via
  `select(User).join(MessageReaction, MessageReaction.user_id == User.id).where(and_(message_id==, emoji==))
  .options(selectinload(User.profile)).order_by(MessageReaction.created_at.asc())`. **Direct User↔MessageReaction
  join** — no `MessageReaction.user` ORM relationship added (avoids an unused rel; plan deviation, see §Deviations).
- `app/schemas/chat.py`: NEW `ReactorOut(SecureBaseModel){user_id: UUID, name: str|None, avatar_url: str|None}`.
- `app/services/chat/query_service.py`: `get_reactors(chat_id, message_id, emoji, user, locale)` — `get_by_id` +
  `ensure_exists` + `check_participant` + `message_exists_in_chat` 404 → maps `User → ReactorOut`,
  `name=(u.profile.full_name if u.profile else None)`, `avatar_url=(u.profile.avatar_url if u.profile else None)`.
- `app/api/chat.py`: NEW `GET /chats/{chat_id}/messages/{message_id}/reactions?emoji=` (emoji Query,
  `response_model=list[ReactorOut]`) — coexists with the W206 POST + DELETE at the same path (FastAPI routes by method).
- NEW `tests/test_wave207_reactors.py` (6 tests): maps rows, empty, no-profile → null name, non-participant → 403,
  chat-not-found, message-not-in-chat → 404.
- **The (z): mypy caught a runtime bug the 2949-passing suite missed.** First cut wrote `u.full_name` / `u.avatar_url`
  → mypy `"User" has no attribute "full_name"/"avatar_url"`. Those live on `UserProfile` via `User.profile`
  (`lazy="noload"`). Fix: repo `selectinload(User.profile)` + service guards `u.profile.X if u.profile else None`
  + test mock `.profile` + an explicit no-profile test. The reactor tests had mocked `.full_name` directly,
  so they'd have green-lit the bug. **Gate:** FULL pytest **2950**.

### SW6 — reactor-list frontend popover  `b2b2934d8`
`feat(wave207-sw6-reactor-list-popover)`
- `frontend/src/api/chat.ts`: `Reactor {user_id, name, avatar_url}` + `getReactors(chatId, messageId, emoji)`
  (emoji as a query param, matching the W206 DELETE shape).
- `frontend/src/api/hooks/messenger.ts`: `reactorsQueryKey(chatId, messageId, emoji) = ["reactors", chatId,
  messageId, emoji]` + `reactorsQueryOptions(...)` (staleTime 30s, on-demand) + `type Reactor` value-import.
- NEW `frontend/src/components/messenger/ReactionPill.tsx` — extracted per-pill (each needs its own `useFloating`
  + open-state; hooks can't run in a `.map` loop): `useFloating` + `useHover({mouseOnly:true, handleClose:
  safePolygon(), delay:{open:250}})` + `useFocus` + `useDismiss` + `useRole({role:"tooltip"})` + manual
  long-press (`pointerType !== "mouse"` 500ms timer + `longPressFiredRef`/`longPressTimerRef`) +
  `useQuery(reactorsQueryOptions(...), {enabled: isOpen && !!chatId})` + a `FloatingPortal` popover
  (loading / empty / avatar+name list). Tap still TOGGLES (W206), long-press suppresses the toggle-click.
- `ChatWindow.tsx`: `chatId?` prop + the W206 pill `<button>` map replaced with `<ReactionPill … />`.
- `ChatArea.tsx`: `chatId={selectedChatId ?? undefined}`.
- i18n EN+RU: `reactions.{whoReacted, reactorsLoading, reactorsEmpty}` (no `defaultValue`).

### SW7 — live typing backend  `6070d011c`
`feat(wave207-sw7-live-typing-backend)`
- `app/services/chat/command_service.py`: `ChatMaintenanceService.broadcast_typing(chat_id, user, locale)` —
  `if not await self.repository.check_participant(chat_id, user.id): raise_forbidden(...)` then
  `broadcast_to_chat({type:"typing", chat_id, user_id, user_name}, exclude_user_id=user.id)`. `user_name` =
  `getattr(user.profile, "full_name", None) if getattr(user, "profile", None) else str(user.email)` (mirrors
  dispatcher.py; falls back to the email — defense-in-depth for a noload profile). No DB write (ephemeral).
- `app/api/chat.py`: NEW `POST /chats/{chat_id}/typing` (`sensitive_route_limit(limit=180, window_sec=60,
  key_prefix="typing")` — permissive for the ~2/sec hot path) → `broadcast_typing`.
- **RZ-30-05 trap (re-confirmed):** the venv ruff 0.15.12 STRIPPED `except (ValueError, KeyError, TypeError):`
  at command_service.py:156 → Python 2 SyntaxError, caught by FULL-pytest collection. Restored the parens manually
  (the pinned pre-commit ruff <0.15 keeps them) + `py_compile`-verified. **NEVER `uv run ruff format` (write)** —
  use `--check` or the hook.
- NEW `tests/test_wave207_typing.py` (3 tests): participant broadcasts the frame with `exclude_user_id`; email
  fallback without profile; non-participant → forbidden, no broadcast. **Gate:** FULL pytest **2953**.

### SW8 — live typing frontend wiring  `d93397196`
`feat(wave207-sw8-live-typing-frontend)`
- `frontend/src/api/chat.ts`: `sendTyping(chatId): Promise<void>` (fire-and-forget `POST /chats/{id}/typing`).
- `frontend/src/hooks/useChatWebSocket.ts`: value-import `{ chatApi }`; `sendTyping` rewritten to a throttled
  REST call (`OUTGOING_RATE_LIMITS.typing` 500ms via the existing `lastSentRef` map) → `void chatApi.sendTyping(chatId)
  .catch(() => {})`. The receive `case "typing"` handler (W181/W204) is unchanged.
- `MessageInput.tsx`: `onTyping?: () => void` prop, called in the textarea `onChange`.
- `ChatArea.tsx`: `sendTyping` from `useMessenger()`; `onTyping={() => { if (selectedChatId) sendTyping(selectedChatId) }}`.

### SW9 — close  `b827a0570` (use-no-memo) + this audit commit
`fix(wave207-sw9-reactionpill-use-no-memo)` + `docs(wave207-sw9-audit)`
- **The (z): the React Compiler Babel transform is stricter than the eslint rule (W199).** Build × 3 FAILED with
  `ReactionPill.tsx` "Cannot access refs during render" × 2 — floating-ui's `getReferenceProps({onClick,…})`
  ref-merging + the long-press refs trip `validateNoRefAccessInRender` (a false positive — refs are only touched
  in handlers). SW6's tsc + eslint + vitest all passed; only `npm run build` (the @rolldown/plugin-babel transform)
  caught it. Fix: `"use no memo"` directive (FIX-54-01 / RC-91-01 precedent) — but then eslint flagged it "unused"
  (the plugin disagrees with the transform), so paired with `// eslint-disable-next-line react-compiler/react-compiler`.
- **Live verification** (two-browser, real Caddy → SSR → backend → NATS → ws-hub → browser): see §Live proof.
- Delete temp cookie jars.
- This commit: AUDIT_WAVE207.md + CLAUDE.md W207 row + new Gotchas + INDEX.md + MEMORY.md trim + N+3 rotation.

---

## Live proof (two browser/curl, dev Docker chain)

Backend + frontend rebuilt with W207 code (`bash scripts/dc.sh up -d --build backend frontend`; both `(healthy)`).
userA = chrome-devtools-mcp (isolatedContext `w207-userA`, programmatic fetch-login + CSRF dance — the RHF login
form ignores DOM-set values, so `fill` doesn't fire a login). userB = curl (CSRF jar). Chat
`019e78e7-c0a9-7470-ae89-4f178e58ba50` (test@university.dev ↔ w203reader@university.dev).

1. **Reply/quote — PROVEN.** userB curl-sent reply `"W207-REPLY-LIVE-A"` (id `019e7f6b-…`) replying to userA's
   `"W204-FLIP-1780166551924"` (target `019e7a31-…`) → appeared **LIVE** in userA's browser (snapshot: "Вы" +
   the `W204-FLIP-…` quote + the reply text). Network: exactly **ONE** `GET /messages` (the initial load,
   reqid=613), **0 refetch** — the quote arrived in the WS `new_message` frame. `POST /ws/ticket [201]` confirms
   the W173 routing fix + a live WS.
2. **Reactor-list — PROVEN.** Hovering the 😢 pill on `W204-FLIP` opened the `role="tooltip"` popover
   "ОТРЕАГИРОВАЛИ 😢 Test User" (Test User = userA, who reacted to their own message in W206). The on-demand
   `GET .../messages/019e7a31-…/reactions?emoji=%F0%9F%98%A2 [200]` (reqid=621, 😢 percent-encoded) fired on
   popover-open + rendered the reactor — the identity can only come from that endpoint.
3. **Live typing — PROVEN both directions.**
   - **RECEIVE:** userB curl-POSTed `/typing` 14× (×0.5s) → userA's browser rendered `"W203 Reader печатает..."`
     (caught at the first poll iteration of a generous 12s overlap; `user_name` resolved to the full_name,
     confirming the profile IS loaded in the REST current_user path — the email fallback was unused defense).
     A first short 3.2s poll had missed it (bash-spawn + delivery latency pushed the frames past the window;
     the indicator self-clears 3s after the last frame).
   - **SEND:** userA's keystroke (React-compatible native-setter + bubbling `input` event on the controlled
     composer) fired `onTyping` → throttled `sendTyping` → `POST .../typing [200]` (reqid=631).

Security constraints honored: no DB-credential / hash edits; two-account verification via existing test accounts +
`POST /auth/login/json`; temp cookie jars deleted; userB curl-only for ASCII (no emoji-body mangling per W206).

---

## Gates (close)

| Gate | Result |
|------|--------|
| `tsc --noEmit` | **0** |
| `npm run lint` (eslint `--max-warnings=0 src tests`) | **0** |
| vitest | **1344 passed / 12 skipped / 0 failed** (W206 baseline preserved — W207 FE is UI wiring; backend tests cover the features) |
| backend `uv run pytest` (FULL, −ws_hub_contract) | **2953 passed / 25 skipped / 0 failed** (W203 §H#5; +8 reply +6 reactors +3 typing vs the pre-W207 suite) |
| W207 test slices | reply 8 · reactors 6 · typing 3 — all pass within the FULL suite |
| OpenAPI contract | **pass** (pure additions hold the superset; no regen — W205 gotcha) |
| alembic `202605300004` up→down→up | **idempotent** (verified) |
| Build × 5 | **BYTE-IDENTICAL** main `index-Dm-a9dmU.js` 180,268 b sha `f5b650e386aeb83565de7d783d30d207a279b41d04a040df76cfad7cff67df8b` + server.js 24,024 b sha `8dae5a45530a14e7b6d870d28cdebb297e9cc2e865e8b16e2d11921e9e6e4977` |
| husky | clean every commit (NO `--no-verify`; SW7 ruff-paren restore was manual, not a hook bypass) |

**Bundle:** NEW W207 baseline. Delta vs W206 (`index-BVE-wSwF.js` 180,274 b): **−6 bytes** main (W193-SW5
route-lazy effect — reply UI + ReactionPill + sendTyping land in the route-lazy `Messenger-*.js` chunk; the
entry shifts only by import-bookkeeping). server.js size identical (24,024 b), content sha changed (W207's
`reply_to` serialize + the new typing/reactors routes are referenced by the SSR module graph). **NOT
byte-identical to W206** — expected for new client-tree code (honest framing).

---

## §Honesty (0–3 OPEN)

- **#0 — live-in-DEV-only (carry-forward).** prod has no ws-hub/nats → all three features flip live only in the
  dev Docker chain; prod self-heals via refetch. The prod ws-hub deploy is a separate infra wave (W208 headline).
- **#1 — W134 §H#2 bundle-delta recording-only (carry-forward).** The −6-byte delta is recorded, not deeply
  investigated (it's route-lazy noise).
- **#2 — W134 §H#10 /messenger Phase 5 SSR by-design (carry-forward).** /messenger stays `ssr: 'data-only'`
  (W161 SW2 by-design — privacy/cache scoping + WebSocket-driven UX).
- **#3 — NEW: reactor-list is forward-looking infra.** Chats are 1-on-1 DMs today (`create_chat` takes one
  `participant_id`; no group-creation path), so "who reacted" is low-value until group chats exist. Built **full**
  per user direction (desktop hover + keyboard focus + mobile long-press). Reply notifications (notify the quoted
  author) are deliberately OUT of scope (a future wave; would touch `MessageSent` + the outbox). `dispatcher.py`'s
  typing handler is left as-is (unused by the frontend, harmless; dedupe later).

---

## (z) discoveries

- **(z)#1 — mypy > the green suite (SW5).** mypy caught `User.full_name`/`avatar_url` (they're on `UserProfile`
  via `User.profile`, `lazy="noload"`) — a real runtime bug the 2949-passing reactor tests would have green-lit
  (they mocked `.full_name` directly). Fixed at the source (selectinload + guarded access + a no-profile test).
- **(z)#2 — RZ-30-05 re-confirmed (SW7).** venv ruff 0.15.12 `format` (write) STRIPS except-parens →
  Python 2 SyntaxError. Caught by FULL-pytest collection. Use `--check` / the pinned hook; never `uv run ruff format`.
- **(z)#3 — React Compiler Babel transform stricter than the eslint plugin (SW9).** Build failed where SW6's tsc +
  eslint + vitest all passed; `"use no memo"` + the paired eslint-disable (W199 / FIX-54-01) is the fix.
- **(z)#4 — ephemeral-broadcast verification is timing-sensitive (SW9).** The `TypingIndicator` self-clears 3s
  after the last frame, so a single short poll races bash-spawn + NATS→ws-hub→browser latency. The fix is a
  *generous overlap*: a producer loop emitting frames over several seconds while the consumer poll runs long
  enough to cover spawn latency + the producer window + one indicator lifetime.

0 NEW anti-patterns (the 14-pattern register is stable post-W159 #15 archival).

---

## W208 candidates

- **Prod ws-hub deploy** (closes §H#0 live-in-DEV-only across W203–W207) — the highest-value next step.
- Reply notifications (notify the quoted author) — touches `MessageSent` + the outbox.
- `dispatcher.py` typing-handler dedupe (it's dead code now that the frontend POSTs the REST endpoint).
- Group-chat creation path (would make reactor-list high-value).
- `mark_single_message_read` cleanup (dead since W203 SW4).
