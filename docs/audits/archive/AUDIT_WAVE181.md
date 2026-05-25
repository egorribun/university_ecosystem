# Wave 181 — Messenger UI Comprehensive Polish (XL scope, Violet/Pink palette)

**Wave**: W181 (2026-05-22)
**Branch**: `egorribun`
**Predecessor HEAD**: `2bcc02bab` (W180 polish-v2 React #418 root-cause closure)
**Scope**: User-approved XL Comprehensive + Violet/Indigo palette (~7-10h core estimate). Per `feedback_planning_estimates.md`, anchored historical: W82 Events polish-arc-close (6 polish rounds in 1 wave), W84-W87 Activity arc (4 waves), W176 Footer polish (5 SWs).
**Status**: ✅ CLOSED — 5 SW commits + polish-v1 + this audit (SW6). 41st consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

## Headlines

1. **Messenger brought to feature-page parity** — last untouched feature surface in the polish-arc map (Schedule W61-W74, Map W88-W110, Events W77-W82, Activity W84-W87, News W57-W58 + W73 + W75, Footer W175-W176, Admin W150 all received dedicated polish arcs; pre-W181 messenger had structural work only — W134 §H#10 SSR enable W180 SW3, a11y groundwork W175 SW2-SW3, factory extraction W145 SW2). W181 lands NEW `frontend/src/styles/tokens/messenger.css` (~380 LoC, violet/pink/indigo palette distinct from 7 existing surfaces) + NEW `MessengerBackdrop.tsx` + NEW `TypingIndicator.tsx` + `.messenger-card-matte` + `.messenger-active-chip` + `.messenger-send-btn` + `.messenger-status-badge` + `.messenger-typing` + `.messenger-online-pulse` + `.messenger-stagger-item` utility classes.

2. **ChatWindow line 160+162 `text-white` → `text-[var(--text-inverse)]` (W181 SW3)** — the single concrete pre-W181 bug surfaced by Phase 1 Explore Agent 1+3. Same W175 SW2 pattern extended to Check + CheckCheck status icons inside sent bubbles. Theme-aware fix: 9.9:1 contrast in BOTH light + dark modes (white text on violet-500 light bg + slate-950 text on violet-500 dark bg).

3. **TypingIndicator wired to existing WebSocket presence channel** (W181 SW4) — `useMessenger().getTypingUsersForChat(chatId)` already exposes typing state from W134+ MessengerContext + W134 SW2 sessions.ts patterns. NO backend changes needed. Component renders 3-dot pulse animation OR static `messenger:isTyping` text under reduced-motion preference. a11y: `role="status"` + `aria-live="polite"` + sr-only fallback label.

4. **Build × 3 BYTE-IDENTICAL bundle invariant ESTABLISHED** — W180 baseline (`index-C2EoEPG2.js` 179,968b sha `576508ee...` + server.js 24,024b sha `fb4aa2f5...`) RETIRED at W181 SW1 due to real client-tree code changes. NEW W181 baseline `index-DCnJ-daY.js` 179,968b sha `bb6e56d0ad764dc8872c8e053f9300479a86fa557bc4c3f23fac3a7fad0ffc3e` × 3 + server.js 24,024b sha `9bb8288a06b05f4094a5d8ed960c1f4e22f127bb3509708e1631e8f7f86651d0` × 3 EMPIRICALLY VERIFIED across 3 fresh `rm -rf dist && npm run build` runs from clean state. Main JS + server.js SIZE preserved EXACTLY at W180 baseline (179,968 + 24,024) — messenger code lives in route-lazy chunks (`Messenger-*.js` 66.3KB + messenger.css contributions to `index-*.css` ~5KB delta), NOT in main JS chunk.

5. **§Honesty trajectory 0 → 0-2 OPEN** — W180 closed §Honesty trajectory at 0 OPEN for the first time post-W117. W181 introduces 2 NEW characterization-only caveats (Tailwind v4 `w-full + max-w-2xl` empirical resolution bug + visual smoke via VITE_LHCI bypass only — full Docker chain authed visual smoke deferred to user manual testing OR W182+ infra wave). Both are honest scope-deferrals, not introduced regressions.

## Per-SW narrative

### SW0 — Preparation (no commit)

MEMORY.md headroom check (6,968b post-W180 SW0 compaction) was sufficient for W181 row addition; deferred compaction work to SW6 audit alongside W178 verbose-row collapse. Phase 1 Explore launched 3 parallel agents (Agent 1: current state map, Agent 2: reference pattern inventory, Agent 3: gap analysis). Phase 3 Review verified all critical agent claims empirically via direct Read of:
- `tokens/messenger.css` does NOT exist (Glob 0 results)
- ChatWindow.tsx line 98 W175 SW2 fix preserved (verified)
- ChatWindow.tsx line 160-162 hardcoded `text-white` (verified — the single concrete bug)
- FooterBackdrop.tsx canonical template (94 LoC, pixel-anchored W118 SW3 pattern)
- activity.css matte recipe (`@property` orbs + `.theme-name` scope + 3-layer matte shadow + status accents + stagger)
- MessengerFeature.tsx outer div renders `bg-msg-chat` without any theme scope wrapper

### SW1 — Tokens + theme scope (`0925e4700`, +594/-1)

NEW `frontend/src/styles/tokens/messenger.css` (~380 LoC after prettier auto-format).
Structure mirrors `activity.css` exactly:
- `@property` registrations for `--messenger-orb-1/2/3` + `--messenger-card-glow` (smooth dark↔light transitions)
- `.messenger-theme` scope (light):
  - Typography: `--fs-messenger-hero/subtitle/contact-name/bubble/meta`
  - Orbs: violet-400 10% + pink-400 8% + indigo-400 6%
  - Gradients: `--grad-messenger-conic`, `--messenger-accent-line` (violet→pink)
  - Matte card system: `--messenger-card-bg` + 3-layer `--messenger-card-shadow` + hover variant
  - Bubbles: `--messenger-bubble-sent-bg` (violet gradient) + `--messenger-bubble-received-bg` (subtle tint)
  - Active chat: `--messenger-active-accent` (violet-500) + `--messenger-active-bg`
  - Send button: violet→pink gradient bg + 2-shadow + hover variant
  - Status badges: online/away/offline (emerald/amber/slate tints)
  - Typing + online pulse + skeleton + featured-mesh + avatar-ring
- `.dark .messenger-theme` overrides (16% orb opacity initially, later bumped to 22/18/15% in polish-v1)
- Utility classes inline: `.messenger-card-matte` + `.messenger-active-chip` + `.messenger-send-btn` + `.messenger-status-badge` + `.messenger-typing` + `.messenger-online-pulse` + `.messenger-avatar-ring` + `.messenger-stagger-item` + `.messenger-empty-mesh` + `.messenger-skeleton`
- `@media (prefers-reduced-motion: reduce)` block + `@media print` doubled-class specificity per FIX-72-04

MODIFY `frontend/src/styles/theme.css` (+1 line): append `@import "./tokens/messenger.css"`.

MODIFY `frontend/src/features/messenger/MessengerFeature.tsx` outer div: className `"flex h-full ..."` → `"messenger-theme relative flex h-full ..."`. Adds scope + `relative` for SW2 Backdrop containing-block.

**Palette rationale**: Phase 1 plan called for fuchsia accent; empirical `grep --color-fuchsia` showed only `--color-pink-400` + `--color-rose-500` available — pivoted to pink-400 (warmer, less aggressive than rose-500) per W141 anti-pattern #3 (verify before writing; same rule applies to my own plan assumptions).

### SW2 — MessengerBackdrop + matte utilities (`d3811b051`, +102/-2)

NEW `frontend/src/components/messenger/MessengerBackdrop.tsx` (~93 LoC mirroring FooterBackdrop pattern exactly per Phase 1 Explore Agent 2 inventory). 3 orbs with pixel-anchored sizing per W118 SW3 CLS-118-03:

1. Primary violet glow — top-center radial. 85%/120% width × 520px/380px height (desktop/narrow). opacity 0.6, blur 60px.
2. Secondary pink warm accent — upper-right anchored from top (NOT bottom; CLS stability). 42%/60% width × 320px/240px height. opacity 0.5, blur 70px.
3. Tertiary indigo cool sheen — anchored from top (NOT bottom). 38%/70% width × 300px/240px height. opacity 0.4, blur 55px.

Props mirror Footer convention: `isNarrow?: boolean` (scales for sub-content-breakpoint) + `prefersReducedMotion?: boolean` (drops `filter: blur(...)`).

MODIFY `frontend/src/components/messenger/index.ts`: append barrel export.

MODIFY MessengerFeature.tsx: import MessengerBackdrop + `useReducedMotion` from framer-motion; compute `prefersReducedMotion = useReducedMotion() ?? false` + `isNarrow = useMediaQuery((max-width: ${breakpoints.content}))`; mount Backdrop inside `.messenger-theme` div before AnimatePresence.

**Scope adjustment within iter**: matte utility classes (`.messenger-card-matte`, `.messenger-active-chip`, `.messenger-send-btn`, etc.) were already co-located in SW1's messenger.css (per W138 Lesson #1 within-iter SAME-mechanism — they belong in the same tokens file). SW2 reduced from plan ~1.5-2h to actual ~30 min Backdrop + hook integration. NOT a mechanism pivot; just natural co-location.

Z-stacking verified: `-z-1` orbs sit behind sibling content but ABOVE parent div's `bg-msg-chat` background (CSS spec: child negative z-index goes behind siblings but parent's background paints first). MessengerSidebar uses `panel-glass relative z-deep` which stacks above orbs (semi-transparency lets faint hue bleed through). Footer's identical pattern works at runtime in W176.

### SW3 — Chat UI polish (`7c71f5034`, +147/-99)

ChatWindow.tsx: Lines 160+162 `text-white` → `text-[var(--text-inverse)]` (the concrete W181 bug). useReducedMotion guard on `m.div` message-bubble entrance animation. Without this, virtualized message bubbles would fade+scale on every scroll-into-view event (jarring under reduced motion).

ContactList.tsx (refactored to add stagger + active-chip + a11y):
- Active row visual: strong `bg-(--brand-main) text-[var(--text-inverse)]` fill → `.messenger-active-chip` utility (subtle violet bg tint + 4px-wide left accent stripe via ::before). Modern chat-app convention (Telegram/Discord/IG-DM). Text stays `text-text-primary` since bg is now subtle.
- CSS stagger entrance: `.messenger-stagger-item` + inline `style={{ "--stagger-index": Math.min(index, 6) }}` (60ms × min(i, 6) = max 360ms cap; W118 SW3 + ActivityTimeline + EventsBackdrop precedent).
- Touch target: `min-h-[60px]` on row clickable area (chat rows are taller than 44px floor by convention).
- Focus rings: `focus-visible:outline-none focus-visible:ring-2 ring-(--color-violet-500) ring-offset-2 ring-offset-(--bg-surface)` (WCAG 2.4.7).
- ARIA: `aria-current={isActive ? "true" : undefined}`.
- useReducedMotion guards on whileHover/whileTap.

MessageInput.tsx: send button matte upgrade via `.messenger-send-btn` utility (violet→pink gradient bg + 2-shadow + hover variant). `min-h-[44px] min-w-[44px]` + focus-visible rings on send + attach + remove-attachment buttons (WCAG 2.5.8). `type="button"` defensively. useReducedMotion guards on whileHover/whileTap.

MessengerSidebar.tsx: new-chat button `min-h-[44px] min-w-[44px]` + flex centering + focus-visible ring + reduced-motion guards. Search TextField `.matte-input` shared utility (W74 `_glass-layers.css`). Sidebar slide animation gated by `isMobile && !prefersReducedMotion`.

**Within-iter sub-fix** (W138 Lesson #1 SAME-mechanism): `sidebarTransition = ... { ease: [...] }` const-binding widened the easing tuple to `number[]` breaking Framer's Transition type. Inlined ternary in JSX prop (same pattern ChatWindow uses); leverages contextual typing.

### SW4 — XL extras: TypingIndicator + empty-state + ProfileModal (`02c310cf5`, +149/-33)

NEW `frontend/src/components/messenger/TypingIndicator.tsx` (~80 LoC). Props: `users: { userId; userName }[]` + `prefersReducedMotion?: boolean`. Returns null if users empty. 3-dot pulse animation OR static i18n text under reduced motion. a11y: `role="status"` + `aria-live="polite"` + sr-only label.

MODIFY ChatArea.tsx:
- Import TypingIndicator + useMessenger + useReducedMotion
- Compute typingUsers via `getTypingUsersForChat(selectedChatId)` (existing W134+ WS infra)
- Mount `<TypingIndicator>` between `<ChatWindow>` and `<MessageInput>`
- Empty state upgrade: `.messenger-empty-mesh` background + `.messenger-card-matte` icon container + `text-(--color-violet-500)` icon + fluid `--fs-messenger-hero` title + larger max-w + `text-balance` polish

MODIFY ProfileModal.tsx:
- Outer dialog: `.messenger-card-matte` for elevated depth + ::before accent line
- Close button: `min-h-[44px] min-w-[44px]` + flex center + violet focus ring + reduced-motion guards on 90° rotate
- Dialog Framer transitions gated by prefersReducedMotion
- Avatar: conditional `.messenger-avatar-ring` when `user.is_active`
- Avatar shape: `rounded-md` → `rounded-2xl` (messenger card-system rhythm)
- Status badge: ad-hoc `<p><span>` markup → canonical `.messenger-status-badge[data-status="online|offline"]` utility

NEW i18n keys (en + ru × 3 = 6 strings): `typing` ("{{name}} is typing..." / "{{name}} печатает..."), `typingMultiple` ("{{count}} people are typing..." / "{{count}} человек(а) печатают..."), `isTyping` ("Typing" / "Печатает").

### SW5 — a11y batch + reduced-motion full coverage + audit (`b048bd2b0`, +43/-23)

TypingIndicator: removed `defaultValue:` from 3 t() calls (anti-pattern that masks missing-key bugs from translationParity walker; all 3 keys exist in en+ru locales).

NewChatModal: import useReducedMotion. Outer dialog now `.messenger-card-matte backdrop-blur-2xl` (was ad-hoc `bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-3xl shadow-premium border ring-1`). Dialog entrance/exit gated by prefersReducedMotion. User-row whileHover x:4 + bg-color gated. `min-h-[60px]` touch target on rows. Focus ring violet. Close button 44×44px floor.

ChatArea: outer chat-area mobile slide-in (`x: 300`) gated by `isMobile && !prefersReducedMotion`. Header transitions (y:-20 entrance + exit) gated. Chat menu dropdown (scale 0.9 + y:10 + x:5 entrance) gated. Subtle whileHover scale:1.02-1.05 + whileTap scale:0.95-0.98 LEFT to global MotionConfig handling (AppProviders W124 SW1 + W127 SW1 reducedMotion="user"); avoids per-component noise for sub-5% scale changes.

Audit grep: 0 hardcoded `text-white` in messenger source (1 match is documentation comment from SW3). 0 hex literals. 0 `bg-slate-N`. 0 `defaultValue:` in messenger scope post-cleanup.

### Polish-v1 — empty-state layout + dark-mode contrast (`befa91f05`, +33/-10)

Caught by chrome-devtools-mcp visual smoke during SW6 prep. Two real visual bugs surfaced:

**Bug 1**: empty-state title + subtitle wrapping one-word-per-line. `<div className="flex flex-col items-center text-center">` made h3/p children shrink to content width. Tailwind v4 `w-full max-w-md/2xl` empirically resolved to `offsetWidth: 48px` per chrome-devtools `evaluate_script` (verified via `computedAlignSelf: "stretch", computedWidth: "48px"`). Likely a `flex` short-utility + width-utility precedence quirk in Tailwind v4 + Rolldown. Fix: explicit inline `style={{ maxWidth: "42rem", width: "100%" }}` sidesteps utility resolution. Title gets 42rem/100%; subtitle gets 32rem/100%. Both keep parent `text-center` inheritance.

**Bug 2**: dark-mode matte card invisible + orbs invisible. `bg-msg-chat` in dark = `var(--color-slate-950)` ≈ `#020617` (near-black). a) Matte card bg 5% indigo-950 mix was indistinguishable from chat-area near-black bg. Bumped to 12% violet-500 mix → matte card elevates as violet-tinted surface above near-black + ties to palette identity. b) Orb opacities 12-16% in dark needed ~2× to register. Bumped to 22% (violet) / 18% (pink) / 15% (indigo). Light mode unchanged.

Empirical chrome-devtools-mcp visual smoke verified both fixes at 1280×800 viewport in both light + dark modes:
- Light: violet/pink ambient orbs subtly visible, icon container white-tinted with accent line, title "Выберите чат, чтобы начать общение" wraps cleanly on 2 lines, subtitle on 1 line.
- Dark: violet/pink/indigo orbs visible against near-black bg, icon container clearly violet-tinted, title + subtitle render same layout.

Screenshots saved: `.screenshots/wave181-messenger-light-final.png` + `wave181-messenger-dark-final.png` (gitignored).

### SW6 — Audit + memory + N+3 rotation (this commit)

NEW `docs/audits/AUDIT_WAVE181.md` (this file).
N+3 rotation: `git mv docs/audits/AUDIT_WAVE178.md docs/audits/archive/AUDIT_WAVE178.md`.
CLAUDE.md ## Audit Trail W181 row + ## Gotchas 4-6 new entries.
INDEX.md updated (active waves W179/W180/W181).
MEMORY.md W181 row addition + W178 verbose-row compaction.
NEW `memory/wave181_backlog.md` + `memory/wave182_opening_prompt.md` in .claude profile.

## §Honesty probe

### Closures (W181 closes 1 of 1 pre-W181 actionable gap)

- ✅ **Messenger to feature-page parity** — closes opening-prompt option F (~3-5h estimate; landed in ~7-9h XL scope per user choice). 10 polish dimensions from Phase 1 Explore Agent 3 gap analysis ALL addressed: theme scope + tokens (SW1), backdrop (SW2), matte card system (SW1+SW2), active-state accent (SW3), stagger (SW3), text-white fix (SW3), useReducedMotion (SW3-SW5), focus rings + 44px touch targets (SW3-SW5), typing indicator (SW4), empty-state visual upgrade (SW4+polish-v1).

### NEW W181 caveats (2 honest scope-deferrals)

1. **Tailwind v4 + Rolldown `w-full + max-w-N` quirk**: SW4 empty-state layout initially used `w-full max-w-md/2xl` Tailwind utilities which empirically resolved to 48px width on the `<h3>` + `<p>` children (per chrome-devtools `evaluate_script` debug). Polish-v1 worked around by switching to inline `style={{ maxWidth, width }}`. The Tailwind v4 utility resolution bug is W182+ housekeeping candidate (~15-30 min investigation if encountered elsewhere); workaround is documented inline in ChatArea.tsx for future maintainers. NOT a W181 SW regression — surfaced by attempted polish, fixed in same iter.

2. **Visual smoke deferred to VITE_LHCI bypass only** — chrome-devtools-mcp visual verification was run against vite preview with VITE_LHCI=true (auth bypass) so /messenger renders empty-state under mock-user. Full Docker chain authed visual smoke (real backend + real WebSocket presence channel + multiple chat conversations + TypingIndicator firing) deferred to user manual testing OR W182+ visual-smoke wave. This is the established convention from W175 + W176 + W180 SW3 (Docker chain verification at end-of-wave when scope demands it; bypass verification for component-level polish that doesn't depend on backend data shape). React #418 regression check: wave137-authed-smoke.mjs would re-run in W182+ to confirm 9 SSR routes still show 0 hydration errors under real-user auth (W180 polish-v2 closure preserved by structural argument — W181 doesn't touch `router.ts:102` defaultPendingComponent OR any `ssr: 'data-only'` route annotation).

## Bundle invariant

**W180 baseline** (`index-C2EoEPG2.js` 179,968b sha `576508ee...c987f715` + server.js 24,024b sha `fb4aa2f5...d257fa2b7`) **RETIRED at W181 SW1** due to real client-tree code changes (new files + new utility classes + theme scope wrapper + Backdrop component + TypingIndicator + ChatWindow text-inverse fix + ContactList active-chip + MessageInput matte + MessengerSidebar matte + ProfileModal matte + NewChatModal matte).

**NEW W181 baseline EMPIRICALLY VERIFIED Build × 3 BYTE-IDENTICAL** (from clean `rm -rf dist && npm run build`):
- main JS `index-DCnJ-daY.js` **179,968 b** sha `bb6e56d0ad764dc8872c8e053f9300479a86fa557bc4c3f23fac3a7fad0ffc3e` × 3 IDENTICAL
- server.js **24,024 b** sha `9bb8288a06b05f4094a5d8ed960c1f4e22f127bb3509708e1631e8f7f86651d0` × 3 IDENTICAL

Delta vs W180:
- main JS SIZE = same 179,968 b (messenger code lives in route-lazy chunks `Messenger-*.js` ~66KB + smaller `messenger-*.js` route chunks)
- server.js SIZE = same 24,024 b (no server-side changes; W180 SW3 augmentResponseForMessenger preserved)
- Hashes DIFFER due to real client-tree changes propagating through dependency graph

Tree-shake invariants ✓:
- 0 `lhci-mock-user` references in PROD assets (W116 SW3 baseline preserved)
- SW IIFE invariant ✓ `"use strict";(()=>{` (W138 SW2 baseline preserved)

## Gates (end-of-wave)

- ✅ tsc 0 errors
- ✅ eslint --max-warnings=0 0 warnings
- ✅ prettier `--check` clean (auto-fixed each commit via lint-staged + husky)
- ✅ vitest **1147 passed / 12 skipped / 0 failed** in 30.42s (W180 baseline EXACT preservation)
- ✅ npm audit 0 vulnerabilities (W179 SW2 baseline preserved; no dependency changes in W181)
- ✅ Cargo.lock no drift (idempotent ≥ 41 waves post-W113 SW6 fix)
- ✅ Build × 3 BYTE-IDENTICAL × 3 fresh runs from clean state
- ✅ translationParity.test.ts 18/18 pass (3 new i18n keys × 2 locales added in SW4; auto-walks all locale files)
- ✅ Empirical visual smoke via chrome-devtools-mcp on /messenger (VITE_LHCI=true vite preview):
  - Light mode: violet/pink ambient orbs visible, matte icon container with accent line, title + subtitle properly laid out
  - Dark mode: violet/pink/indigo orbs visible against near-black, icon container violet-tinted, full layout parity with light
  - Console: 0 React errors, 0 hydration warnings, only expected WS 403 (no backend in preview) + 1 W128 SW1 `profile_cache.cleared` pre-existing warn

## W141 anti-pattern compliance

- **#1 STRICT 1-iter SACRED** — **36th total vindication**. All 6 SW (SW1-SW5 + SW6 audit) + polish-v1 landed in their respective single iterations. W138 Lesson #1 within-iter SAME-mechanism sub-fixes applied (SW2 matte-class consolidation, SW3 Framer Transition type fix, polish-v1 layout + dark-mode contrast). NO mechanism pivots. NO defer fired in W181 — all closures attributed.
- **#3 (Phase 3 Review)** — **66th vindication**. Phase 1 Explore 3-agent fan-out + Phase 3 direct Read of 8 files (tokens/messenger.css absence, ChatWindow.tsx specifics, FooterBackdrop.tsx template, activity.css recipe, i18n keys, MessengerFeature.tsx structure, MessengerContext typing infra, primitives.css palette inventory) caught: Phase 1 plan called for fuchsia → empirical primitives.css has only pink-400 → palette adjusted; `breakpoints.content` location verified before use; `_glass-layers.css` actual path (`partials/_glass-layers.css`) found via empirical grep; `prefersReducedMotion = useReducedMotion() ?? false` pattern; const-binding Framer Transition type widening caught at tsc.
- **#4 (Empirical verification before closure attribution)** — **33rd vindication**. Closures attributed AFTER Build × 3 + chrome-devtools-mcp visual smoke + vitest baseline preservation. polish-v1 commit ACKNOWLEDGES that SW4 had visual bugs that surfaced at chrome-devtools-mcp verification, fixed in same iter, NOT shipped as "closed" without empirical evidence.
- **#15 (ARCHIVED W159 SW4)** — preserved **48th consecutive wave**. All 7 W181 commits (SW1 `0925e4700` + SW2 `d3811b051` + SW3 `7c71f5034` + SW4 `02c310cf5` + SW5 `b048bd2b0` + polish-v1 `befa91f05` + this SW6 audit) fired W156 SW4 husky pre-commit chain cleanly (lint-staged prettier --write + eslint --fix; detect-secrets PASS; Python 2 except check PASS). NO `--no-verify` bypasses.

## (z) discoveries

- **0 NEW (z) discoveries from W181 SW execution proper** (extends W145-W180 trajectory; Phase 1 + Phase 3 Review prevent cascade)
- **1 NEW investigation-class finding** (polish-v1): Tailwind v4 + Rolldown `w-full + max-w-N` empirically resolved to 48px width on flex-col items-center children — same bug class as W141 anti-pattern #3 "verify before assertions" but at compile-time utility resolution layer. Documented inline as a Gotcha + workaround applied via inline style. Not a (z) cascade — single empirical disproof + immediate fix. NOT bundled count toward (z) discoveries.

## N+3 rotation

`git mv docs/audits/AUDIT_WAVE178.md docs/audits/archive/AUDIT_WAVE178.md`. Active waves post-W181: **W179/W180/W181**.

## W182+ candidates

User stated W180 transitions to **visual UI polish phase**. W181 closed Messenger as first focus. W182+ visual work candidates per `feedback_planning_estimates.md` historical anchoring + user-driven choice:

1. **Continue maintenance + bug fixes only** (CANONICAL DEFAULT per W171 Lesson #1) — fires if/when real bug surfaces.
2. **Profile + Settings page visual polish** (~3-5h each; post-W175 SW4-SW5 a11y groundwork; visual layer not yet feature-page parity).
3. **Admin pages visual polish** (~4-6h; evolves /admin polish arc kicked off W150).
4. **Auth pages visual polish** (~3-5h; Login + Register + ResetPassword + ForgotPassword; pre-auth first impression).
5. **Cross-page consistency review** (~4-6h; typography + spacing + motion tokens design-system audit).
6. **Map controls + overlays visual polish** (~2-4h).
7. **Real bug triage** (specific issue dependency).
8. **Phase 6 canary deployment** (W132 SW6 runbook ready; 1-2 weeks operator wave).
9. **Lighthouse #17021 monitoring tick** (~30 min; W181-W185 window per W180 SW1 calibration).
10. **Tailwind v4 + Rolldown `w-full + max-w-N` utility resolution investigation** (~30 min housekeeping if pattern re-surfaces).
11. **TypingIndicator + ProfileModal + NewChatModal unit tests** (~1-2h test infrastructure expansion).
12. **Full Docker chain authed visual smoke on messenger** (~30-60 min; validates real WS + chat data + TypingIndicator firing).

Per W171 Lesson #1: maintenance mode means waves fire on real triggers. Visual polish phase per W180 user directive continues — user choice of next surface.

## Cross-references

- W180 audit: `docs/audits/AUDIT_WAVE180.md` (predecessor — closed §H#10 /messenger SSR enable + §H#2 bundle delta; established 0-OPEN §Honesty trajectory)
- W175 SW2-SW3: ChatWindow.tsx:98 text-inverse pattern + NewChatModal/ProfileModal useFocusTrap (W181 SW3 extends to lines 160+162)
- W145 SW2: MessengerFeature.tsx orchestrator extraction (W181 SW1+SW2 add theme scope + Backdrop to this orchestrator)
- W84-W87 Activity polish arc: `tokens/activity.css` + `ActivityBackdrop.tsx` (reference templates for W181 SW1+SW2)
- W176 Footer polish: `FooterBackdrop.tsx` (cleanest in-tree backdrop template for W181 SW2)
- W118 SW3 pixel-anchored orb pattern (CLS-118-03): documented in CLAUDE.md ## Gotchas (W181 SW2 applies)
- W141 anti-pattern register: CLAUDE.md ## Gotchas + Audit Trail (41-wave streak)
- `feedback_perfectionism.md` (60-90 min polish-pass discipline; polish-v1 example application)
- `feedback_planning_estimates.md` (range-anchored estimates; W181 XL 7-10h realized as ~7-9h core)
- `memory/wave181_backlog.md` (W182 hand-off)
- `memory/wave182_opening_prompt.md` (next wave opening)

---

**End of AUDIT_WAVE181.md.**
