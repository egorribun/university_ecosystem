# Wave 136 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 135 CLOSED + POLISHED** (2026-05-08) — L scope: B + Aggressive cleanup +
Option E Path B per user-approved AskUserQuestion 3-question flow (Q1=L,
Q2=Aggressive, Q3=Path B full commitment). Plus polish-pass post user
"безупречно?" probe closed 2 more caveats + ran 7 invariant verifications.

### 4 git commits ahead of W134 close (`a26ca7cbd`)

1. **`6c5ada141`** `feat(wave135-sw1-cleanup-aggressive)` — Aggressive cleanup. 4 files +230/-34. Full AbortController removal in `useProfileSync.ts` (queryClient.cancelQueries is sole cancellation; `isCancel(error)` axios canonical replaces signal.aborted check); useSessionManagement migration to factory exports `updateSessionInCache` + `invalidateSessions` in sessions.ts; 11 new sessions tests. Vitest **1052p / 12s / 0f**.

2. **`d58b5c74b`** `feat(wave135-sw3-build-orchestrated)` — Retires wave127-build-x3.sh via integrated `frontend/scripts/build-orchestrated.mjs` (~280 LoC, 6 steps). 4 files +363/-42. `BUILD_SKIP_PWA=true` env-flag gates `VitePWA({disable: true})` in vite.config.mts. Subprocess vite build with kill-after-artifacts (poll for _shell.html + server.js stable for 2s, then SIGTERM). Standalone `workbox-build.injectManifest()` precaches 209 files / 4.80 MB. Build × 3 BYTE-IDENTICAL: `index-DqqHVXgy.js` 139,808 + `_shell.html` 65,864 (matches W134 baseline exactly). Build duration 26s × 3 (vs wave127's ~95s × 3).

3. **SW2** Docker chain verification — no commit. Curl-only fallback per plan risk-fallback (chrome-devtools-mcp `take_snapshot` Windows wall). Caddy chain → frontend:3000 SSR proven. Discovered 2 backend/gateway issues (W136 candidates).

4. **`abbf29687`** `docs(wave135-sw4-audit-handoff)` — NEW `docs/audits/AUDIT_WAVE135.md` (~330 lines), NEW `memory/wave135_backlog.md` + `memory/wave136_opening_prompt.md`, CLAUDE.md ## Audit Trail W135 row + 3 new gotchas, N+3 rotation `git mv docs/audits/AUDIT_WAVE132.md docs/audits/archive/AUDIT_WAVE132.md`. 6 files +688/-3.

5. **`5d41d5701`** `chore(wave135-polish)` — Polish-pass post "безупречно?" probe (~15-20 min). 4 files +38/-24. **Closed 2 caveats**: W135 §Honesty #12 cross-session vitest 5/5 × 1052p / 12s / 0f flake band = 0; W134 §Honesty #6 MEMORY.md path normalization (17 broken `../../../../docs/audits/` → 21 clean `docs/audits/` text refs; the prior `../../../../` resolved to `C:\Users\egorribun\` from USER `.claude` dir — needed SIX levels not FOUR). **7 invariant verifications**: commit-stat cross-check via `git show --stat` (all match exactly), memory-link resolution 21/21, archive 16 W117-W132 audit files, npm audit 0, Cargo.lock no drift, build × 1 BYTE-IDENTICAL (139,808/65,864/53,181), AUDIT REMAINING #11 consolidated into #9 (both Linux CI duplicates). Discovered W134 SW4 commit message described `memory/wave134_backlog.md` written to git-tracked REPO but actually written to USER `.claude` dir (not git-tracked). My W135 SW4 wrote to REPO; polish-pass copied to USER dir as well — both locations now have wave135_backlog.md + wave136_opening_prompt.md.

Verify session-start: `git log --oneline a26ca7cbd..HEAD | wc -l` → **4**

---

## NO-DEPLOY scope clarified 2026-05-08 (W134/W135 carried forward)

Cluster deployment NOT pursued. Goal is "fully working + visually + internally
flawless локально + структурно". Cluster-dependent items remain removed:

- ~~Phase 6 ACTUAL canary rollout~~ ~~RUM wiring~~ ~~Real LCP measurement~~
- ~~SECURITY_COOKIE_SAMESITE_OVERRIDE prod SSO callback~~
- ~~Caddy weight flip live test~~ ~~frontend-stable image build~~
- ~~kubectl apply --dry-run=server~~

W125-W133 SSR migration arc remains shipped + locally verified + structurally
correct; W134 + W135 closed Phase 5 polish + housekeeping + Windows build
infrastructure retirement. Real LCP victory (~12s → <2.5s) is theoretical
under no-deploy goal — architecture ready, no production traffic to measure on.

---

## Bundle baseline (PROD × 3 reproducible)

- **`dist/client/assets/index-DqqHVXgy.js` 139,808 bytes** (BYTE-IDENTICAL to W134 baseline; SW3 build pipeline change is byte-neutral)
- **`_shell.html` 65,864 bytes** (BYTE-IDENTICAL to W134 baseline)
- **`sw.js` 53,181 bytes** (NEW: real compiled SW with workbox manifest, was 1,872-byte placeholder pre-W135 — net +51,309 bytes service-worker delta is improvement, not regression)
- **`server.js` 39,373 bytes**
- Reproducibility ≥ 7 waves (build × 3 verified post-SW3 via new orchestrator; SW4 docs-only had zero bundle impact expected)

## Gates baseline (preserved through W135 + polish)

- tsc 0 errors, lint 0 warnings (`max-warnings=0`; broader src/ scan
  including `eslint-plugin-react-compiler` at error level)
- vitest **single-run + cross-session 5-run = 5/5 × 1052p / 12s / 0f**
  (W134 1041 + 11 SW1 sessions tests = 1052; cross-session flake band = 0 measured in polish-pass)
- pytest backend slice NOT re-run (no backend changes in W135 — W134 baseline 52p preserved by invariant)
- npm audit **0 vulnerabilities** (re-verified in polish-pass)
- Cargo.lock no drift (idempotent ≥ 25 waves at end of W135 polish)
- i18n parity 18p (translationParity.test.ts; CLDR-aware EN/RU)
- MEMORY.md size **24,090 bytes** ✓ (< 24,400; **21/21 referenced memory files resolve** post-polish)
- Archive directory has all 16 W117-W132 audit files (W132 newly rotated in SW4)
- Tree-shake invariant ✓ (PROD `grep -l "lhci-mock-user" dist/client/assets/*.js`
  → 0; VITE_LHCI builds → 1 W116 SW3 useFocusTrap chunk known-exception)
- **Build × 4 reproducibility WITHOUT wave127-build-x3.sh** ✓ (NEW W135 SW3 invariant: build × 3 post-SW3 + 1 post-polish all IDENTICAL hash + sizes)

**Active waves after N+3 rotation**: W133 / W134 / **W135**

---

## SSR routes (8 total — preserved through W135)

W135 added NO new SSR routes. SW1 + SW3 are infrastructure-level changes; no
`ssr: false` → `ssr: true` conversions.

| Route | Status | When |
|-------|--------|------|
| `/dashboard` | SSR | W128 SW3 |
| `/events` | SSR | W129 SW1 |
| `/events/$id` | SSR | W129 SW2 |
| `/news` | SSR | W129 SW4 |
| `/news/$id` | SSR | W129 SW5 |
| `/schedule` | SSR (full sequential per W133 SW3) | W130 SW2 + W133 SW3 |
| `/profile` | SSR | W133 SW4 |
| `/settings` | SSR + tab=N URL param + Security-tab sessions prefetch | W133 SW5 + W134 SW2 |

**Remaining `ssr: false` siblings**: 2 (messenger × 2 — heavy WebSocket +
IndexedDB at render time, deferred indefinitely by no-deploy "production-as-is"
decision).

`/map` + `/activity` preserved at `ssr: 'data-only'` (W127 SW6 annotations
under permissive parent `_auth.tsx ssr: true` W128 SW2).

---

## Wave 136 candidates (15+ candidates across 5 tiers)

### REMOVED from backlog (closed by W135 SW1+SW2+SW3+polish)

- ✅ **AbortController cleanup in useProfileSync** (W134 §Honesty #3) — closed via SW1
- ✅ **useSessionManagement mutation path migration to factory** (W134 §Honesty #5) — closed via SW1
- ✅ **Option B chrome-devtools-mcp through Docker chain** (W134 §Honesty #1 + #8) — closed PARTIAL via SW2 (curl + Caddy chain proven; chrome-devtools snapshot wall documented as sub-deferral)
- ✅ **Option E vite-plugin-pwa Windows hang** (W126 polish #3) — closed at orchestration level via SW3 (wave127-build-x3.sh retired, integrated build-orchestrated.mjs reproducible). Structural hang remains.
- ✅ **Cross-session vitest 5-run flake band measurement** (W135 §Honesty #12) — closed via polish: 5/5 × 1052p clean.
- ✅ **MEMORY.md `../../../../docs/audits/` path normalization** (W134 §Honesty #6) — closed via polish: 17 broken paths → 21 clean text refs.

### Tier 1 — HIGH priority (W135 discoveries; recommended W136 starts here)

- **Gateway+backend JWT protocol mismatch fix** (~1-2h, HIGH PRIORITY) — `services/gateway/middleware/auth.go:720` checks `claims.IsActive` from JWT but backend JWT only embeds `sub/aud/iat/nbf/exp/jti`. ALL authed gateway requests return 403 "user account is not active". Backend direct (port 8000) correctly returns full user with `is_active: true`. Fix choices: (a) backend embeds is_active in JWT (cheaper but JWT becomes stale on user deactivation), (b) gateway looks up DB on each request with cache (more correct, +latency, gateway already has L1 + Redis L2). Recommend (b). Add backend ↔ gateway JWT contract test to prevent regression.

- **chrome-devtools-mcp Windows snapshot wall investigation** (~1-2h) — CDP `Accessibility.getFullAXTree timed out` + `Runtime.evaluate timed out`. Same family as W132 polish round 2. `list_network_requests` + `list_console_messages` work fine. Paths: (a) CDP backchannel timeout config, (b) alternative real-Chrome via Playwright with extended timeout, (c) file upstream issue. Affects ALL future visual smokes on this dev workstation.

- **`failed_login_attempts.user_id` NOT NULL schema fix** (~30min) — INSERT fails for non-existent emails (NotNullViolation on `user_id=NULL`). Pre-existing backend schema bug. Fix: NOT NULL → nullable, OR conditional INSERT only when user exists.

### Tier 2 — foundational structural (W135 carry-forward)

- **build-orchestrated.mjs structural hang trace** (~2-3h) — second hang point in tanstackStart-core not investigated. Use `process._getActiveHandles()` instrumentation OR direct vite/tanstackStart issue file. Closes the underlying hang properly (vs W135 SW3's kill-after-artifacts workaround).

- **Workbox config drift fix** (~30 min) — export `PWA_INJECT_CONFIG` as named constant from vite.config.mts; import in build-orchestrated.mjs to avoid hardcoded mirror.

- **build-orchestrated.mjs Linux CI validation** (~30 min) — workflow_dispatch trigger to ensure Linux behavior also works (faster — no hang, but kill-after-artifacts pattern still operates correctly).

### Tier 3 — housekeeping batch (W134 + W135 carry-forward)

- **MEMORY.md `../../../../docs/audits/` path normalisation** (W134 §Honesty #6, ~30min) — documentation-style not navigation-style; fix to use absolute or shorter relative paths.
- **`frontend/nginx.conf` deletion** (~30min) — unused Phase 6 rollback safety irrelevant under no-deploy.
- **spicedb healthcheck investigation** (~30-60min).
- **file-processor + grafana + prometheus + tempo + loki + imgproxy healthchecks** (~1h).

### Tier 4 — cross-cutting "внутренне + визуально безупречно"

- **Test infrastructure expansion** (~2-4h) — close vitest skips + e2e gaps (a11y-public WebKit OOM W115 SW1 partial; mobile-webkit /404 W116 SW1 remainder).
- **LHCI gate ratchet on local baseline** (~1-2h) — Perf warn → error@higher; uses `lhci-windows-fallback.mjs` OR Linux CI workflow_dispatch.
- **a11y deep-audit cross-browser** (~2-3h) — re-attempt WebKit + mobile-webkit axe-core sweep.
- **i18n parity consolidation** (~1-2h).
- **Per-page visual audit** (~0.5-1 wave per page) — opportunistic discovery on 8 SSR routes.
- **Storybook/Chromatic activation** (~1-2h) — unblocked W123 SW1; requires user-side `CHROMATIC_PROJECT_TOKEN` secret + `vars.CHROMATIC_ENABLED=true`.

### Tier 5 — optional big scope (explicit user decision)

- **Option Q Messenger × 2 polish arc** (~5-7 waves) — heavy WebSocket interactivity per Map(23)/Schedule(14) precedent. Pursue OR explicitly punt as "production-as-is".
- **Option R Admin pages depth audit + polish** (~3-5 waves). Pursue OR explicitly punt.

### NEW W136 candidates from W135 §Honesty (12 caveats post-SW4)

Most caveats already mapped to Tier 1-3 above. Cross-session vitest 5-run flake-band measurement is a polish-pass-of-W135 candidate (run during anticipated "безупречно?" pass at session end), not a separate W136 task.

---

## Pragmatic recommendation (no-deploy scope)

- **Best ROI immediate (Tier 1)**: **Gateway+backend JWT mismatch fix + chrome-devtools-mcp wall investigation** (~3-4h combined). Both are HIGH-impact W135 discoveries. JWT fix unblocks ALL authed gateway calls (currently 100% fail); chrome-devtools investigation unblocks future visual smokes on Windows dev workstation.
- **Best W136 starter combo**: **Tier 1 (3 fixes ~3-4h) + Tier 2 (build-orchestrated.mjs structural fix + Workbox config drift ~3h)** (~6-7h) — closes ALL 3 W135 discoveries + retires the kill-after-artifacts workaround for true structural fix.
- **Closes most §Honesty deferrals**: **Tier 1 + Tier 2 + Tier 3 housekeeping (MEMORY.md path norm + nginx.conf deletion + healthchecks ~1.5h)** (~7-9h) — drops to ≤3 remaining caveats from W135.
- **Tier 5 explicit decision**: User to confirm Messenger/Admin scope OR punt as "production-as-is" before W137+.

---

## Read mandatory files in order

1. **`docs/audits/AUDIT_WAVE135.md`** — full SW narrative + verification matrix + §Honesty probe (12 caveats; 4 closed via implementation; 8 remain) + W136 candidates list at bottom + lessons-learned for W136+
2. **`memory/wave135_backlog.md`** — close-status entry-point file refs; §Honesty section split CLOSED-via-implementation vs REMAINING
3. **`memory/wave136_opening_prompt.md`** — this file
4. ~~`docs/CANARY_ROLLOUT_PHASE6.md`~~ — NOT REQUIRED under no-deploy scope
5. **`docs/plans/2026-05-08-wave133-c-plus-d-design.md`** — W133 architectural decisions + 4-alternative mechanism comparison (Bridge mechanism context)
6. **`docs/plans/2026-05-01-wave125-ssr-design.md`** § Phase 5-6 — original design source
7. **`CLAUDE.md`** ## Audit Trail W135 row + 3 new W135 gotchas section:
   - Wave 135 SW1 AbortController removal (queryClient.cancelQueries sole cancellation, isCancel axios canonical)
   - Wave 135 SW1 sessions factory exports (updateSessionInCache + invalidateSessions)
   - Wave 135 SW3 build-orchestrated.mjs orchestration pattern (BUILD_SKIP_PWA flag + kill-after-artifacts + standalone workbox-build)
8. **`memory/MEMORY.md`** — auto-loaded; W135 row at top; SW4 compaction (W132 collapsed to one-liner; W133/W134/W135 stay verbose)
9. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?" probe (60-90 min polish budget)
10. **`memory/feedback_planning_estimates.md`** — range estimates over single numbers; "production-grade polish" anchor 3-5h base + variance

---

## Skills to invoke immediately (per `superpowers:using-superpowers`)

- **`superpowers:writing-plans`** — invoke for plan file creation in plan mode
- **`superpowers:brainstorming`** — invoke for scope decision via 3-question AskUserQuestion pattern (W133/W134/W135 success: scope tier → sub-scope → mechanism). DO NOT skip — even "simple" waves need design before code.
- **`superpowers:systematic-debugging`** — invoke if hitting bugs (W132 polish round 3 + W133 polish framing-accuracy + W134 SW2 multi-iteration + W135 SW3 hang investigation arc proven valuable)
- **`superpowers:verification-before-completion`** — invoke before claiming completion (Iron Law: fresh evidence before claims; "безупречно?" probe surfaces verification gaps)
- **`superpowers:executing-plans`** — invoke after plan approval

---

## Use Context7 MCP

For TanStack Start v1 / TanStack Router v1 / vite-plugin-pwa internals /
workbox-build API / Caddy / Nitro / k8s / Sentry / Helm / Argo CD docs as
relevant per Option chosen. Don't trust agent inferences — W128 polish + W135
SW3 both surfaced incomplete diagnoses (W128 said programmatic vite.build was
the fix; W135 found prerender doesn't fire that way; W126 polish said vite-plugin-pwa
was the sole hang; W135 found a second hang in tanstackStart-core).

---

## Anticipated AskUserQuestion 3-question pattern

W133 + W134 + W135 successful pattern:

1. **Q1 — Primary scope tier**: Tier 1 (gateway JWT + chrome-devtools wall + failed_login_attempts schema) vs Tier 2 (build-orchestrated structural + Workbox config + Linux CI) vs Tier 3 (housekeeping batch) vs Tier 4 (cross-cutting K-P) vs Tier 5 (Q/R Messenger/Admin optional).
2. **Q2 — Within chosen tier, sub-scope**: e.g. Tier 1 → JWT fix (a) embed in JWT vs (b) DB lookup with cache; chrome-devtools wall investigation depth; failed_login_attempts schema migration.
3. **Q3 — Architecture/design (if applicable)**: e.g. Tier 1 + 2 → which structural fix path for build-orchestrated.mjs hang; Tier 4 → test infra strategy.

---

## 44 critical pitfalls (W125-W135)

### W125-W128 (1-15) — TanStack Start v1 SSR foundation

(see W134 prompt for full list — preserved verbatim)

### W129-W131 (16-30) — Phase 5 continuation + Phase 4 deploy

(see W134 prompt for full list — preserved verbatim)

### W132-W133 (31-38) — Canary infra + cookie forwarding

(see W134 prompt for full list — preserved verbatim)

### W134 (39-41)

(see W134 prompt — preserved)

### W135 NEW (42-44)

42. **Bridge mechanism cancellation now via `queryClient.cancelQueries`** (W135 SW1) — pre-W134 had `AbortController` per-request; W134 SW1 added `queryClient.cancelQueries` alongside the controller; W135 SW1 retires the controller entirely. `isCancel(error)` (axios canonical) replaces `controller.signal.aborted` check in the catch block. `clearProfile`'s `controller?.abort()` → `queryClient.cancelQueries`. The previous `activeRequestRef` ref is gone. Future cancellation in this hook should use `queryClient.cancelQueries({ queryKey: currentUserQueryKey })` only.

43. **`updateSessionInCache` + `invalidateSessions` factory helpers** (W135 SW1) — exported from `frontend/src/api/hooks/sessions.ts`. Mirror W129 events.ts / W130 schedule.ts factory placement convention. `useSessionManagement` mutation paths route through these helpers; cache key never touched directly. Future mutation cache writes for the sessions slot should use these helpers, NOT inline `setQueryData(sessionsKey, ...)`. Defensive: `if (!Array.isArray(previous)) return previous` no-op when cache slot empty or hydrated to non-array.

44. **`build-orchestrated.mjs` 6-step pattern + `BUILD_SKIP_PWA=true` env flag** (W135 SW3) — replaces wave127-build-x3.sh on Windows. `vite.config.mts` reads `process.env.BUILD_SKIP_PWA` to gate `VitePWA({disable: true})`. Subprocess `vite build` poll-and-kill-after-artifacts breaks out of post-prerender hang (which has TWO causes: vite-plugin-pwa AND a second tanstackStart-core hang point). esbuild compiles sw.ts → dist/client/sw.js with tsconfig path resolution. workbox-build.injectManifest standalone replaces `self.__WB_MANIFEST` with actual manifest. Build × 3 reproducible 26s/run. Future Windows build issues should look at this orchestrator first; CI Linux uses default `vite build` via the same npm script (BUILD_SKIP_PWA falsy → VitePWA enabled normally; subprocess exits cleanly without kill).

---

## Lessons from W135 polish pass (meta-pattern for W136+)

(SAME as W134 lessons — re-verify gates POST-final-commit, cross-session vitest 5-run, eslint-react-compiler at error level is implicit React Compiler audit, honest framing recordings ≠ deferrals, memory file changes need separate verification, archive directory presence verifiable in seconds.)

ADDITIONAL W135-specific lessons:

1. **Empirical findings can disprove plan assumptions** — W128 polish round 2 said programmatic `vite.build()` exits cleanly + would fix the Windows hang once we figured out prerender. W135 SW3 found programmatic build doesn't fire prerender at all (so it can't substitute), AND that subprocess CLI build still hangs after prerender even with vite-plugin-pwa disabled. **Two false starts within SW3 (~30min lost)** before pivoting to kill-after-artifacts pattern. Plan time-boxes for "structural fix" approaches should include 30-90min budget for empirical diagnostics that may invalidate the plan's premise.

2. **Honest re-scoping mid-implementation is acceptable** — Q3 was "Path B full commitment ~3-5h". Empirical findings showed full structural fix isn't possible without deeper investigation (filed as W136 candidate). Pivoted to kill-after-artifacts (improvement, not structural fix) + documented sub-deferral in §Honesty. User-approved Q3 was honored at "best-effort full commitment" semantics, not "structural fix at all costs". Future Q3 phrasing should anticipate this — "Path B time-boxed (~2h cap)" gives explicit permission to escape, while "Path B full commitment ~3-5h" implicitly does too via "no hard time-box" language.

3. **Discovered out-of-scope issues should be filed as W+1 candidates IMMEDIATELY** — W135 SW2 surfaced 2 backend bugs (gateway JWT mismatch + failed_login_attempts schema). Adding to AUDIT_WAVE135 §Honesty + W136 opening prompt happened during SW4 (not at discovery time). Better pattern: when surfacing an unrelated issue, write the W+1 candidate entry at discovery time (~30s) rather than at audit time (forgotten ~5%).

---

## Build × 3 reproducibility discipline (refined post-W135)

Pattern: run `npm run build` × 3 (now via build-orchestrated.mjs, no more
wave127-build-x3.sh) AFTER each wave's final commit (including docs-only
commits). Three identical hash + size prints prove the wave produced a
deterministic bundle.

Expected for code-changing SWs: hash will differ from baseline (size delta
should match closure size of new exports + import bookkeeping).

Expected for docs-only SWs (like W135 SW4): hash MUST match the previous
code-changing SW's bundle exactly. Different hash = something silently
touched the bundle.

Windows note: build-orchestrated.mjs handles the post-prerender hang
transparently via kill-after-artifacts. CI Linux uses the same script;
subprocess exits cleanly without kill.

---

## "безупречно?" probe response template

(SAME as W134 — preserved verbatim. Anticipate "безупречно?" probe per
`memory/feedback_perfectionism.md` after SW4 — budget 30-60 min polish to close
any post-final-commit gaps.)

W135 polish budget candidates:
- Cross-session vitest 5-run (~2.5min) — closes W135 §Honesty #12.
- MEMORY.md `../../../../` path normalization (~5-10 min) — closes W134 §Honesty #6.
- Build × 3 post-SW4 reproducibility check (~1.5min) — invariant proof.
- 24/N memory-link resolution check (~30s) — invariant proof.
- AUDIT_WAVE135.md commit-stat cross-check (~1 min) — invariant proof.
- Archive directory presence verification (~30s).

W135 polish total budget: ~5-15 min if no surprises; up to 30-60 min if SW2 chrome-devtools wall workaround comes online (e.g., Playwright path).

---

**Begin**: brainstorming → AskUserQuestion (3 questions) → plan file →
ExitPlanMode → execute.
