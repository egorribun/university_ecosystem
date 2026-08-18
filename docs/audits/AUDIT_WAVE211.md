# Wave 211 — Forwarding (F) end-to-end + Group UI (G4: display + create + manage)

**Date:** 2026-06-01
**Branch:** `egorribun`
**Scope (user):** Q0 = **G4 + F**; sequence = **F first, then G4** (W211→W212 span accepted); forward model = **snapshot-copy** (privacy-safe); forward depth = **single message** (endpoint accepts 1..N for forward-compat).
**Wave type:** 71st consecutive wave with brainstorming + Phase 1 Explore → Plan agent → Phase 3 verify-before-write + W141 anti-pattern discipline.
**Outcome:** **F complete + live-verified** (the guaranteed deliverable). **G4: display + create + manage** (groups fully usable). **SW11 (seen-by-N read marker) + combined FE-UI live smoke carried to W212** per the plan's accepted span.

---

## Headline

The corporate-messenger program's group BACKEND was complete (W209 identity + membership, W210 per-recipient read receipts + group-notification context); the group FE api-surface shipped in W209 but was **unused** (no `chat_type === "group"` branch existed anywhere in the FE). W211 ships:

1. **Forwarding (F), end-to-end** — a snapshot-copy message into another chat (backend + single-message UI), **PROVEN LIVE** cross-user through the real Docker chain.
2. **Group UI (G4) — display + create + manage** — group label/avatar everywhere a chat renders, a create-group mode, and a full member-management panel (rename + add + remove + leave).

11 commits: F = SW1-SW6 (W210 session) + SW7 tests + the attribution fix (`d37c21d34`); G4 = SW8 (`b477db9c6`) + SW9 (`eee3b4154`) + SW10 (`8218e44fc`) + this close.

---

## F — Forwarding (snapshot-copy), end-to-end

**Why snapshot-copy (the security one-way-door):** a forwarded message lives in the DEST chat, whose viewers may not be participants of the SOURCE chat. A self-FK the FE dereferences to render source content is a cross-chat BOLA leak (W207's reply preview is safe *only* because `message_exists_in_chat` guarantees the quote is in the SAME chat — an invariant forwarding cannot hold). So forwarding COPIES content + attachments into a fresh dest message + a denormalized `forwarded_from_name` that never links back.

| SW | Commit | What |
|----|--------|------|
| SW1 | `56bcc07ec` | `Message` += `forwarded_from_name String(128)` + `forwarded_from_chat_id`/`forwarded_from_message_id` (FK SET NULL; only the message-id indexed). Alembic `202605300007` (down_revision `202605300006`; idempotent; **verified LIVE up/down/up against real PG**). **AmbiguousForeignKeysError fix** (caught by `configure_mappers()` after the model edit — the Plan flagged only the second-self-FK `replied_to`, but `forwarded_from_chat_id` is also a second `Message→chats.id` FK breaking `Chat.messages`/`Message.chat`): added `foreign_keys="Message.reply_to_message_id"` to `replied_to` + `foreign_keys="Message.chat_id"` to both `Chat.messages` and `Message.chat`. |
| SW2 | `292a5fdfa` | `MessageDTO += forwarded_from_name` (silent-gatekeeper) + `MessageResponse += forwarded_from_name` + `ForwardMessages{source_chat_id, message_ids: list[UUID] min_length=1 max_length=FORWARD_MAX_MESSAGES(50)}`. |
| SW3+SW4 | `a39828725` | `ChatMessageDispatcher.forward_messages(dest, user, source, ids, locale)` — **dual-chat authz-first**: dest get_by_id+ensure_exists+check_participant (403), then source check_participant (403 — the cross-chat-leak gate, BEFORE any source read), then per-id `message_exists_in_chat` (404, ALL before any create); `len(sources)!=len(ordered_ids)` defensive guard; per-source `Message(chat_id=dest, sender_id=forwarder, content=src.content, forwarded_from_*…)` + `create_message` + `record_event(MessageSent)` + attachment copy; one timestamp bump + single commit; reload via `get_last_messages`. NEW route `POST /chats/{dest_chat_id}/forward`. `serialize_message` += scalar `forwarded_from_name`; the 3 field-by-field `MessageResponse` sites set it (the 2 spread sites auto-carry). |
| SW5 | `d3d994437` | FE `chatApi.forwardMessages(destChatId, sourceChatId, messageIds)` + `Message += forwarded_from_name?` + vitest (coverage-included `src/api/`). |
| SW6 | `48604bcbf` | Forward button on every bubble → NEW `ForwardModal` dest-picker (NewChatModal a11y) + "Forwarded from X" chip + `forwardMutation` + handlers + i18n. |
| SW7 | `cdda32f08` | NEW `tests/test_chat_forwarding.py` (9: cross-chat-leak 403, not-dest-participant 403, source-not-in-source 404, snapshot copies content+attribution+attachment, reactions-not-copied, multi-forward N→1-commit, dedupe) + 3 integration tests in `test_chat_api.py`. |

### F attribution fix (`d37c21d34`) — surfaced by the live verify

The first live two-account forward returned `forwarded_from_name: None`. Root cause (W205 §H#5 / W210 lesson): `forward_messages` read `src.sender.full_name` from `get_last_messages`, but `MessageDTO.sender` (`ChatParticipantDTO`) maps from the bare `User` (`selectinload(Message.sender)`), and `full_name` lives on `UserProfile`, NOT `User` (the W207 SW5 gotcha) — so it is structurally `None`. The unit test passed only because its mock DTO had `sender.full_name` pre-set.

Fix (within-SW7 SAME-mechanism per W138 L#1 — making forward attribution actually work, like W205 SW9's post-live-run fixes):
- NEW `ChatRepository.get_user_display_names(user_ids)` — batched, profile-loaded (`{id: profile.full_name or None}`; ONE SELECT for all distinct senders, no N+1).
- `forward_messages` resolves names via this batch + `sender_names.get(src.sender_id)`.
- `test_chat_api` snapshot integration test: `source_peer full_name="Source Author"` + assert `forwarded_from_name == "Source Author"` — guards the fix at the REAL-repo level (the missing assertion that let the bug ship).

### F LIVE verification (real Caddy → SSR → backend → PG chain; CSRF dance; seeded accounts)

- **Forward 200** + content snapshot `"W211 from-anna snapshot"` + **`forwarded_from_name: 'Анна Петрова'`** (the ORIGINAL sender, anna — through the real PG profile join), while `sender_id` is the forwarder (test). The snapshot-copy attribution is correct: *"new message by test, Forwarded from Анна Петрова."*
- **HEADLINE cross-chat-leak 403** — userC (in dest, NOT in source) forwarding from source → 403 (the security one-way-door blocks it).
- Integration tests (real repo + SQLite): 403 / 200+"Source Author" / 404.
- **FULL pytest** (W203 §H#5 — forward touches the send/broadcast hot path): **3000 passed / 25 skipped / 0 failed** (W210 2988 + 12 new = 3000, no-cascade).

---

## G4 — Group UI (display + create + manage)

| SW | Commit | What |
|----|--------|------|
| SW8 | `b477db9c6` | NEW `chatDisplay.ts` (`chatDisplayInfo(chat, currentUserId, t)` — single source of truth branching DM vs group) + `GroupAvatar.tsx` (Lucide Users in the `--messenger-send-bg` violet→pink gradient + CONSTANT `--color-white` glyph — theme-independent gradient, the W175 `--text-on-footer` rationale). `Contact += isGroup?/memberCount?`; contacts memo branches via `chatDisplayInfo` (typed `Contact[]` so the inferred prop shape keeps the optional fields); `activeChatDisplay` exposed. ContactList GroupAvatar glyph for group rows (no photo, no presence dot). ChatArea header: group → GroupAvatar + name + "{n} members" (no presence pulse); DM → prior photo + presence; `onOpenGroupInfo` forward-compat prop. i18n: `group.untitled`, `group.members`, `unknownUser` (migrated the prior hardcoded literal). +1 group-rendering test. |
| SW9 | `eee3b4154` | NewChatModal DM/Group mode toggle (only when `onCreateGroup` wired → DM-only otherwise, backward-compatible) + group-name TextField + removable selected-member chips + multi-select rows (Check indicator + `aria-selected`) + create-group CTA disabled until name + ≥2 selected (backend ≥3 total incl. auto-included creator) + min-members hint; resets on close. `createGroupMutation` + `handleCreateGroup` + `isCreatingGroup`. i18n: newGroup, modeToggle/modeDirect/modeGroup, groupName, selectMembers, removeMember, createGroup, creatingGroup, error.minMembers. +3 tests (toggle visibility, group UI, full create flow). |
| SW10 | `8218e44fc` | NEW `GroupInfoPanel` (mirrors ProfileModal a11y: focus-trap, role=dialog + aria-modal, Escape, matte, reduced-motion, 44px close), opened from the group header. Authz mirrors the backend (W209): rename + add-member = any member; **KICK = owner only** (`created_by === currentUserId`); **LEAVE = always**. `renameChat`/`addParticipant`/`removeParticipant` mutations (each invalidates `["chats"]` + `["chats", id]`; self-removal → close panel + navigate `/messenger`); kick/leave route through `confirmDialog`. MessengerFeature.test: mock ForwardModal + GroupInfoPanel (the latter uses `useQuery` → would need a QueryClient) + sync `makeController` with the SW6/SW8/SW9/SW10 fields. NEW GroupInfoPanel.test (+5: owner-gating, leave, rename). i18n: renameGroup, addMember, leaveGroup, groupOwner, memberYou, removeMemberConfirm/Title, confirmRemoveMember, confirmLeaveGroup. |

---

## Gates (end of wave)

- **FULL `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py`**: **3000 passed / 25 skipped / 0 failed** (W210 2988 + 12 = 3000, no-cascade arithmetic — W203 §H#5).
- OpenAPI contract: passes (new route + field hold the superset, no regen).
- tsc 0; `npm run lint --max-warnings=0` 0; i18n parity 18/18.
- **`npm run test:ci`**: **1385 passed / 12 skipped / 0 failed**; coverage **Funcs 70.28% ≥ 70%** (gate), Stmts/Lines 79.41%, Branch 72.88%.
- **Build × 3 BYTE-IDENTICAL**: main JS `index-BzDbycBp.js` **180,274 b** sha `371266a1db4abb8e24b505d585a952a4b368ca28a8837f140acf1444d3c38bd2` × 3 + server.js **24,024 b** sha `b95af1ab35df45c547d033999b11919e1f8d81322c4983e366a8bf4a4145958b` × 3. **+6 b vs W210** (the F+G4 client code lives in the route-lazy `Messenger-j_QGE7HF.js` chunk = 135,518 b; the main entry shifts only by import-bookkeeping per W193 SW5/W202). **NOT byte-identical to W210** — expected for real FE runtime code, not a regression.
- Tree-shake invariant ✓ (0 `lhci-mock-user` in PROD); SW IIFE invariant ✓ (`"use strict";(()=>{`).
- husky pre-commit clean on every commit (NO `--no-verify`).
- LIVE: F forward 200 + snapshot + attribution "Анна Петрова" + cross-chat-leak 403 (real Docker chain).

---

## §Honesty probe

**OPEN (carry-forward, by-design):**
1. **live-in-DEV-only** — the prod compose + k8s have no ws-hub/NATS; live messenger features (forward broadcast, read receipts) flip live only in dev. Prod self-heals via refetch. The prod ws-hub deploy is user-deferred (W209/W210 carry).
2. **W134 §H#2** bundle-delta recording-only (moot here — main JS +6 b, honestly framed).
3. **W134 §H#10** /messenger Phase 5 SSR by-design (`ssr: 'data-only'` per W180 SW3).

**NEW W211 caveats (honest, plan-sanctioned deferrals):**
4. **SW11 (seen-by-N read marker) DEFERRED to W212** per the plan's accepted W211→W212 span ("the W212 opening prompt carries the G4 remainder (e.g. member panel / seen-by-N)"). Groups are fully usable (create + display + rename + add/remove/leave); the "Seen by N of M" marker (building on W210's per-recipient read receipts) is additive.
5. **FE-UI live smoke DEFERRED to W212** — the running frontend Docker image is stale (pre-W211; no forward UI, no group UI). A combined live smoke (forward UI + group create/manage + seen-by-N) needs a frontend rebuild (W137 Windows-wall risk on a cold rust-crypto WASM compile), so it folds into W212 (which rebuilds the frontend for SW11's live verify anyway) — ONE rebuild, not two. The backend forward is live-verified; the FE is comprehensively unit-tested (F: 20 chat-api + 9 forward + 3 integration; G4: 177 messenger-slice incl. GroupInfoPanel 5 + NewChatModal group 3 + controller group 1).
6. **G4 add-member is forward-looking for non-DM groups** — chats remain creatable as DMs or groups; the member panel's add/remove/leave are real but exercised against the group create path (SW9), not yet against a long-lived populated group (W212 live smoke).

**1 NEW (z) discovery** — the **MOD-30-01 `lazy=noload` gate is comment-blind** (CI-only, surfaced post-push, fixed in the close-fix commit): the gate greps `relationship\s*\(` across the whole file, so the SW1 comment `…never traversed by a relationship (privacy).` matched the literal `relationship (` → flagged as a `relationship(...)` call without `lazy=`. Local gates were GREEN (the gate runs inside the "Validate docker-compose.yml" CI job, NOT the husky chain — same CI-surfaced class as the W210 blockers). Fixed by rewording the comment to "a mapped link (privacy)" + a CLAUDE.md Gotcha; reproduced the gate logic locally (`ci.yml:210-251` snippet) → passes. The AmbiguousForeignKeysError (SW1, `configure_mappers()`) + the attribution-None bug (SW7, live verify) were within-SW SAME-mechanism fixes per W138 L#1, NOT (z). **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

**W141 compliance:** #1 (each SW 1-iter; the attribution fix + the tsc/test sub-fixes are within-SW SAME-mechanism, not pivots) + #3 (verify-before-write caught the second-chats-FK ambiguity, the profile-not-on-User attribution path, the `useMemo<Contact[]>` prop-inference, the `getByLabelText` listbox-dupe, the MessengerFeature QueryClient coupling — all before/at commit) + #4 ("GREEN" attributed only after captured gate output — FULL pytest 3000, test:ci 70.28%, Build × 3 sha; F live-verified, FE-UI smoke honestly deferred) + #15 (every commit clean husky).

---

## W212 carry

- **SW11 (seen-by-N)** — `applyGroupReadFrame` in useChatWebSocket (upsert `chat.read_receipts`) + extend `case "read"` + `seenByCount` in chatDisplay + `readByCount`/`readByTotal` on UiMessage + ChatWindow "Seen by N of M" group branch + i18n `seenByGroup` + LIVE read-receipt verify (W210 pattern).
- **Combined FE-UI live smoke** — rebuild frontend once → chrome-devtools/Playwright smoke of the forward UI + group create/manage + seen-by-N.
- Then Track **A** (attachment perfection) / **S** (pgvector message search) / **F**-extras (multi-select forward UI).
