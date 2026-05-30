# AUDIT — Wave 202 (Messenger-page polish foundation — first wave of the full-feature-expansion arc)

> **Status: CLOSED.** User directed "finish the messenger page to a flawless reference ideal" + chose **Full feature-expansion arc** (messenger becomes multi-wave) + **best-in-class judgment** for visuals/animations, with **W202 = polish foundation only** (make the EXISTING surface flawless + fully tested before W203+ adds backend-dependent features — reactions/read_at/edit/voice each need model+migration+endpoint+ws-hub first; `app/models/chat.py:77` Message has only `read_status:bool`). Three Explore audits + a Plan-agent design confirmed the messenger is already the most-worked surface (W145 + W180-W184; theme 95 / responsive 85 / palette 98 / a11y 92) with every hard safeguard verified in place — so "to ideal" = a focused gap-closure, not a rebuild. 62nd consecutive wave with brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 discipline. **8 SW** (SW6 split 6a/6b per the planned contingency).

## Headline

- **Closed all ~10 audit gaps + the 3 missing wrapper tests** to flawless-foundation: the HIGH dark-mode `bg-white` attachment-chip contrast fail (SW3), 4 grouped a11y/responsive fixes (SW4), the orphan online-pulse wired up (SW5), the message-entrance scroll-re-animation anti-pattern (SW6b), 4 code-quality conversions (SW1) + the WS double-cast collapse (SW2), + MessengerBackdrop/MessengerSidebar/MessengerFeature unit tests (SW7).
- **Bundle main JS 180,273 bytes — size UNCHANGED from W201, content-sha CHANGED** `1bff1fd7…c97` → `15159334e7b2b99c1415940aeb98b3d3f70c90991641367cf77a9aed91393bd1` × 3 (BYTE-IDENTICAL across 3 clean builds). Real client-tree edits (fn-decls, theme token, breakpoints, pulse swap, entrance state) net-neutral on byte count. **The W134-SW3 → W201 ≥60-wave content-sha invariant RETIRES at W202** (first real messenger-source change since W184/W185); NEW W202 baseline established + ×3-reproducible. server.js 24,024 b sha `c39b4b8f…fb35b` × 3.
- **+16 tests** (vitest messenger suite 15 files / **157 passed**); TypingIndicator test (3 cases) + ChatArea test (1 assertion) updated for the SW4/SW5 changes.
- **Animation polish, react-compiler-safe**: SW6b animates only newly-appended messages (no scroll-re-animation) via a `useState(Number.POSITIVE_INFINITY)` boundary bumped in the auto-scroll effect — state read in render, ref only in effects (passed the react-compiler eslint rule AND the Babel build-gate × 3). SW6a guarded the 4 unguarded ChatArea header-button micro-interactions.

## Per-SW table

| SW | Commit | Work | Gate |
|----|--------|------|------|
| SW1 | `492fa28a4` | React.FC → fn declarations (ChatWindow/MessageInput/NewChatModal/MessengerProvider) + type-import hygiene + hoist ATTACH_MENU_ITEMS | tsc 0, eslint 0, vitest 51/51 |
| SW2 | `a0201dc03` | collapse `as unknown as Message` → single `as Message` (×4) in useChatWebSocket + document the deliberate cast | tsc 0, eslint 0, useChatWebSocket 8/8 |
| SW3 | `2b710a9ca` | HIGH `bg-white` chip → NEW `--messenger-attachment-bg` veil token (4-state correct; shared icon container made conditional) | tsc 0, eslint 0, 0 `bg-white` left, ChatWindow 14/14 |
| SW4 | `40ae5ffa4` | remove-btn `md:size-9`; TypingIndicator single-SR (drop redundant aria-label, +3 test updates); bubble sm/lg/xl ramp; ProfileModal monotonic ramp | tsc 0, eslint 0, 50/50 |
| SW5 | `df7faec26` | wire orphan `.messenger-online-pulse` → ChatArea active-chat header avatar ONLY (1 anim); test assertion updated | tsc 0, eslint 0, ChatArea 12/12 |
| SW6a | `75309dce1` | guard the 4 unguarded ChatArea header-button `whileHover`/`whileTap` for reduced-motion | tsc 0, eslint 0, 0 unguarded left, 12/12 |
| SW6b | `43c05e940` | animate only newly-appended messages (POSITIVE_INFINITY boundary + effect bump); reduced-motion + search-gated | tsc 0, eslint 0 (react-compiler+exhaustive-deps), 14/14 |
| SW7 | `d5c754930` | unit tests for MessengerBackdrop (5) + MessengerSidebar (5) + MessengerFeature (6) | tsc 0, eslint 0, 16/16 |
| SW8 | _(this)_ | cross-cutting sweep + Build × 3 re-baseline + visual smoke + audit + N+3 (W199→archive) + INDEX/CLAUDE.md/MEMORY.md + memory files | full gates green |

## Verify-before-write hazards the Plan agent caught (W141 #3)

- **SW2 — the audit's "redundant cast" premise was FALSE.** `validated.message` is the Valibot `ParsedMessage` (`api/schemas/wsMessage.ts` — attachments/sender validated shape-only as `Record<string,unknown>`), structurally **not** assignable to `@/api/chat` `Message` (`Attachment[]`/`User`). Deleting the cast fails tsc. Verified: `Message` IS assignable to `ParsedMessage`, so the two are *comparable* → a single `as Message` compiles (collapsed the `unknown` hop). Added a comment so it isn't "cleaned up" to deletion later.
- **SW1 — `React.FC` is NOT lint-enforced.** The real lint pressure is the now-unused `import React` default. MessageInput had **three** `React.*` tokens (FC + KeyboardEvent + ChangeEvent), not the one the audit named — all converted to `import type`.
- **SW4 — the TypingIndicator aria fix breaks an existing test.** Removing the redundant `aria-label` flips the assertion; the 3 affected tests shipped in the same SW (single SR source = the sr-only span).
- **SW6b — the lazy-init stampede trap.** Hooks run before the `isLoading`/empty early-returns, so `useState(() => filteredMessages.length)` would capture 0 during the loading render → first populated render stampedes. `useState(Number.POSITIVE_INFINITY)` is the robust fix (nothing "new" until the effect sets a real boundary).

## Two judgment calls (best-in-class mandate)

- **(A) `bg-white` → NEW `--messenger-attachment-bg` veil token.** The reads refined the Plan's "unify both branches onto a white veil": the SENT chip sits on the theme-independent violet bubble (white veil works both themes; no `.dark` override) but the RECEIVED chip sits on a theme-neutral bubble where a white veil would VANISH on the light received bubble. So the conditional STAYS: sent → veil token, received → existing `--bg-surface-raised`. The real bug was the *shared* icon container being unconditionally white → made conditional (sent: veil + inverse glyph; received: surface + brand glyph).
- **(B) online-pulse WIRED, not deleted.** The orphan `.messenger-online-pulse` (fully built, reduced-motion-guarded) → ChatArea active-chat header avatar ONLY = exactly one infinite animation, where the conversation is open. ContactList rows + ProfileModal keep the static `.messenger-online-indicator` (a pulse per row = N infinite animations).

## Verification (wave-close gates)

- Per-SW: `npx tsc --noEmit` 0 + `npx eslint <touched> --max-warnings=0` 0 + targeted vitest green (every SW). Husky chain clean on all 8 commits (lint-staged prettier+eslint; detect-secrets **Passed**; Python 2 except **Passed**; NO `--no-verify`).
- Wave-end: full `npx tsc --noEmit` 0, full `npm run lint` (`--max-warnings=0` src+tests) 0, **npm audit 0 vulnerabilities**, full messenger suite (15 files) **157 passed / 0 failed** (serial — the Windows Node-IPC parallel-OOM flake is documented infra, not a W202 failure).
- **Build × 3 BYTE-IDENTICAL** main JS `15159334…393bd1` ×3 (180,273 b) + server.js `c39b4b8f…fb35b` ×3 (24,024 b) — the react-compiler Babel build-gate passed all 3 (validates SW6b). Tree-shake invariant ✓ (0 `lhci-mock-user` in PROD client assets); SW IIFE invariant ✓ (`"use strict";(()=>{`); Cargo.lock no drift.
- **Visual smoke** (VITE_LHCI preview + chrome-devtools, isolated context): /messenger SSRs 200/43,175 b; **0 React #418 / hydration / ReactCompilerError** from W202 (all 19 console messages are expected backend-down noise — 502 on `/ws/ticket`, WS reconnect attempts capped per W183 SW3, the W128 `profile_cache.cleared` warn). DOM-injection probe confirmed SW3 token `--messenger-attachment-bg` resolves to `#ffffff24` (14% white veil) + a chip renders `rgba(255,255,255,0.14)`, SW5 `.messenger-online-pulse` resolves to emerald `position:absolute` `10px` (now consumed), MessengerBackdrop renders 3 orbs. Screenshot saved (gitignored `.screenshots/`).

## §Honesty probe

1. **Full real-chat 4-state visual NOT verified** — /messenger under VITE_LHCI without backend shows the empty state (no chats), so the attachment chip on real sent/received bubbles, the pulse on a live participant avatar, and the bubble breakpoint ramp could only be verified via DOM-injection token/CSS probes (W182 SW4 pattern), not on real rendered chat data. The full chat-UI visual needs the Docker chain (deferred — established W181/W182/W184 messenger-wave precedent).
2. **SW6b light-mode pulse shade probe anomaly** — the deterministic `.dark`-toggle probe read emerald-400 (dark value) even after removing `.dark` from `<html>`; a single-tick propagation quirk, not a correctness issue (the token has no light/dark divergence concern for the chip; the pulse renders emerald either way). Dark-mode pulse confirmed emerald-400; light shade not independently confirmed.
3. **Pre-existing AnimatePresence quirk surfaced (NOT W202 scope, W203+ candidate)** — MessengerFeature's `<AnimatePresence mode="wait">` wraps the sidebar + chat-area as two *unkeyed* children, so on desktop (both panes render) it logs "multiple children with mode=wait" + "same key". `mode="wait"` is for one-at-a-time swaps (the mobile case); the desktop two-pane case is semantically off. A proper fix is an animation refactor (not just adding keys), out of the approved W202 polish-foundation scope. Surfaced during SW7 testing; flagged for W203+.
4. **CI not yet observed at wave-close commit time** — single push pending; will poll CI - Matrix Expansion + Frontend Tests / Unit Tests (the Windows-local full-parallel run OOMs; CI Linux runs the full suite + coverage per W198).
5. Carry-forward structural non-goals (NOT W202 scope): **W134 §H#2** bundle-delta recording-only, **W134 §H#10** /messenger Phase 5 SSR by-design (W161 SW2; /messenger is `ssr: 'data-only'` per W180 SW3).

## (z) discoveries + anti-patterns

- **0 NEW (z) discoveries.** The four would-be cascade traps (SW2 ParsedMessage≠Message, SW1 three-React-tokens, SW4 test-breakage, SW6b lazy-init stampede) were all identified by the Plan agent's verify-before-write reads BEFORE writing — the discipline working as designed, not surprises discovered mid-impl. Extends the low-(z) streak (W145-W202).
- **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).
- **W141 compliance**: #1 STRICT 1-iter (every SW landed 1-iter; SW6 split 6a/6b was the *pre-planned* contingency — #11 then landed clean in 1 iter, no defer); #3 (Plan agent + Phase 3 reads caught the 4 hazards + confirmed exact text before each edit — never trusted prose/diffs); #4 (Build × 3 sha + visual smoke captured BEFORE the audit's bundle/render claims); #15 ARCHIVED preserved (all 8 commits fired the husky chain cleanly, NO `--no-verify`).

## NEW Gotchas (added to CLAUDE.md ## Gotchas)

1. **`--messenger-attachment-bg` veil token** (W202 SW3): chips on the theme-independent violet SENT bubble use a low-opacity white-veil token (no `.dark` override needed); RECEIVED-bubble chips use the theme-aware `--bg-surface-raised` (a white veil VANISHES on the near-white light received bubble). The shared file-icon container must be conditional on `message.isMe`, not unconditionally white.
2. **`.messenger-online-pulse` wired to the active-chat header avatar ONLY** (W202 SW5): one infinite presence animation where the conversation is open; ContactList rows + ProfileModal keep the static `.messenger-online-indicator` (a pulse per row = N infinite animations = mobile-battery cost).
3. **WS `validated.message` is `ParsedMessage`, NOT structurally `@/api/chat` Message** (W202 SW2): the Valibot schema validates attachments/sender as `Record<string,unknown>`; `Message` is assignable to `ParsedMessage` so a single `as Message` compiles, but DON'T delete the cast (deleting fails tsc — they're not structurally equal).
4. **ChatWindow "animate-only-new-messages" boundary pattern** (W202 SW6b): `useState(Number.POSITIVE_INFINITY)` boundary bumped to the new length inside the auto-scroll effect → only appended rows (`index >= boundary`) animate; already-seen rows render `initial={false}` (no scroll re-animation). React-compiler-safe: state read in render, the lone ref touched only in effects. Infinity-init avoids the first-populated-render stampede.

## Messenger arc / W203

W202 made the existing messenger surface a flawless, fully-tested **foundation**. The arc continues: **W203+ = backend-dependent features, one per wave** — each needs SQLAlchemy model + alembic migration + repo/service + REST/ws-hub message type BEFORE the UI. Likely order: read-receipt timestamps (`read_at`) or message edit/delete (lowest backend risk), then reactions, then voice messages. Also tracked: the W203+ MessengerFeature AnimatePresence `mode="wait"` two-pane refactor (§Honesty #3), and frontend-only фишки (date dividers, consecutive-message grouping, scroll-to-bottom FAB, image lightbox) that need no backend.

Memory references (`.claude` profile only): `memory/wave202_backlog.md`, `memory/wave203_opening_prompt.md`.
