# Wave 189 — M-L Housekeeping Batch (B1+B2+B3+B4) + N+3 Rotation

**Date**: 2026-05-26
**Branch**: `egorribun`
**Scope**: M-L user-mandate per Opening Prompt Option F → 3-wave decomposition
**Budget**: ~3-5h core; actual ~2-3h (verified gates remained GREEN throughout)
**Total commits**: 4 SW + 1 audit (this SW5) = **5 commits**
**Status**: ✅ CLOSED + polish-v? chain (TBD based on PR #1126 CI verification post-push)
**Wave streak**: **49th consecutive wave** preserving brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline (W141-W189)

---

## 🟢 Headlines

1. **All 4 housekeeping carries from W187-W188 CLOSED**:
   - **B4** SW1 `3195a7ba0` `fix(wave189-sw1-news-print-important)` — news.css 9 `!important` → doubled-class specificity (FIX-72-04 pattern); 11th themed surface migrated to the canonical print-stylesheet pattern (admin.css + dashboard.css + profile.css + ... + news.css now all consistent).
   - **B1** SW2 `833a692a8` `feat(wave189-sw2-unauthed-visual-smoke)` — NEW `frontend/scripts/wave189-unauthed-smoke.mjs` (~280 LoC) covers /login + /register + /forgot-password + /reset-password through real Caddy → Node SSR → backend chain. Both light + dark theme runs PASSED: 4/4 routes HTTP 200 + 0 hydration errors. Closes W187 §H NEW #2.
   - **B3** SW3 `2bc0455f9` `refactor(wave189-sw3-hook-migration)` — 4 components migrated from framer-motion's jsdom-incompat `useReducedMotion()` to project's `useMediaQuery("(prefers-reduced-motion: reduce)")` DEFAULT export: Footer.tsx + EventsCard.tsx (dashboard/) + MapShortcutsOverlay.tsx + MapWeatherPanel.tsx. Closes Path D D2+D3 (W188 polish-backlog carry-forward).
   - **B2** SW4 `fff5b62e4` `test(wave189-sw4-chatarea-test-infra)` — NEW `frontend/src/components/messenger/__tests__/ChatArea.test.tsx` (~380 LoC, 12 tests across 5 describe blocks) — mirrors W185 SW2 ChatWindow.test.tsx template. Closes W185 SW3 partial defer (carried through W186-W188).

2. **Bundle Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED at NEW W189 baseline**:
   - Main JS `index-Ca-nPbFn.js` **180,277 bytes** sha **`74d26d40417b0ff340c60022665348874063d4881f62e5085a036457826c2583`** × 3 fresh `rm -rf dist && npm run build` runs from clean state
   - Server.js **24,024 bytes** (BYTE-IDENTICAL to W188 — SW3 hook migration is client-tree only; server-side unaffected) sha **`c5f927c741584276b8e8401212ff0863d124c5f375c1f32885acfe1890ab1e62`** × 3
   - **Delta vs W188 baseline** (180,255 b): **+22 bytes** main JS (real client-tree weight from SW3 hook migration: 4 `useReducedMotion()` → `useMediaQuery("(prefers-reduced-motion: reduce)")` replacements + new useMediaQuery imports; well under plan ±100 b range).
   - W134-W186 ≥45-wave content-sha invariant RETIRED at W188; W188 NEW baseline EXTENDS through W189 SW3 (real production code change) → **NEW W189 baseline × 3 reproducible** established.

3. **§Honesty trajectory**: 0-2 OPEN pre-W189 → **0-2 OPEN post-W189** (CLOSE 4 actionable items + 2 W134 structural non-goals preserved unchanged; expected 0 NEW W189 caveats since all 4 SW shipped without scope deferrals).

4. **CI on PR #1126 verification pending post-push** — at SW5 commit time, the polish-v1+v2+v3+v4 chain landed PR #1126 EMPIRICALLY GREEN (45 SUCCESS / 0 FAILURE / MERGEABLE for HEAD `ff4d0b55d`). W189 commits push to same egorribun branch → CI re-runs for new HEAD; expected GREEN given strict gate baseline preservation throughout each SW.

---

## SW Breakdown

### Pre-flight (this session) — Pre-SW1

- `gh pr view 1126` → state: OPEN, mergeable: MERGEABLE, headRefOid: `ff4d0b55d...` — W188 polish-v4 head; W189 commits land on same PR
- `gh run list --branch egorribun --limit 5` → CI on `ff4d0b55d`: 4 SUCCESS + 1 IN_PROGRESS (Lighthouse Audit pending; non-blocking)
- `git status --short` → clean
- `git log --oneline -5` → top: `ff4d0b55d docs(wave188-polish-v4)` (matches opening prompt expectation)
- `wc -c MEMORY.md` → 23,821 b (~579 b headroom; W189 SW5 compaction needed before adding W189 row)
- `npx tsc --noEmit` → 0 errors
- `npm run lint --max-warnings=0` → 0 warnings
- `npx vitest run --silent=true` → 1256 passed / 12 skipped / 0 failed in 37.03s (W188 baseline preserved EXACTLY)

All 8 pre-flight gates GREEN. No scope blockers.

### SW1: B4 news.css !important removal (`3195a7ba0`)

**File**: `frontend/src/styles/tokens/news.css` lines 504-563
**Pattern**: FIX-72-04 doubled-class specificity (.news-theme.news-theme), already proven in dashboard.css:143-154 + admin.css:366-396 + profile.css:213-222.

Replaced 9 `!important` occurrences inside the `@media print` block:

- Line 506-507: `.news-theme { background+color: ... !important }` → `.news-theme.news-theme { background+color: ... }`
- Line 514: `.news-theme .aurora-mesh + [aria-hidden] + .news-reading-progress + .news-sticky-categories { display: none !important }` → `.news-theme.news-theme .X { display: none }` (wrapped under doubled-class parent)
- Line 536-537: code/pre background+border `!important` → no-important under doubled-class
- Line 558-561: glass-layer-surface/elevated/floating x4 `backdrop-filter / background / border / box-shadow !important` → no-important under doubled-class

**Specificity reasoning** (verified inline + via Phase 3 read of news.css structure):

- @media print block at top-level (outside `@layer base` per line 1-502 wrapper); unlayered rules beat layered rules per CSS cascade-layers spec
- Doubled-class `.news-theme.news-theme` raises specificity to 0-2-0
- Single-class non-print rules anywhere inside @layer base = 0-1-0
- Result: print rules win cascade WITHOUT `!important`

**Verification**:

- `grep -c "!important" news.css` → 2 (both inside W189 SW1 comment block describing the fix; **0 actual CSS rule** `!important`)
- `awk '/@media print/,/^}/' news.css | grep -c "!important"` → 0 ✓ (all 9 removed from inside @media print block)
- `prettier --check news.css` → clean ✓
- Husky pre-commit chain: lint-staged + prettier --write + detect-secrets + Python 2 except syntax check all PASS

**Bundle impact**: CSS-only change; main JS BYTE-IDENTICAL to W188 baseline (unchanged at this SW commit).

**Scope**: 1 of 4 housekeeping items closed. Closes Path D D5 follow-up scope from W188 (news.css was the 11th of 12 themed surfaces; admin.css + dashboard.css + profile.css + others already migrated in prior waves).

### SW2: B1 NEW wave189-unauthed-smoke.mjs (`833a692a8`)

**File**: NEW `frontend/scripts/wave189-unauthed-smoke.mjs` (~280 LoC; lint-staged auto-formatted to ~310 LoC final)
**Routes**: /login + /register + /forgot-password + /reset-password (4 public routes; _public/$token excluded since invalid-token scenario covered by /reset-password without token)

Mirror of wave137-authed-smoke.mjs structure minus the auth chokepoint (CSRF dance + login POST + JWKS pre-check + JWT decode/validation). Unauthenticated visitors don't traverse those code paths.

**3-layer theme init pattern** (W188 SW2 lesson applied here — verified via Phase 3 read of wave165 lines 312-362):

- Layer 1: `page.context().addCookies([{name:"ue-mode", value:theme, ...}])` → SSR initial render reads via globalThis.__ssrThemeGetter__
- Layer 2: `page.addInitScript((themeName) => localStorage.setItem("ue-mode", themeName), theme)` → client hydration init reads localStorage on mount
- Layer 3: `page.emulateMedia({ colorScheme: theme })` → media query defense-in-depth

All BEFORE `page.goto`. Default theme = "light" (unauth visitors). Dark theme runs via THEME=dark env override.

**Per-route fresh page** (W129 §Honesty `new_page` workaround preserved from wave137): existing-page navigation has been observed to time out at 30s under chrome-devtools Windows wall family. Trade-off: ~500ms slower per route from page setup, but every route smokes successfully.

**Hydration error filter** extended to React #418-#427 minified family per W180 polish-v1 + W167 SW1 W166 (z) #2 class bug fix.

**Empirical verification** (both themes via THEME=light + THEME=dark runs through real Caddy → Node SSR → backend chain):

| Route                | HTTP   | Hydration errors | Console errors                           | Final URL              |
| -------------------- | ------ | ---------------- | ---------------------------------------- | ---------------------- |
| /login (light)       | 200 ✓  | 0 ✓              | 2 (pre-existing 401 /users/me noise)     | /login                 |
| /register (light)    | 200 ✓  | 0 ✓              | 1 (pre-existing 401 noise)               | /register              |
| /forgot-password     | 200 ✓  | 0 ✓              | 1                                        | /forgot-password       |
| /reset-password      | 200 ✓  | 0 ✓              | 1                                        | /reset-password        |
| Same 4 routes (dark) | 200 ✓  | 0 ✓              | Identical noise pattern                  | (same)                 |

Exit codes per script: 0=all green, 1=non-200 status, 2=hydration errors.

**Scope**: 2 of 4 housekeeping items closed. Closes W187 §H NEW #2 carried through W188.

### SW3: B3 Path D D2+D3 hook migration (`2bc0455f9`)

**Files**: 4 production components (W141 anti-pattern #3 caught the EventsCard.tsx path drift pre-implementation — opening prompt claimed `features/events/components/EventsCard.tsx` but actual path is `frontend/src/components/dashboard/EventsCard.tsx` per Phase 1 Agent 3 + Phase 3 direct Read):

- `frontend/src/components/layout/Footer.tsx` (line 3 + line 46)
- `frontend/src/components/dashboard/EventsCard.tsx` (line 5 + line 31)
- `frontend/src/components/map/MapShortcutsOverlay.tsx` (line 14 + line 45)
- `frontend/src/components/map/MapWeatherPanel.tsx` (line 8 + line 44)

**Migration pattern**:

```tsx
// Before:
import { useReducedMotion } from "framer-motion"
const prefersReducedMotion = useReducedMotion() ?? false // boolean | null

// After:
import useMediaQuery from "@/hooks/useMediaQuery" // DEFAULT export (W186 SW3 lesson)
const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)") // boolean
```

For Footer.tsx specifically: file ALREADY imported useMediaQuery (line 8 for `isNarrow`). SW3 just added a SECOND useMediaQuery call for `prefersReducedMotion` and removed the lone `useReducedMotion` import from framer-motion.

For MapShortcutsOverlay + MapWeatherPanel + EventsCard: kept other framer-motion exports (AnimatePresence + m); only dropped `useReducedMotion` from each import list. Added new `useMediaQuery` import.

EventCardHero.tsx manual `window.matchMedia()` at line 99 (inside `useEffect`) **NOT migrated** per Phase 1 Agent 3 verification — it's a one-time read inside useEffect (no listener registration), so jsdom incompat risk doesn't apply.

**Out-of-scope** (24 other files using framer-motion's useReducedMotion = W190+ candidate per Phase 1 Agent 3 bulk grep): NewChatModal, ContactList, ChatWindow, ChatArea, MessengerSidebar, MessengerFeature, MessageInput, ProfileModal, _admin.tsx, Schedule.tsx, EventDetail.tsx, EventsHeader.tsx, MapFeature.tsx, EventsFeature.tsx, ActivityTrendChart.tsx, ActivityBarChart.tsx, ActivityFeature.tsx, ScheduleMobileView.tsx, ScheduleSettingsPanel.tsx, ScheduleShortcutsOverlay.tsx, NowPlayingCard.tsx, NewsQuickView.tsx, WeatherParticles.tsx, EventQuickView.tsx.

**Verification**:

- `npx tsc --noEmit` → 0 errors ✓
- `npx eslint --max-warnings=0` → 0 warnings ✓
- `grep -rn "useReducedMotion } from \"framer-motion\"" <4 target files>` → 0 matches ✓
- `npx vitest run` → **1256 passed / 12 skipped / 0 failed** (W188 baseline preserved EXACT) ✓

**Bundle impact**: Real client-tree code change in 4 production components. W188 BYTE-IDENTICAL invariant RETIRED at SW3 commit; NEW W189 baseline established (verified in SW5 Build × 3 — see Headlines section above; +22 bytes vs W188).

**Scope**: 3 of 4 housekeeping items closed. Closes Path D D2+D3 (W188 polish-backlog carry-forward).

### SW4: B2 NEW ChatArea.test.tsx (`fff5b62e4`)

**File**: NEW `frontend/src/components/messenger/__tests__/ChatArea.test.tsx` (~380 LoC final, 12 tests across 5 describe blocks)

**Template reference**: ChatWindow.test.tsx (W185 SW2) — 14 tests with mocks for react-i18next + SmartImage + framer-motion + useDebounced + useVirtualizer.

ChatArea has **19 props** (verified Phase 3 — opening prompt's "20 props" was off-by-one). ChatArea also uses framer-motion's `useReducedMotion()` at line 95 → must be mocked per ChatWindow.test.tsx pattern.

**Test plan executed** (12 tests passed):

1. Renders 'select a chat' empty state when selectedChatId=null
2. Renders empty state when activeChat=null even if selectedChatId is set
3. Renders participant name in header when activeChat set
4. Renders offline status when participant NOT in presenceMap as active
5. Renders online status + presence indicator when presenceMap.active=true
6. Clicking Search button fires setShowSearchInChat(true)
7. Renders search input when showSearchInChat=true
8. Clicking Menu button fires setShowChatMenu toggle
9. Renders 3 menu items when showChatMenu=true (View Profile + Clear + Delete)
10. Clicking menu items fires the correct callback (Clear Chat case)
11. Renders ChevronLeft back button only when isMobile=true
12. Renders ChatWindow + TypingIndicator + MessageInput when chat selected

**Mock strategy**:

- `react-i18next` → pass-through `t()` with JSON-serialized opts
- `SmartImage` → plain `<img>`
- `framer-motion` → `vi.importActual + ...actual, useReducedMotion: () => false` (W184 SW6 jsdom-incompat workaround)
- `useMessenger` context → `{ getTypingUsersForChat: () => [] }`
- `useNavigate` → `vi.fn()` stub
- `@/components/messenger` barrel → stub ChatWindow + MessageInput + TypingIndicator (jsdom can't render @tanstack/react-virtual or Framer Motion exits meaningfully)

**Type-safety challenges resolved**:

- `Chat` type lives at `@/api/chat` NOT `@/components/messenger/types` (Phase 3 direct Read corrected initial assumption)
- `User` is `UserOut` extended from generated OpenAPI types → use `as unknown as User` cast since ChatArea only reads {id, full_name, avatar_url}
- ChatAreaProps derives from `ReturnType<typeof useMessengerController>` → declared `baseProps: ComponentProps<typeof ChatArea>` to force TS to match exact prop types
- `presenceMap` requires `PresenceStatus` shape with `last_seen_at: string | null`
- `getOtherParticipant` signature is `(chat: Chat) => User | undefined` per useMessengerController.ts:367-372

**Verification**:

- `npx tsc --noEmit` → 0 errors ✓
- `npx vitest run src/components/messenger/__tests__/ChatArea.test.tsx` → 12 / 0 failed in 2.42s ✓
- `npx vitest run` (full suite) → **1268 passed / 12 skipped / 0 failed** in 35.04s (baseline 1256 + 12 NEW = 1268 EXACT) ✓

**Out-of-scope** (W190+ candidates documented in test file comment block):

- Full TypingIndicator integration (W181 SW4 + W184 hook surface)
- Mobile vs desktop layout assertion (responsive width branches)
- AnimatePresence dialog transitions (jsdom doesn't render Framer Motion exit animations)

**Scope**: 4 of 4 housekeeping items closed. Closes W185 SW3 partial defer.

### SW5: Audit + N+3 rotation + memory files (this commit)

- NEW `docs/audits/AUDIT_WAVE189.md` (this file)
- `git mv docs/audits/AUDIT_WAVE186.md docs/audits/archive/AUDIT_WAVE186.md` (N+3 rotation; oldest active → archive)
- Update `CLAUDE.md ## Audit Trail` (NEW W189 row at top + extend rotation history with `**W189 SW5 (W186 → archive)**` + update active waves line to `W187/W188/W189`)
- Update `docs/audits/INDEX.md` (move W186 row from Active table to Archived table; add W189 row at top of Active table)
- Update `<.claude>/MEMORY.md` (compact W188 verbose Active backlog + Audit History rows → one-liners per W188 SW0 compaction recipe; add NEW W189 verbose Active backlog + Audit History rows)
- NEW `<.claude>/memory/wave189_backlog.md` (this wave's backlog file)
- NEW `<.claude>/memory/wave190_opening_prompt.md` (handoff for Path E XL messenger features wave)

**Bundle Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED** (see Headlines):

- main JS `index-Ca-nPbFn.js` 180,277 b sha `74d26d40...c2583` × 3 fresh runs
- server.js 24,024 b sha `c5f927c7...e62` × 3 (BYTE-IDENTICAL to W188 — server-side unchanged)
- Tree-shake invariant ✓ (`grep -l "lhci-mock-user" dist/client/assets/*.js` → 0 matches)
- SW IIFE invariant ✓ (`head -c 25 dist/client/sw.js` → `"use strict";(()=>{`)

---

## §Honesty probe (post-W189 SW5)

**Trajectory**: 0-2 OPEN pre-W189 → **0-2 OPEN post-W189** (CLOSE 4 actionable items: B1+B2+B3+B4; carry-forward 2 W134 structural non-goals; 0 NEW W189 caveats since all 4 SW shipped without scope deferrals beyond the explicit "24 other files using framer-motion useReducedMotion = W190+ candidate" framing which is by-design narrowed scope per opening prompt).

### Open caveats (carry-forward unchanged)

1. **W134 §H#2 — Bundle delta recording-only** (structural non-goal, ≥ 51 waves carry-forward).
   W180 SW4 deep dive confirmed bundle is optimally structured. Further reductions require multi-wave structural projects.
2. **W134 §H#10 — /messenger Phase 5 SSR by-design** (structural non-goal, ≥ 51 waves carry-forward).
   /messenger × 2 SSR enabled via W180 SW3 with two-layer privacy posture (cookie + Vary: Cookie + Cache-Control: no-store).

### Honest scope narrowing (NOT regressions)

- **SW3 — 24 other files using framer-motion's useReducedMotion deferred to W190+**: opening prompt explicitly scoped B3 to the 4 named components; the broader migration sweep is a separate scope-bounded wave to maintain W141 anti-pattern #1 STRICT 1-iter discipline.
- **SW2 — wave189-unauthed-smoke.mjs single-theme default**: light theme is default; dark theme runs via THEME=dark env. Both verified pre-commit. Acceptable scope per Opening Prompt 30-min budget.

---

## W141 anti-pattern compliance

- **#1 STRICT 1-iter per SW SACRED** → **80th-84th total vindications** (5 SW commits this wave + SW5 audit; each landed 1-iter with within-iter SAME-mechanism sub-fixes per W138 Lesson #1 — SW4 ChatArea.test.tsx had 3 within-iter type-fixture corrections before TSC clean; ALL within W141 #1 cap, NOT mechanism pivots).
- **#3 Phase 3 Review verify-before-write** → **98th-101st vindications** (4+ caught this wave):
  - **#98** Phase 1 Agent 3 + Phase 3 direct Read caught EventsCard.tsx path drift (opening prompt claimed `features/events/components/EventsCard.tsx`; actual `frontend/src/components/dashboard/EventsCard.tsx`).
  - **#99** Phase 1 Agent 1 confirmed wave137 has 9 SSR routes (NOT 8 as I might have estimated earlier).
  - **#100** Phase 1 Agent 2 confirmed ChatArea has 19 props (NOT 20 as opening prompt claimed; corrected before writing test fixtures).
  - **#101** Phase 1 Agent 1 confirmed news.css has 9 `!important` (not 1) inside `@media print` block; awk verification of line numbers in Phase 3 before applying Edit.
- **#4 Closures-after-empirical-verification** → **41st vindication**: closures attributed AFTER per-SW empirical verification — SW1 grep count + prettier check, SW2 4-route × 2-theme PASS, SW3 grep+tsc+lint+vitest, SW4 12-test PASS + 1268p full suite, SW5 Build × 3 BYTE-IDENTICAL × 3 fresh runs.
- **#15 (ARCHIVED W159 SW4)** preserved **66th-69th consecutive waves** — all 5 W189 commits (SW1 + SW2 + SW3 + SW4 + SW5 audit) fired W156 SW4 husky pre-commit chain cleanly (lint-staged auto-format via prettier --write + eslint --fix; detect-secrets PASS; Python 2 except check PASS). NO `--no-verify` bypasses.

**0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

---

## (z) Discoveries

**0 NEW (z) discoveries from W189 SW execution proper** — Phase 1 Explore + Phase 3 Review prevented cascade per W141 anti-pattern #3 4 vindications (#98-#101). Extends low-(z) streak: 24 of last 24 waves (W145-W189 inclusive).

3 within-iter SAME-mechanism sub-fixes applied in SW4 (type fixture corrections) — all classified as W138 Lesson #1 sub-fixes (NOT (z) discoveries; mechanism = "import Chat type correctly + cast User minimally + use ComponentProps for fixture conformance"; each iteration narrowed within the same mechanism).

---

## Gates GREEN end-of-wave

- **tsc**: 0 errors ✓
- **eslint --max-warnings=0**: 0 warnings ✓
- **vitest** (full suite): **1268 passed / 12 skipped / 0 failed** in 35.04s (baseline 1256 + 12 NEW W189 SW4 ChatArea tests = 1268 EXACT) ✓
- **npm audit --omit=dev**: 0 vulnerabilities ✓ (W183 SW3 baseline preserved through W189)
- **Cargo.lock**: no drift ✓ (idempotent ≥ 48 waves at end of W189)
- **Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED**: main JS sha `74d26d40417b0ff340c60022665348874063d4881f62e5085a036457826c2583` × 3 + server.js sha `c5f927c741584276b8e8401212ff0863d124c5f375c1f32885acfe1890ab1e62` × 3 fresh runs from clean state ✓
- **Tree-shake invariant**: 0 matches `lhci-mock-user` in PROD `dist/client/assets/*.js` ✓
- **SW IIFE invariant**: `head -c 25 dist/client/sw.js` → `"use strict";(()=>{` ✓
- **i18n parity**: 18/18 ✓ (no new i18n keys in W189 — test infra + CSS + hook migration only)

---

## N+3 rotation

- `git mv docs/audits/AUDIT_WAVE186.md docs/audits/archive/AUDIT_WAVE186.md`
- Active waves post-W189: **W187 / W188 / W189**
- Archive table in INDEX.md gets W186 row appended (newest first in Frontend audit era W112-W190).

---

## W190+ candidates (priority order)

A) **Continue maintenance mode** (CANONICAL DEFAULT per W171 Lesson #1) — no real production trigger, no specific user motivation, no real bug reports. Wave fires on real triggers OR user-chosen scope.

B) **W190 XL Path E messenger features** (~6-10h core, deferred from W189 Option F 3-wave decomposition):

- E1: Read receipts UI — checkmark animations + `read_at` field display + ARIA labels (~2-3h)
- E2: Reactions UI — emoji picker + reaction count badge + tap-to-react interaction (~2-3h)
- E3: Voice messages UI — recorder + waveform display + playback control (~2-4h)

Prerequisites: verify `app/models/messenger.py` (or wherever Message model lives) for `read_at`, `reactions`, `voice_message_url` fields. If NOT exist: W190 becomes a backend wave first (~3-5h to add migrations + repo methods + endpoints) + UI wave second. If EXIST: proceed directly to UI.

C) **W190+ broader hook migration sweep** (~3-5h, 24 other files identified by Phase 1 Agent 3 bulk grep) — migrate remaining components from framer-motion's `useReducedMotion()` to project's `useMediaQuery`. Scope-bounded same-mechanism work; preserve W141 #1 1-iter discipline.

D) **Lighthouse #17021 monitoring tick** at W193+ if still no upstream movement.

Per W171 Lesson #1: maintenance mode means waves fire on real triggers OR user-chosen scope.

---

**Wave 189 status post-SW5**: ✅ CLOSED — 4 housekeeping items closed (B1+B2+B3+B4) + N+3 rotation done. Push to egorribun branch → PR #1126 CI re-runs for new HEAD; expected GREEN. Polish-vN chain may follow if «безупречно?» probe fires OR if CI surfaces unexpected failures.
