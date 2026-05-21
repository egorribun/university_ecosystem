# Wave 178 audit — Close W177 §Honesty #2 (Approach 1 extension)

**Date**: 2026-05-21
**Branch**: `egorribun` (HEAD pending after this SW2 audit commit; SW1 = `381f85578`)
**Scope**: Q0=B real-trigger wave per W171 Lesson #1 (user-approved Option B at session start; not force-fired)
**Plan**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-buzzing-oasis.md`
**38th consecutive wave** with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline (W141-W177 → +W178).

---

## Headline

✅ **W177 §Honesty #2 EMPIRICALLY CLOSED via Approach 1 extension**: reactive layout-level `useEffect` added to `_public.tsx`'s `PublicLayout` covering ALL 5 routes under `/_public/` (`/login`, `/forgot-password`, `/register`, `/reset-password`, `/reset-password/$token`) via a single mechanism. Authed user who hard-navigates to any of these 5 routes (bookmark / search engine / external link / new tab) is now redirected to `/dashboard` with `replace:true`. Verified through real Caddy → Node SSR → backend Docker chain via chrome-devtools-mcp.

The W178 mechanism is PURELY ADDITIVE. W177 SW1's Login.tsx useEffect REMAINS unchanged as defense-in-depth — React 19 child-effect-before-parent-effect ordering means both fire when the user transition null→set occurs; both navigate to `/dashboard` with `replace:true`; the second call is a no-op once the route already changed. Removing Login.tsx's would orphan the W177 §Honesty #3 regression test and break Login.test.tsx — outside W178 minimal scope per W141 anti-pattern #1.

**Closes ONE explicit W177 scope-trade-off**: the user-chosen "Approach 2" in W177 SW1 was narrow-by-design (`/login`-only). W177 §Honesty #2 documented the explicit gap. W178 Q0=B chose to close it via the dual mechanism.

---

## Q0 / Q1 / Q2 decision context

User-approved at session start via brainstorming + AskUserQuestion:

- **Q0 = Option B** (Approach 1 extension; ~1-2h focused scope). 4 options offered: A continue pause (Recommended canonical default) / B Approach 1 extension / D npm audit fix ws / I Tier 4 housekeeping. User picked B over the canonical A — surfaces real motivation rather than maintenance-mode pause.
- **Q1 implicit** = Design A "additive, keep Login.tsx useEffect" (NOT replacement) per W141 anti-pattern #1 STRICT 1-iter discipline + Q0 wording "extension" not "replacement". Decision made at plan-write time without separate AskUserQuestion — justified by 4 reinforcing reasons documented in plan §Implementation (W138 Lesson #1 within-iter SAME-mechanism; W177 SW1 regression test preservation; defense-in-depth value; minimal blast radius).
- **Q2 = STRICT 1-iter per SW** per W141 anti-pattern #1 SACRED.

---

## SW1 — `_public.tsx` PublicLayout + dedicated unit test

**Commit**: `381f85578 feat(wave178-sw1-public-layout-redirect): close W177 §Honesty #2 via _public.tsx useEffect`
**Files**: 3 modified (+208 / -3)

### File 1: `frontend/src/routes/_public.tsx` (+43 / -11)

Refactored stateless `component: () => <Outlet />` to named export `PublicLayout` with reactive useEffect. Beforе W178 the component was a 1-line arrow function returning `<Outlet />` directly. Post-W178 it's:

```tsx
export function PublicLayout() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  useEffect(() => {
    if (user) {
      navigate({ to: "/dashboard", replace: true })
    }
  }, [user, navigate])
  return <Outlet />
}

export const Route = createFileRoute("/_public")({
  // ... existing comment blocks preserved ...
  beforeLoad: () => {
    const { user, loading } = useAuthStore.getState()
    if (loading) return
    if (user) {
      throw redirect({ to: "/dashboard" })
    }
  },
  component: PublicLayout,
})
```

3 new imports (`useEffect` from "react", `useNavigate` from "@tanstack/react-router" — joins existing `createFileRoute, Outlet, redirect` import). 32-line jsdoc-style comment block explains:
- Approach 1 extension rationale + 5 routes covered
- Defense-in-depth design (Login.tsx useEffect remains unchanged; React 19 child-before-parent effect order; idempotent double-fire pattern)
- beforeLoad-vs-useEffect division of labor (beforeLoad runs once on initial mount; useEffect catches subsequent transitions like AuthProvider's useProfileSync settling /users/me mid-mount)
- Hardcoded `/dashboard` target matches W177 SW1 (NOT `state.from` — that's W177 §Honesty #3, out of W178 scope)
- Named export rationale (custom unit test cannot reuse renderWithRouter helper per its docstring caveat lines 50-54)

W174 SW1 `beforeLoad` block UNCHANGED. New W178 SW1 comment added below it referencing the dual mechanism.

### File 2: `frontend/src/routes/__tests__/_public.test.tsx` (+136 NEW)

NEW unit test file (the FIRST file under `src/routes/__tests__/`). 4 test cases:

1. `redirects authed user away from /forgot-password to /dashboard` (it.each parameterized)
2. `redirects authed user away from /register to /dashboard` (it.each)
3. `redirects authed user away from /reset-password/sample-token-123 to /dashboard` (it.each)
4. `leaves unauth user on /forgot-password (negative case)`

Test approach: builds a CUSTOM route tree via `createRoute + addChildren` mounting `PublicLayout` as parent layout, 3 representative child routes (forgot-password / register / reset-password/$token), and `/dashboard` as sibling root-level route. The standard `renderWithRouter` helper (W114 SW1) builds a flat tree and does NOT exercise layout components — so this custom-tree pattern is reusable for future layout-level testing (NEW test infrastructure pattern documented inline).

`afterEach` resets `useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })` matching Login.test.tsx:65-70 (W177 SW2 pattern for cross-test pollution discipline).

Each it.each test: render at child path → assert child marker visible → `act(() => useAuthStore.setState({ user: testUser, loading: false }))` → `waitFor` assert `/dashboard` "Welcome!" marker visible. Negative case: just render at child path, assert child marker present + `/dashboard` marker NOT present.

Local vitest: **1108 passed / 12 skipped / 0 failed** in 30.31s (W177 baseline 1104 + 4 new W178 cases = exact target). 5 consecutive runs would extend cross-session flake band measurement; single-run sufficient for SW1 close per W141 anti-pattern #4 (closure attribution after empirical verification).

### File 3: `frontend/vite.config.mts` (+10 / -1)

NEW `routeFileIgnorePattern: "__tests__"` option in `tanstackStart()` config router block. Silences TanStack Router generator warning that fires on every build:

> Warning: Route file "src/routes/__tests__/_public.test.tsx" does not export a Route. This file will not be included in the route tree.

12-line comment block documents:
- Why `__tests__/` co-located with routes (clarity)
- Why prefix-with-`-` workaround (default `routeFileIgnorePrefix: "-"`) doesn't work (clashes with vitest's `*.test.tsx` glob)
- (z) #1 finding: pattern is REGEX not GLOB — initial `"**/__tests__/**"` attempt threw `new RegExp: Nothing to repeat` because `**` isn't valid regex; bare `"__tests__"` substring works correctly

### (z) discoveries

**(z) #1 — TanStack Router's `routeFileIgnorePattern` is REGEX not GLOB** despite warning text suggesting glob-like syntax. Empirically caught at first rebuild attempt: `Error: Invalid regular expression: /\*\*/__tests__/\*\*/g: Nothing to repeat`. Fix: bare `"__tests__"` substring (matches paths containing `/__tests__/`). Documented inline in `vite.config.mts` comment block + as Gotcha addition in CLAUDE.md. **W141 anti-pattern #3 39th vindication** — empirical test caught assumption-style read from warning text.

**(z) #2 — chrome-devtools-mcp viewport (1280×720) layout: InstallPrompt push panel overlaps "Войти" button**. `document.elementFromPoint(buttonCenterX, buttonCenterY)` returned the InstallPrompt's "Уведомления" DIV instead of the button. The button click was being captured by the overlapping panel, not reaching the form submit. Mitigated for the visual smoke by clicking "Скрыть подсказки об уведомлениях" before retrying submit click. Documented for W179+ if real users report similar overlap at specific viewport widths (W118 SW4 `min-h-[260px]` reservation doesn't prevent this at full-width hero layout; real-user reports of /login submit failures should investigate this overlap as a candidate). NOT a W178 regression — pre-existing layout-overlap pattern surfaced during W178 visual smoke.

---

## SW1 verification matrix

### Local gates (each step)

| Gate | Result | Baseline |
|------|--------|----------|
| `npx tsc --noEmit` | 0 errors | W177 0 |
| `npm run lint -- --max-warnings=0` | 0 warnings | W177 0 |
| `npx prettier --check src/routes/_public.tsx src/routes/__tests__/_public.test.tsx vite.config.mts` | clean | (auto-fixed via lint-staged at commit time) |
| `npx vitest run --silent` | **1108p / 12s / 0f** (30.31s) | W177 **1104p / 12s / 0f** (+4 new tests exact) |
| `npm audit` | 2 moderate `ws` upstream | W177 baseline preserved (NOT W178 regression) |

### Bundle baseline (W178 NEW)

Clean `rm -rf dist && npm run build`:

- main JS `index-DZRgbi7a.js` **179,692 bytes** (sha256 `1d9d4d86...575eae`) — **+185 b vs W177 179,507 b** (within plan tolerance ±100-300 b; useEffect closure + selector + useNavigate import + named export bookkeeping)
- server.js **23,600 bytes** (sha256 `3134ca39...068ebfc`) — SAME SIZE as W177 (PublicLayout compiles to server bundle too but produces same output byte count post-Vite environments build)
- `_shell.html` **66,459 bytes** (sha256 `06d901c8...5b5665`) — SAME SIZE as W177
- `sw.js` **53,584 bytes** (sha256 `817f2774...2453a040`) — slight delta ±83 b from W177 (W141 polish A3 documented build-infra non-determinism)
- Tree-shake invariant ✓ (0 `lhci-mock-user` in PROD assets)
- SW IIFE invariant ✓ (`"use strict";(()=>{` prefix preserved per W138 SW2)

W134-W177 ≥37-wave LOCAL-MACHINE BYTE-IDENTICAL bundle invariant **explicitly retired at W178 SW1** (real client-tree code change in route guard layout component). NEW W178 baseline established; reproducibility verified via Build × 1 from clean state. Build × 3 fully-byte-identical claim NOT made — would require empirical verification; defer to polish-pass IF «безупречно?» fires.

### Empirical Caddy → Node SSR → backend chain verification

Rebuilt frontend Docker container via `bash scripts/dc.sh up -d --build frontend` (W170 SW4 helper resolves to project root regardless of caller cwd). Container reached `(healthy)` post-rebuild. Caddy reconnected upstream after a ~5s transient (initial 503 on /healthz immediately post-recreate; settled to 200 within 6s — known Caddy upstream re-resolution behavior).

curl smoke (5 routes via Caddy chain):

| Route | HTTP | Size |
|-------|------|------|
| `/healthz` | 200 | 15 b |
| `/login` | 200 | 21,539 b SSR HTML (-71 b vs W177 21,610 b — slight drift from PublicLayout SSR-rendered into HTML stream; React tree node identity changed) |
| `/forgot-password` | 200 | 16,025 b |
| `/register` | 200 | 22,193 b |
| `/reset-password/sample-token-xyz` | 200 | 18,319 b |

chrome-devtools-mcp visual smoke (2 isolated contexts):

**Unauth context (`wave178-unauth`)**:
- `new_page` http://localhost/forgot-password → renders ForgotPassword form ("Восстановление пароля" / "Введите ваш адрес..."), URL stays at `/forgot-password`, **no redirect** ✓
- Console: only expected baseline noise (1× `/users/me` 401 from W174 + 1× `profile_cache.cleared` warn from W128 SW1 AuthProvider). **0 React #418 hydration errors**.

**Authed context (`wave178-authed`)**:
- `new_page` http://localhost/login → fill email + password → click "Войти" (after dismissing InstallPrompt overlay per (z) #2) → POST /auth/login 200 → full authed bootstrap (csrf-cookie + login + users/me + events + chats + stories + ws/ticket + notifications + news + Open-Meteo weather) → URL = `/dashboard`, h1 = "Доброе утро, Test!☀️" ✓
- `navigate_page` to `/forgot-password` → **immediately redirected to `/dashboard`** ✓
- `navigate_page` to `/register` → **immediately redirected to `/dashboard`** ✓
- `navigate_page` to `/reset-password/sample-token-xyz` → **immediately redirected to `/dashboard`** ✓
- `navigate_page` to `/login` (defense-in-depth — W177 SW1 + W178 SW1 both fire) → **immediately redirected to `/dashboard`** ✓
- Console post-4-navigations: 2 errors of class `AbortError: Transition was skipped` + paired `Uncaught (in promise)`. **TanStack Router internal transient when redirect throws mid-navigation; pre-existing behavior class documented in CLAUDE.md ## Gotchas (W167 SW2 reference); NOT a W178 regression**. **0 React #418 hydration errors** across all 4 navigations.

5 of 5 visual smoke scenarios PASS. End-state correctness proven; mechanism dispatch (beforeLoad vs useEffect) not isolated by visual smoke but exercised separately by 4 unit tests.

### Verification mechanism boundary (honest framing)

The visual smoke proves the **user-facing outcome** but cannot distinguish which of the two mechanisms fired on a given navigation:

| Mechanism | When it fires | Visual smoke can detect? |
|-----------|---------------|--------------------------|
| `_public.tsx beforeLoad` (W174 SW1) | Initial route mount; reads `useAuthStore.getState()` synchronously | YES — but indistinguishable from useEffect at end-state |
| `PublicLayout useEffect` (W178 SW1) | Layout mounts; user transitions null→set DURING mount | YES — but masked by beforeLoad firing first in most cases |
| `Login.tsx useEffect` (W177 SW1) | Login mounts inside PublicLayout's Outlet; user transitions | YES — defense-in-depth fires alongside W178 useEffect on /login only |

The **4 unit tests at `_public.test.tsx`** specifically exercise the W178 SW1 reactive useEffect path via `act(() => useAuthStore.setState({ user: testUser }))` after render — covering the post-mount transition path that beforeLoad cannot see. This is the key coverage for the §Honesty #2 closure (the gap was reactive transitions, not navigation-time redirects).

### Pre-commit chain (W156 SW4 husky)

SW1 commit `381f85578` fired W156 SW4 husky pre-commit chain cleanly:
- lint-staged: prettier --write + eslint --fix → 2 files processed, modifications applied
- detect-secrets scan → PASSED
- Detect hardcoded secrets → PASSED
- ruff/bandit/mypy → skipped (no .py files)
- Reject Python 2 except syntax → PASSED

**NO `--no-verify` bypass**. W141 anti-pattern #15 (ARCHIVED W159 SW4) preserved **43rd consecutive wave**.

---

## SW2 — Audit + memory + N+3 rotation

**Commit**: pending after this audit doc + supporting file updates

### N+3 rotation

`git mv docs/audits/AUDIT_WAVE175.md docs/audits/archive/AUDIT_WAVE175.md`

Active waves post-W178: **W176 / W177 / W178**. Archive count: 61 → 62.

### Documentation updates

- NEW `docs/audits/AUDIT_WAVE178.md` (this file)
- `docs/audits/INDEX.md` — move W175 from active to archive (insert at top of archive list per reverse-chronological convention); add W178 as newest active row
- `CLAUDE.md`:
  - Audit Trail rotation history line: append `W178 SW2 (W175 → archive)`
  - Audit Trail new Wave 178 row (concise per W134 user-feedback recommendation, ~1.5 KB referencing AUDIT_WAVE178.md for detail)
  - `## Gotchas` section: append 1 NEW entry documenting the `_public.tsx` layout-level reactive redirect pattern + the `routeFileIgnorePattern` REGEX-vs-GLOB (z) #1 finding
- `memory/MEMORY.md` (`.claude` profile):
  - Active backlog: replace W177 entry with W178 detail
  - Audit History table: add W178 row at top; push W174 off (only 3 most-recent CLOSED waves kept verbose)
- NEW `memory/wave178_backlog.md` in `.claude` profile (post-W178 §Honesty trajectory + carry-forward + W179+ candidates)
- NEW `memory/wave179_opening_prompt.md` in `.claude` profile (canonical opening prompt for next session)

---

## §Honesty trajectory

**Pre-W178**: 0-9 OPEN (W177 close baseline per opening prompt).

**Post-W178**: **0-9 OPEN** (count unchanged in worst case; potential -1 to 0-8 if (z) discoveries don't count as new caveats per W138 Lesson #8 dynamic counting). Closure:

- ✅ **W177 §Honesty #2 EMPIRICALLY CLOSED** — Approach 1 extension shipped + verified through real Docker chain (4 of 4 redirect cases + 1 of 1 negative case + 4 unit tests).

NEW W178-introduced caveats (3, honestly framed per `feedback_perfectionism.md`):

1. **(z) #1 — `routeFileIgnorePattern` regex-vs-glob fix shipped**: in-scope SW1 fix, NOT deferred. Documented in vite.config.mts inline + CLAUDE.md Gotcha for future-wave awareness.
2. **(z) #2 — InstallPrompt push panel overlapping login button at chrome-devtools-mcp viewport 1280×720**: NOT a W178 regression; pre-existing layout overlap pattern surfaced during visual smoke. W179+ candidate if real users report similar at specific viewport widths.
3. **Visual smoke mechanism-boundary ambiguity (honest framing)**: end-state correctness proven for all 4 redirect navigations + 1 unauth case, but visual smoke cannot isolate W174 SW1 beforeLoad path from W178 SW1 useEffect path. Unit tests at `_public.test.tsx` cover the reactive useEffect path specifically via `act(setState)` — closure coverage relies on this unit test layer.

Carry-forward unchanged from W177 close (6 items): W177 §Honesty #3 (state.from race) / W177 §Honesty #4 (npm audit ws) / W176 §Honesty #4 (authed visual smoke /dashboard etc.) / W175 §Honesty #7 (ChatWindow msg-bubble-sent) / W170 §Honesty #1 (helper-script enforcement) / W174 §Honesty #4-routeGuards + #4-playwright (test coverage gaps) / W134 §Honesty #2 (bundle delta) / W134 §Honesty #10 (/messenger Phase 5).

---

## W141 anti-pattern compliance

| # | Pattern | W178 vindication |
|---|---------|------------------|
| 1 | STRICT 1-iter SACRED | **31st total vindication** — SW1 landed in 1 iter; (z) #1 routeFileIgnorePattern regex fix was within-iter SAME-mechanism per W138 Lesson #1 (not a mechanism pivot); (z) #2 InstallPrompt overlay was test-infrastructure workaround, not production code change. 0 mechanism iter cycles. |
| 3 | Phase 3 Review | **59th vindication (+1 from W177 baseline 55-58)** — direct Reads of `_public.tsx`, `_auth.tsx`, `Login.tsx`, `Login.test.tsx`, `useLoginFlow.ts`, `renderWithRouter.tsx`, ForgotPassword.test.tsx, the route files for register/reset-password during Phase 1 surfaced 3 critical findings pre-implementation: (a) renderWithRouter docstring caveat about layout routes; (b) `_public.tsx` component was stateless arrow function (no existing logic to preserve); (c) page tests use renderWithRouter directly so they wouldn't be affected by adding useEffect to _public.tsx layout (no msw scoping cascade like W175 SW10 hit). |
| 3 | Phase 3 Review | **39th vindication for (z) #1** — empirical build attempt disproved Agent-style assumption that `routeFileIgnorePattern` accepts glob syntax. |
| 4 | No premature "Closes" | **29th vindication (+1 from W177 baseline 28)** — SW1 commit subject says "close W177 §Honesty #2" but body explicitly notes empirical verification through real Docker chain BEFORE attributing closure. This audit doc attributes closure only AFTER 5 visual smoke scenarios + 1108 vitest cases passed. |
| 15 | ARCHIVED W159 SW4 | **43rd consecutive wave preserved** — SW1 commit `381f85578` + SW2 audit commit (pending) both fire W156 SW4 husky pre-commit chain cleanly. NO `--no-verify` bypass. |

---

## W179+ candidates (priority order)

Per W171 Lesson #1: maintenance mode means waves fire on real triggers.

| # | Option | Trigger | Effort | Closes |
|---|--------|---------|--------|--------|
| ⭐ A | **Continue maintenance** | No specific motivation; project rests | 0 (close session) | — |
| B | `state.from` redirect-path race fix | User notices /events → /login → login lands on /dashboard not /events | ~30-60 min | W177 §Honesty #3 |
| C | `npm audit fix` ws CVE | User wants 0 vulnerabilities baseline | ~5-10 min | W177 §Honesty #4 |
| D | W176 §Honesty #4 authed visual smoke | User wants full empirical footer + 5 authed routes verification | ~30-60 min | W176 §Honesty #4 |
| E | routeGuards.test.tsx infrastructure | User wants W173+W174+W177+W178 test coverage extension | ~3-4h | W174 §Honesty #4-routeGuards |
| F | Playwright wave174+178-login-flow e2e | User wants e2e regression coverage | ~2-3h after CI infra | W174 §Honesty #4-playwright |
| G | ChatWindow msg-bubble-sent visual fix | User notices chat bubble visual breakage | ~1-2h | W175 §Honesty #7 |
| H | Tier 4 housekeeping | Quarterly check fires (next window per W170 SW3 calibration: W177-W181) | ~30 min | operational only |
| I | /messenger Phase 5 SSR enable | User wants SSR expansion | ~3-5h own wave | W134 §Honesty #10 (reverses W161 SW2 by-design) |
| J | Helper-script enforcement | User wants to close W170 §Honesty residual | ~1-2h | W170 §Honesty #1 |
| K | Long-tail polish | User wants depth-over-breadth | ~3-5h | W134 §Honesty #2 |
| L | Task G admin-smoke auto-activates on PR merge | External (PR merge happens) | 0 min automatic | W169 §Honesty residual operational |

---

## Honest scope-end framing

W178 is a **narrow, additive, well-bounded closure** of a single W177 scope-trade-off. The mechanism mirror of W177 SW1 (reactive useEffect on `useAuthStore.user`) at the layout level produced exactly the planned outcome (5 routes covered via single mechanism; defense-in-depth preserved on /login; unit test coverage for the reactive path; visual smoke for end-state correctness).

The 2 NEW (z) discoveries (routeFileIgnorePattern regex-vs-glob + InstallPrompt overlay) are documented honestly per `feedback_perfectionism.md`: (z) #1 shipped as fix in SW1 commit (in-scope; NOT deferred), (z) #2 documented for future-wave awareness (test-infrastructure-only workaround; NOT a production code change).

If user invokes «безупречно?» probe post-close, expected polish-pass scope (~30-60 min):
- Empirical Build × 3 verification of new W178 baseline (current claim is Build × 1 + structural argument)
- Cross-session vitest 5/5 flake band measurement (current claim is single 1108p run)
- CI Matrix Expansion verification post-push (expected GREEN per W177 SW5 precedent)
- Potential additional Gotcha entries if any subtle finding surfaces

---

## Polish-v1 empirical confirmations (post «безупречно?» probe, 2026-05-21)

User invoked «безупречно?» probe at session-end of SW2. Polish-v1 ran the deferred verification items + surfaced 1 latent housekeeping finding.

### Empirical Build × 3 BYTE-IDENTICAL confirmed

3 fresh `rm -rf dist && npm run build` runs from clean state produced IDENTICAL sha256 across runs:

- main JS `index-DZRgbi7a.js` 179,692 b — sha256 **`1d9d4d863663c2717fde1f3f0dc5fbc17d51e78fe8c7bff232ad1d8aef575eae`** × 3
- server.js 23,600 b — sha256 **`3134ca3964e7c434f83a3d1bb3d10eafd76cf1189b89b32e3f516d657068ebfc`** × 3

Build × 3 reproducibility EMPIRICALLY VERIFIED for the W178 NEW baseline. This delivers on the plan-file's "Build × 3 fully-byte-identical claim NOT made — would require empirical verification; defer to polish-pass IF «безупречно?» fires" promise. The new baseline is reproducible from source × 3 consecutive clean builds.

`_shell.html` 66,459 b and `sw.js` 53,584 b have same byte count across builds but per-run sha varies — known W141 polish A3 non-determinism source (CSP nonce in shell + workbox precache revision hash in sw.js).

### Cross-session vitest × 5 flake band = 0

5 consecutive vitest sessions + 1 verification follow-up = **6 total runs all 1108 passed / 12 skipped / 0 failed** (W177 baseline 1104 + 4 new W178 cases = exact target):

| Run | Duration |
|-----|----------|
| 1 | 30.92s |
| 2 | 30.67s |
| 3 | 29.37s |
| 4 | 29.56s |
| 5 | 29.41s |
| Verification follow-up | 31.50s |

Duration band 29.37-31.50s (±1.1s; tight). **0 flaky tests across 6 sessions × 1108 cases = 6,648 test invocations**. Confirms W178 SW1 unit tests + W177 baseline tests are deterministic; no msw scoping cascade or AbortSignal race introduced.

### Storybook build verified post `vite.config.mts` change

`routeFileIgnorePattern: "__tests__"` addition was a real risk surface — `tanstackStart()` plugin is shared between main app build (vite.config.mts) AND Storybook iframe build (`.storybook/main.ts` viteFinal hook per W125 Phase 2 + W146 SW3 history). Polish-v1 ran `npm run build-storybook` → **success in 8.56s** (within W123 SW1 baseline ~8s ±1s tolerance). Storybook iframe.html emitted; main-app chunks tree-shake correctly. Routes/__tests__/*.test.tsx files correctly ignored by both TanStack Router generator AND Storybook's mock-loader.

### i18n parity + Cargo.lock + tree-shake all GREEN

- **i18n parity**: 18 tests passed in `src/tests/translationParity.test.ts` (walks every locale file recursively per W112 SW1) — 0 RU/EN drift.
- **Cargo.lock**: `git diff --stat HEAD -- frontend/rust-crypto/Cargo.lock` blank — idempotent across W178 SW1 build cycle (≥38 wave invariant preserved).
- **Tree-shake invariant**: `grep -c "lhci-mock-user" frontend/dist/client/assets/*.js` = 0 across ALL ~180 PROD chunks. VITE_LHCI bypass code correctly tree-shaken from production bundle.
- **SW IIFE invariant**: `head -c 25 dist/client/sw.js` = `"use strict";(()=>{` — W138 SW2 IIFE wrapping preserved.

### Cross-ref integrity verified

- `docs/audits/INDEX.md`: 4 mentions of `AUDIT_WAVE17[5-8]` (W175 + W176 + W177 + W178 all referenced; W175 link path correctly archive/).
- `CLAUDE.md`: 1 W178 row at top of bullet list; new Gotcha entries inserted before W177 MFA gotcha; rotation history line includes `**W178 SW2 (W175 → archive)**`.
- `memory/MEMORY.md`: 2 W178 mentions (Active backlog row + Audit History row); 24,277 b (under 24,400 ceiling with 123 b headroom).
- Active waves consistent everywhere: **W176/W177/W178**.

### CI verification (at polish-v1 commit time)

CI - Matrix Expansion run `26211125590` for SW2 commit `0959665de`:

- **38 of 40 sub-jobs SUCCESS** at polish-v1 commit time (Contract Tests + Pre-commit & Linting + CI Diagnostic + Go Fuzz Tests + Validate docker-compose + Backend Type Check + Helm Lint & Validate + Trivy Image Scan + Alembic Migrations + Verify Runtime Requirements + DB Migration Gate + SBOM Generation + Verify OpenAPI Types + SLSA Provenance Dry-Run + Go Integration Tests (3 services) + Security Audit (6 sub-jobs: detect-secrets + Python Dep Audit + Go Vuln Scan + Semgrep SAST + Generate SBOM + Node.js Dep Audit + Container Security Scan) + Frontend Tests (Production Build + Unit Tests + Lint & Format + Bundle Analysis) + E2E Tests (chromium) + Backend Tests (Unit + Integration All-Python 3.13) + Go Tests × 3 (gateway + ws-hub + file-processor; Lint + Test) + Go Integration Tests × 3).
- **1 skipped** (Post-fix Formatting Bot Push — expected behavior, only fires on lint-staged auto-format failures during CI).
- **1 in_progress**: Frontend Tests / Lighthouse Audit (~23-25 min per W160 SW2 calibration; CI Matrix overall ~26 min at polish-v1 commit time).
- **7 of 8 top-level workflows SUCCESS** (Dependency Review + DB Performance Gate + Generate OpenAPI Spec + Go Lint & SBOM + Contract Validation + Chromatic + Auto-merge dependabot skipped expected; CI - Matrix Expansion in_progress with Lighthouse Audit as final gate).

**Polish-v2 captured final CI outcome below**: Matrix Expansion run `26212297489` completed SUCCESS at ~08:09 UTC (~29 min total runtime including Lighthouse Audit at ~28 min — slightly above W160 SW2 documented calibration ~23-25 min but well under workflow timeout). **39 of 39 jobs SUCCESS + 0 failures**. Performance Gate (last in_progress) completed cleanly. **W178 fully closed at empirical CI level**.

### NEW W178 latent finding — pre-existing prettier drift NOT W178 regression

`npx prettier --check .` from frontend/ flagged **245 files** with code style issues. Verified: NONE of the W178-touched files (`frontend/src/routes/_public.tsx`, `frontend/src/routes/__tests__/_public.test.tsx`, `frontend/vite.config.mts`) are in the flagged list — those were prettier-checked at SW1 commit time + auto-formatted via lint-staged at commit. The 245 files are:

- Cargo build artifacts under `wasm-sanitizer/target/`, `rust-crypto/target/`, `rust_ext/target/`, `wasm-sanitizer/pkg/`, `rust-crypto/pkg/` — should be in `.prettierignore`
- A handful of pre-existing root-level files (`public/sw.js` generated, `README.md`, `TOKENS.md`, `scripts/*.cjs`)

**Filed as W179+ housekeeping candidate**: extend `frontend/.prettierignore` to exclude cargo target dirs + wasm-pack pkg dirs (~5-10 min). NOT a W178 regression — pre-existing accumulated drift dating back multiple waves; not surfaced earlier because no full-repo prettier scan was triggered during regular SW workflow (lint-staged scopes to staged files only).

### Polish-v1 §Honesty trajectory update (no change in count)

**Pre polish-v1**: 0-9 OPEN. **Post polish-v1**: 0-9 OPEN. Polish-v1 surfaced 1 NEW W179 housekeeping candidate (pre-existing prettier drift, NOT W178 regression) but does NOT add a §Honesty caveat — it's pre-existing latent drift, like the ws CVE upstream disclosure in W177 §Honesty #4. Filed as ordinary W179+ candidate, not §Honesty caveat.

Build × 3 EMPIRICALLY VERIFIED (was Build × 1 + structural argument) + vitest × 6 flake band = 0 (was single 1108p run) + Storybook verified — these are STRENGTHENING the SW2 audit claims, NOT closing additional caveats.

### Polish-v1 summary

**8 polish items verified GREEN**:
1. ✅ Build × 3 BYTE-IDENTICAL
2. ✅ Cross-session vitest × 6 flake band = 0
3. ✅ Storybook build success post `routeFileIgnorePattern` change
4. ✅ i18n parity 18p
5. ✅ Cargo.lock idempotent
6. ✅ Tree-shake invariant (0 lhci-mock-user in PROD)
7. ✅ SW IIFE invariant
8. ✅ Cross-ref integrity (INDEX.md + CLAUDE.md + MEMORY.md)

**2 pending items** for polish-v2:
1. ⏸ CI Matrix Expansion final outcome (Lighthouse Audit in_progress at polish-v1 commit time; expected GREEN per W160 SW2 calibration ~24 min runtime + W177 SW5 precedent)
2. ⏸ Polish-v1 commit itself fires W156 SW4 pre-commit chain — verify clean

**1 NEW W179+ candidate surfaced**: `.prettierignore` update for cargo target + wasm-pack pkg dirs (~5-10 min; pre-existing drift, NOT W178 regression).

---

## Polish-v2 final empirical CI verification (post «безупречно?» continuation, 2026-05-21)

User invoked polish-v2 action via scheduled wakeup after polish-v1 completed.

### CI Matrix Expansion run `26212297489` COMPLETED SUCCESS

Final state captured at ~08:09 UTC (~29 min total runtime):

- **Status**: completed
- **Conclusion**: SUCCESS
- **Jobs**: 39 of 39 SUCCESS + 0 failures (Post-fix Formatting Bot Push skipped expected per W178 SW2 audit)
- **Lighthouse Audit**: completed SUCCESS at ~07:40 + ~28 min = ~08:08 UTC (slight overshoot vs W160 SW2 documented calibration ~23-25 min; well under workflow timeout)
- **Performance Gate**: completed SUCCESS (the last in_progress job before Matrix-level completion)

Combined with the 7 top-level workflows already SUCCESS at polish-v1 commit time (Dependency Review + DB Performance Gate + Generate OpenAPI Spec + Go Lint & SBOM + Contract Validation + Chromatic + Auto-merge dependabot skipped expected), this delivers **W178 fully closed at empirical CI level**.

### Framing propagation completed

The "Build × 1 + structural argument" framing in CLAUDE.md row + wave178_backlog.md + wave179_opening_prompt.md + MEMORY.md was updated to **"Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED in polish-v1"**. wave179_opening_prompt.md already had the framing post-polish-v1 (updated in-session). polish-v2 commit also explicitly captures the CI Matrix Expansion SUCCESS as load-bearing evidence.

### W178 closure attribution (W141 anti-pattern #4 final vindication)

All 3 W178 commits (`381f85578` SW1 + `0959665de` SW2 + `1f3622236` polish-v1) plus this polish-v2 audit-only commit fired W156 SW4 husky pre-commit chain cleanly. NO `--no-verify` bypasses. **W141 anti-pattern #15 (ARCHIVED W159 SW4) preserved 43rd consecutive wave**.

Closure attribution sequence honored W141 anti-pattern #4 "no premature 'Closes' attribution":
1. SW1 commit subject "close W177 §Honesty #2" but body explicitly noted empirical verification through real Docker chain BEFORE attributing closure
2. SW2 audit attributed closure ONLY after 5 of 5 visual smoke scenarios + 1108 vitest cases passed
3. Polish-v1 audit section added empirical Build × 3 + vitest × 6 + Storybook verification
4. **Polish-v2 (this section) adds the final CI Matrix Expansion SUCCESS verification** — closure is now empirically complete at every layer (unit → integration → visual → bundle reproducibility → CI Matrix)

### W178 final state declaration

**§Honesty trajectory**: 0-9 OPEN post-W178 (unchanged from polish-v1 — closures are documented honestly; 2 within-wave (z) discoveries shipped as fix + test-infra workaround). 1 NEW W179+ candidate (`.prettierignore` housekeeping for cargo + wasm-pack pkg dirs).

**Bundle**: Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED — main JS `index-DZRgbi7a.js` 179,692 b sha `1d9d4d86...575eae` × 3 from clean state.

**Tests**: 1108p / 12s / 0f × 6 sessions ≅ 0 flake band (durations 29.37-31.50s, ±1.1s).

**CI**: 7 main-workflow SUCCESS + Matrix Expansion 39 sub-jobs SUCCESS + 0 failures.

**Production deploy is unambiguously ready post-W178 polish-v2**. Primary user pain status: NONE user-facing-wedge class across W156-W178.

---

Full detail in this audit doc + plan file. Memory references (`.claude` profile only): `memory/wave178_backlog.md`, `memory/wave179_opening_prompt.md`.

**Production deploy is unambiguously ready post-W178.** Primary user pain status: NONE user-facing-wedge class across W156-W178.
