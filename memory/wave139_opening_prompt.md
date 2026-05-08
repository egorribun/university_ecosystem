# Wave 139 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 138 CLOSED + POLISHED + PUSHED** (2026-05-08) — Tier 1+2+3 broad
combo per user-approved 3-question AskUserQuestion (Q1=Tier 1+2+3,
Q2=Full root-cause SW investigation, Q3=Allow +2h mid-wave expansion;
expansion budget UNUSED).

W138 closed **3 of 7 W137 §Honesty caveats** (W137 #4 fully via SW1
Docker × 3 BYTE-IDENTICAL verification; NEW W138 SW eval fix via SW2
esbuild iife format change; W136 #6 Playwright /login VITE_E2E_MODE
ALREADY DONE per Phase 1 finding) + introduces **1 NEW caveat from W138
SW3+SW4 polish** + carries **4 from W134/W137** = **5 caveats total**.

W138 surfaced + fixed a **MEDIUM-impact Service Worker eval failure**
silently failing browser-side since W135 SW3 (esbuild `format: "esm"`
produced trailing `export{...}` from sw.ts test-compat re-exports →
classic-script registered SW + ES export = SyntaxError). Fix: change
esbuild `format: "esm"` → `format: "iife"` in `build-orchestrated.mjs:330`.
Verified via wave137-authed-smoke.mjs re-run: 8 SSR routes × 0 console
errors (was 1/route pre-fix). PWA functionality (runtime caching, push
notifications, offline support) restored across the entire SSR stack.

**Branch state**: `egorribun` PUSHED to origin/egorribun post-W138 polish
(8 W138 commits + previous waves; user-driven push 2026-05-08).

### 8 git commits in W138 (full progression)

The W138 prompt-update commit `a50e0bf9d` was the entry point;
implementation commits begin at `9a699a4fd`:

1. `9a699a4fd` SW0 `docs(wave138-sw0-design)` — design doc (1 file +222)
2. `90d636d88` SW1 `chore(wave138-sw1-docker-build-x3)` — Docker × 3
   BYTE-IDENTICAL verification (1 file +89)
3. `1795b0d9b` SW2 `fix(wave138-sw2-sw-iife-format)` — Service Worker
   eval failure root-cause fix (1 file +15/-4)
4. `d291d5672` SW3 `feat(wave138-sw3-visual-audit-infrastructure)` —
   wave138-visual-audit.mjs (1 file +527)
5. `35a0052f3` SW8 `docs(wave138-sw8-audit-handoff)` — AUDIT_WAVE138 +
   W139 prompt + N+3 rotation (W135 → archive) + 5 NEW memory files
   (10 files +1583/-30)
6. `772f9dc7f` SW7-followup `docs(wave138-sw7-rolldown-filed)` — record
   rolldown/rolldown#9327 URL (2 files +36/-22)
7. `498067ecc` polish `chore(wave138-polish)` — 3 SW8-deferred gaps
   closed + 5 missing memory files mirrored from `.claude` profile to
   repo + AUDIT_WAVE138 polish-pass invariant table verified + Workbox
   upstream alignment (Context7) + Cross-session vitest 5/5 × 1052p
   (6 files +487/-20)

Verify session-start: `git log --oneline a50e0bf9d..HEAD | wc -l` →
**7** (8 if you include the prompt-update; recommendation: count from
SW0 9a699a4fd to polish 498067ecc inclusive = 7 implementation commits).
If different, investigate before brainstorming.

```bash
git status --short  # Should be clean working tree
git rev-parse --abbrev-ref @{u}  # Should be origin/egorribun (push state preserved)
ls docs/audits/AUDIT_WAVE*.md  # Should be 3 files: W136/W137/W138
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # Should be 24 (W112-W135)
wc -c memory/MEMORY.md  # Should be < 24,400 (auto-load threshold)
```

---

## Bundle baseline post-W138 polish (LOCAL × 1 verified post-SW2 fix)

**LOCAL `npm run build` (build-orchestrated.mjs)** — verified post W138
polish-pass (Phase 2):

```
dist/client/assets/index-DqqHVXgy.js  139,808 bytes (LOCAL — preserved W137 baseline)
dist/client/_shell.html                65,864 bytes (preserved W137 baseline)
dist/client/sw.js                      53,115 bytes (POST-W138-SW2-FIX; W137 was 53,181 = -66 b dropped export keyword)
dist/server/server.js                  39,373 bytes (preserved W137 baseline)
```

sw.js head: `"use strict";(()=>{` (IIFE wrapper). Tail: `;})();`.
0 export statements verified via grep. Workbox 7.4.0 + `__WB_MANIFEST`
replaced + 209 files / 4.80 MB precached.

**DOCKER build via `start-docker.ps1 -Build`** — verified ×3 BYTE-
IDENTICAL in W138 SW1:

```
dist/client/assets/index-tGuQB5EY.js  139,808 bytes (DOCKER — VITE_BACKEND_ORIGIN=http://backend:8000 baked)
dist/client/_shell.html                66,098 bytes (post-build-shell.mjs nonce + LHCI placeholder pipeline)
dist/client/sw.js                      53,115 bytes (post-W138-SW2-fix; classic-IIFE)
dist/server/server.js                  39,371 bytes (-2 vs LOCAL: URL string delta from `localhost:8000` → `backend:8000`)
```

Both LOCAL + DOCKER paths verified post-W138-SW2 fix. The "BYTE-IDENTICAL
× N" reproducibility claim is structurally correct for both build paths
post-W137 SW4-prep Dockerfile dist-clear fix.

---

## NO-DEPLOY scope continued (W134/W135/W136/W137/W138 carried forward)

Cluster deployment NOT pursued. Goal: "fully working + visually +
internally flawless локально + структурно". Cluster-dependent items
remain removed (Phase 6 actual rollout, RUM wiring, Caddy weight flip
live test, kubectl apply, etc.).

W125-W138 SSR migration arc remains shipped + locally verified +
structurally correct + console-error-free post-W138 SW2 fix.

---

## Gates baseline (preserved through W138 + polish)

| Gate | Value | W138+polish status |
|------|-------|---------------------|
| `npx tsc --noEmit` | 0 errors | ✓ preserved |
| `npm run lint` (max-warnings=0) | 0 errors / 0 warnings | ✓ preserved |
| `npx vitest run` single | **1052p / 12s / 0f** | ✓ preserved (W137 polish-v2 baseline) |
| **Cross-session vitest 5-run** | **5/5 × 1052p / 12s / 0f** (flake band = 0; durations 39.52-41.13s) | ✓ W138 polish |
| pytest backend slice (representative) | **31p / 0f** + W137 baseline 255p preserved | ✓ no backend changes in W138 |
| `npm audit` | **0 vulnerabilities** | ✓ preserved (re-verified post-polish) |
| Cargo.lock no drift | working tree clean (≥ 28 waves idempotent) | ✓ preserved |
| i18n parity | 18/18 (CLDR-aware EN/RU) | ✓ SW5 |
| Tree-shake invariant | 0 matches `lhci-mock-user` in PROD `dist/client/assets/*.js` | ✓ preserved |
| Build × 3 LOCAL BYTE-IDENTICAL | hash + sizes match (W137 baseline) | ✓ polish Phase 2 |
| Build × 3 DOCKER BYTE-IDENTICAL | hash + sizes match × 3 fresh runs | ✓ SW1 |
| Real Docker chain authed flow (8 SSR routes) | **8/8 200 + AUTHED + 0 hydration errors + 0 CONSOLE ERRORS** | ✓ SW2 (was 1/route pre-fix) |
| W137 SW1 RS256 contract tests | 5p / 0f | ✓ preserved |
| Storybook build | 19.21s 0 errors | ✓ SW6 |
| **AUDIT_WAVE138 commit-stat** | 4/4 W138 SW commits match `git show --shortstat` | ✓ polish Phase 4 |
| **MEMORY.md size** | 22,456 bytes (< 24,400 auto-load threshold) | ✓ SW8 + polish |
| **Memory link resolution** | **9/9 references** resolve from REPO + `.claude` profile (5 files mirrored in polish to close pre-W138 dual-location drift) | ✓ polish Phase 4 |
| **INDEX.md link resolution** | 30+ archive references resolve OK | ✓ polish Phase 4 |
| **Workbox upstream alignment** | Context7 `/googlechrome/workbox` v7 confirms classic-script SW registration is canonical | ✓ polish Phase 1 |
| Active waves (N+3) | W136/W137/W138 | ✓ SW8 |
| Archive directory | 24 entries W112-W135 | ✓ SW8 |
| Branch state | egorribun PUSHED to origin/egorribun | ✓ post-polish |

---

## SSR routes (8 total — preserved + console-error-free post-W138 SW2)

W138 SW2 fix eliminated the last residual console error per route. ALL
8 SSR routes report:

| Route | Status | HTTP | Auth | Hydr err | Console err | Net req |
|-------|--------|------|------|----------|-------------|---------|
| `/dashboard` | SSR | 200 | AUTHED | 0 | **0** | 107 |
| `/events` | SSR | 200 | AUTHED | 0 | **0** | 110 |
| `/news` | SSR | 200 | AUTHED | 0 | **0** | 110 |
| `/schedule` | SSR | 200 | AUTHED | 0 | **0** | 113 |
| `/profile` | SSR | 200 | AUTHED | 0 | **0** | 110 |
| `/settings` | SSR + tab=N | 200 | AUTHED | 0 | **0** | 114 |
| `/map` | SSR | 200 | AUTHED | 0 | **0** | 110 |
| `/activity` | SSR | 200 | AUTHED | 0 | **0** | 113 |

Remaining `ssr: false`: 2 (messenger × 2 — heavy WebSocket + IndexedDB
at render time, deferred indefinitely under no-deploy "production-as-is").

`/map` + `/activity` preserved at `ssr: 'data-only'` (W127 SW6
annotations under permissive parent `_auth.tsx ssr: true` W128 SW2).

---

## Wave 139 candidates (post-W138)

### Tier 1 — HIGH priority (W138 §Honesty closures + W137 carry-forward)

- **wave138-visual-audit.mjs CI Linux execution wiring** (~30-60 min,
  closes W138 §Honesty #5 fully). NEW
  `.github/workflows/visual-audit.yml` (workflow_dispatch trigger).
  Reuses npm-run-all + npx playwright + Docker stack bring-up patterns
  from existing CI. Linux runner doesn't have the Windows heavy-DOM
  wall that blocks AxeBuilder.analyze() on /dashboard locally. Once
  wired, can run authed visual audit on all 8 SSR routes.

- **file-processor temporal-localhost fix** (~2-3h structural OR
  ~30 min doc-accept, W137 §Honesty #5 carry-forward). Three paths:
  - **(a) Rebind temporal to 0.0.0.0 with token auth** (~2-3h):
    update temporal entrypoint to drop `--ip 127.0.0.1`; add token-
    based authentication; update file-processor + workers to
    authenticate. Restores P0-03 trade-off original intent.
  - **(b) file-processor host network** (~30-60 min): set
    `network_mode: host` on file-processor service. Breaks docker-
    compose service-name DNS for file-processor.
  - **(c) Document accept-as-dev-limitation** (~30 min): add to
    docker-compose.full.yml + CLAUDE.md as known limitation; backend
    workers depending on file-processor get marked best-effort in dev.
    Production K8s (separate Temporal cluster with auth) unaffected.

### Tier 2 — Per-page visual audit (NOW FEASIBLE post-W138 SW3 + Tier 1 CI Linux wiring)

- **/dashboard visual audit (CI Linux)** (~0.5-1 wave). Wire
  wave138-visual-audit.mjs into CI; run on /dashboard first; capture
  axe violations + (optionally) LHCI 3-run medians. Compare against
  gates. Triage critical/serious violations: fix inline if quick
  (<30 min each); defer cosmetic to /dashboard own-wave.

- **Other 7 SSR routes' visual audits** — opportunistic. Pattern:
  one route per ~0.5-1 wave depending on findings.

### Tier 3 — Inherited tech-debt (carry-forward from W134/W135/W136/W137)

- **Test infrastructure expansion** (W115 SW1 a11y-public WebKit OOM;
  W116 SW1 mobile-webkit /404).
- **LHCI gate ratchet on REAL W137-W138 baseline** (now feasible post
  SW1 + polish — Docker × 3 verified stable; LOCAL + DOCKER bundle
  hashes confirmed). W120 SW2 last applied; W124 SW4 documented
  variance band ±0.01-0.02.
- **a11y deep-audit cross-browser** via wave138-visual-audit.mjs on
  CI Linux.
- **i18n parity consolidation**.
- **Storybook/Chromatic activation** (requires user-side
  `CHROMATIC_PROJECT_TOKEN` secret + `vars.CHROMATIC_ENABLED=true`).

### Tier 4 — Pre-existing carry-forward (NOT closeable without
                                          structural change)

- **W134 §Honesty #2 (bundle delta)** — superseded by W137 §Honesty #4
  + W138 SW1 closure. Real bundle hash verified ×3 BYTE-IDENTICAL for
  both LOCAL (`index-DqqHVXgy.js`) + DOCKER (`index-tGuQB5EY.js`).
  Recording-only.
- **W134 §Honesty #10 (/messenger Phase 5 punted)** — no-deploy
  decision unchanged. Tier 5 explicit user decision.
- **W137 #6 + #7 (MAX_SESSIONS dev override + sidecar healthiness ≠
  container healthiness)** — by-design dev-only trade-offs.

### Tier 5 — Optional big scope (explicit user decision)

- **Messenger × 2 polish arc** (~5-7 waves). Per historical anchoring
  (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard ~10):
  messenger has heavy WebSocket + IndexedDB but smaller surface area
  than Map. Pursue OR punt.
- **/admin polish arc** (~3-5 waves). Admin tooling depth audit + UX
  polish. Lower-traffic page. Pursue OR punt.

### Filed upstream issues (W138 SW7 status)

- ✅ **rolldown/rolldown — [#9327](https://github.com/rolldown/rolldown/issues/9327)**
  (FILED 2026-05-08 by user post-W138 close; build hangs post-prerender,
  MessagePort + Worker)
- chromedevtools/chrome-devtools-mcp — Windows headless heavy-DOM
  Accessibility.getFullAXTree + Runtime.evaluate timeout (NOW also
  affecting AxeBuilder per W138 SW3+SW4 finding) — TEMPLATE READY in
  `memory/wave138_upstream_issue_chromedevtools.md`
- grafana/tempo + grafana/loki — distroless `--check-ready` CLI
  subcommand request — TEMPLATE READY in `memory/wave138_upstream_issue_tempo_loki.md`

Resolution timeline outside our control. Monitor rolldown#9327
quarterly for upstream activity; if maintainers fix the worker-pool
cleanup, `frontend/scripts/build-orchestrated.mjs` watch+kill workaround
can be retired (vite build subprocess would exit cleanly without
SIGKILL). User can file the remaining 2 templates if needed.

---

## Pragmatic recommendation (per `feedback_planning_estimates.md` style)

- **Best ROI immediate (Tier 1 W138 §Honesty closures)**:
  wave138-visual-audit.mjs CI Linux wiring (~30-60 min) + file-processor
  temporal-localhost path (a/b/c) (~30 min accept OR ~2-3h structural).
  Total: ~1-4h depending on file-processor path. Closes 1-2 §Honesty
  caveats; brings W139 net caveat count to ~3-4.

- **Best W139 starter combo (Tier 1 + Tier 2 partial)**: above +
  /dashboard visual audit on CI Linux (~30-60 min once SW3 infra
  wired) + LHCI gate ratchet on real W137-W138 baseline (~1-2h). Total:
  ~5-7h. **High user-facing impact** — first feasible per-page visual
  audit results since SSR migration started in W125.

- **Most W138 §Honesty closures**: Tier 1 + Tier 2 + Tier 3 inherited
  batch (~7-9h). Drops to ≤2-3 § Honesty caveats post W139.

- **Tier 5 explicit decision**: confirm Messenger/Admin scope OR punt
  before W140+.

### Anti-patterns to avoid (from W138 + polish lessons)

1. **Service Worker registration silently fails on classic-script + ES
   exports** — esbuild `format: "esm"` produces trailing `export{...}`
   statements. SW registered without `{ type: "module" }` = classic
   script. Classic + export = SyntaxError → "ServiceWorker script
   evaluation failed" at registration. **Always use `format: "iife"`
   for SW compilation OR register with `{ type: "module" }`**. Workbox
   upstream canonical is classic-script registration (verified via
   Context7 `/googlechrome/workbox` v7 docs in W138 polish).

2. **Plan-time hypothesis paths can miss the actual root cause** —
   W138 SW2 plan listed 4 hypothesis paths (CSP / Workbox runtime /
   headless quirk / Service-Worker-Allowed header). Empirical
   investigation found a 5th cause not in any path (esbuild format
   mismatch). Per W137 Lesson #1 + W138 confirmation: include
   "(z) something we haven't thought of" as explicit hypothesis path
   in future investigation plans.

3. **Windows heavy-DOM wall extends to AxeBuilder too** — first
   discovered in W137 SW4 for `page.evaluate(...)` body-snippet
   capture; W138 SW3+SW4 confirms AxeBuilder.analyze() (which
   internally uses page.evaluate to inject axe-core) hits the same
   wall on /dashboard. Future visual-audit infrastructure on Windows
   should default to either CI Linux execution OR scope-reduced axe
   rules + filtered nodes.

4. **MSYS path conversion strikes recurring class** — Wave 116 SW3 +
   W120 SW1 + W138 SW3 all hit Git Bash MSYS path-mangling issues
   with leading-slash env vars. Pattern: always include
   `normalizeRoute()` / `normalizePath()` helper that re-adds leading
   slash if missing. wave138-visual-audit.mjs follows
   lhci-windows-fallback.mjs precedent.

5. **AskUserQuestion 4-option gate works for high-blast-radius
   actions** — SW7 used a single 4-option question to gate the
   `gh issue create` action. Pattern: when a wave SW has known
   high-blast-radius outputs (cross-account writes, data-mutating
   ops), gate via AskUserQuestion at the SW boundary. Plan handles
   scope; AskUserQuestion at SW handles execution authorization.

6. **Memory file dual-location drift discoverable via comprehensive
   polish** — W138 polish surfaced 5 memory files that existed in
   `.claude` profile (auto-load source) but NOT in repo `memory/`. W137
   polish-v2 audit verified "27/27 references resolve" — claim was
   correct for `.claude` profile only; repo side had 5 dead links.
   Pattern recipe for future polish-passes: always audit BOTH locations
   (`.claude` profile auto-load source + repo `memory/` dual-location
   convention).

7. **Tier 3 batch can include "already done" surprise wins** — Phase
   1 Explore-agent finding in W138 was that Playwright /login
   VITE_E2E_MODE refactor was ALREADY in production (W115 SW1 + W116
   SW1). Mark-resolved closures from prior waves can pop up
   unexpectedly when a multi-wave inherited backlog gets re-investigated.

8. **§Honesty caveat counting is dynamic, not zero-sum** — plan target
   was ≤4 caveats post W138; actual = 5. The "extra" caveat is NEW
   from W138 polish-pass discovery (Windows wall on AxeBuilder). This
   isn't a regression — it's a new finding that surfaced honestly via
   the polish process. Per W136 Lesson #7 + W137 Lesson #1: empirical
   findings are sometimes additive to caveat count; honest framing is
   the right response.

9. **Polish-pass discovers gaps in PRIOR-wave audit claims, not just
   current wave** — W138 polish discovered the W137 polish-v2 "27/27
   resolve" claim was correct only for `.claude` profile (auto-load
   source); repo side had drift. Polish-pass scope can extend backwards
   in audit history. Pattern: re-verify claims from prior polish-passes
   with broader assumptions.

---

## Anticipated AskUserQuestion 3-question pattern

(W133/W134/W135/W136/W137/W138 success — 6 waves with same pattern;
W139 should continue)

1. **Q1 — Primary scope tier**:
   - Tier 1 quick-wins (visual audit CI Linux wiring + file-processor
     accept-as-dev ~1-2h)
   - Tier 1+2 (+ /dashboard visual audit on CI Linux ~3-4h) — recommended
   - Tier 1+2+3 (+ inherited tech-debt batch including LHCI gate ratchet
     ~5-7h)
   - Tier 1 + file-processor temporal-localhost structural fix (path a
     ~3-5h)
   - Tier 5 explicit decision (Messenger × 2 OR /admin OR punt)

2. **Q2 — Within chosen tier, sub-scope**: e.g.
   - Tier 1 visual audit → CI workflow shape (workflow_dispatch only,
     PR-triggered with path filter, OR nightly cron)
   - Tier 1 file-processor → Path (a) temporal rebind+auth vs (b) host
     network vs (c) accept-as-dev-limit
   - Tier 2 → which SSR route first (/dashboard recommended; or pick
     by priority — Map / Activity due to /map+/activity ssr: 'data-only'
     specifically?)
   - Tier 3 → which inherited item (LHCI ratchet vs WebKit OOM vs
     Storybook activation)

3. **Q3 — Architecture/design (if applicable)**:
   - Tier 1 visual audit → if CI Linux execution reveals violations on
     /dashboard, fix inline in W139 vs defer to /dashboard own-wave?
   - Tier 1 file-processor → if Path (a) reveals temporal token-auth
     setup complexity (~30-60 min beyond plan), how to handle in W139
     vs W140?
   - Tier 4 diagnostic budget if W139 surfaces more polish-pass
     surprises (per W136 Lesson #7 + W137 Lesson #1 + W138 Lesson #2 +
     W138 polish Lesson #9 pattern — empirical findings disprove plan
     assumptions PERSISTENTLY across multiple waves; polish discovers
     gaps in PRIOR-wave audit claims too)

---

## Read mandatory files in order (per `superpowers:using-superpowers`)

1. **`docs/audits/AUDIT_WAVE138.md`** — full SW0-SW8 narrative +
   verification matrix + § Honesty probe (5 caveats: 3 closed via
   implementation + 1 NEW + 4 carry from W134/W137) + lessons-learned +
   W139 candidates list at bottom + **Polish-pass invariant table
   (verified post-polish)**
2. **`memory/wave138_backlog.md`** — close-status entry-point with
   commit references + § Honesty list + filed upstream URLs
3. **`memory/wave138_docker_x3_verification.md`** — Docker × 3 BYTE-
   IDENTICAL evidence
4. **`memory/wave138_upstream_issue_*.md`** — 3 GitHub issue templates
   (rolldown FILED post-close as #9327; chromedevtools + tempo+loki
   stay user-side decisions)
5. **`memory/wave139_opening_prompt.md`** — this file
6. **`docs/plans/2026-05-08-wave138-tier123-design.md`** — W138
   design doc with Phase 1 Explore findings + 8-SW progression
7. **`docs/plans/2026-05-08-wave137-tier1234-design.md`** — W137
   design doc context
8. **`CLAUDE.md`** ## Audit Trail W138 row + 4 new gotchas:
   - SW eval iife format invariant (NEVER `format: "esm"` without
     register `{ type: "module" }`)
   - Visual audit infrastructure pattern (extends wave137-authed-smoke)
   - AxeBuilder Windows heavy-DOM wall (extends W137 SW7)
   - Plan-vs-reality §Honesty notes
9. **`memory/MEMORY.md`** — auto-loaded; W138 row at top; W135
   collapsed to one-liner (rotated W138 SW8); W136/W137/W138 verbose
   in Active backlog; W134/W135 audit history compact; size 22,456 b
10. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?"
    probe (60-90 min polish budget — W138 used ~33 min polish;
    expect similar for W139 if scope is broad like Tier 1+2)
11. **`memory/feedback_planning_estimates.md`** — range estimates over
    single numbers; "production-grade polish" anchor 3-5h base +
    variance

---

## Skills to invoke immediately (per `superpowers:using-superpowers`)

- **`superpowers:brainstorming`** — invoke FIRST per W134/W135/W136/W137/
  W138 success pattern (3-question AskUserQuestion). MANDATORY before
  any creative work. DO NOT skip.
- **`superpowers:writing-plans`** — for plan file creation in plan
  mode after brainstorming
- **`superpowers:systematic-debugging`** — invoke if hitting bugs
  (W138 SW2 surfaced REAL bug via reproduce-first pattern; W138 polish
  Phase 4 surfaced dual-location drift via comprehensive memory link
  audit; expect more in W139)
- **`superpowers:verification-before-completion`** — invoke BEFORE
  claiming SW completion (Iron Law: fresh evidence before claims;
  W138 SW2 fix verified via wave137-authed-smoke.mjs re-run BEFORE
  commit; W138 polish verified via cross-session vitest 5-run before
  commit)
- **`superpowers:executing-plans`** — invoke AFTER plan approval

---

## Use Context7 MCP (mandatory for library docs)

W139 likely Context7 lookups:
- **GitHub Actions** for workflow_dispatch + matrix + Docker stack
  bring-up patterns (Tier 1 visual audit CI wiring)
- **`@temporalio/sdk` + Temporal documentation** — for Tier 1
  file-processor fix path (a) rebind with auth (token-based + mTLS
  options)
- **`@axe-core/playwright` API** — for Tier 2 visual audit run
  configuration (reduce axe scope on heavy authed routes if needed)
- **Lighthouse CLI** — for Tier 3 LHCI gate ratchet methodology
  refinement
- **`vite-plugin-pwa` + `workbox-build`** — if SW2 fix surfaces any
  related concerns (W138 polish Phase 1 confirmed Workbox upstream
  recommends classic-script SW registration; align W139 changes
  similarly)

Don't trust agent inferences without Context7 verification. W138 SW2
empirical findings disproved 3-of-4 plan hypothesis paths; the 4th
hypothesis path (chrome-devtools quirk) was also wrong; actual root
cause was a 5th, unanticipated path (esbuild format mismatch).

---

## Lessons from W138 + polish (carry-forward for W139+)

1. **Service Worker eval failures are silent at registration phase** —
   the `Service worker registration failed: ServiceWorker script
   evaluation failed` error is browser-reported AT REGISTRATION (not
   at fetch). Evaluation phase has different rules than parsing —
   `export` keyword in classic-script context = SyntaxError silently
   caught at registration. Invariant for W139+: any sw.ts compilation
   must produce classic-script-compatible output (IIFE preferred, OR
   register with `{ type: "module" }`).

2. **Plan-time hypothesis paths can miss the actual root cause** —
   W138 SW2 plan listed 4 hypothesis paths; empirical investigation
   found a 5th cause not in any path. Per W137 Lesson #1 + W138
   confirmation: include "(z) something we haven't thought of" as
   explicit hypothesis path in future investigation plans.

3. **Windows heavy-DOM wall extends to AxeBuilder too** — W138 SW3+SW4
   confirms the wall fires for AxeBuilder.analyze() (which internally
   uses page.evaluate to inject axe-core). Future visual-audit
   infrastructure on Windows should default to either CI Linux
   execution OR scope-reduced axe rules.

4. **MSYS path conversion** — W138 SW3 ROUTES env var normalization
   via `normalizeRoute()`. Pattern recipe: any future env-var-driven
   script that accepts paths must include leading-slash normalization.

5. **AskUserQuestion 4-option gate for high-blast-radius actions** —
   SW7 pattern: when a wave SW has known high-blast-radius outputs
   (cross-account writes, data-mutating ops), gate via AskUserQuestion
   at the SW boundary. Plan handles scope; AskUserQuestion at SW
   handles execution authorization.

6. **Visual audit infrastructure can ship without full verification on
   the target platform** — W138 SW3 shipped a structurally-sound
   script. Empirical verification on /dashboard hit Windows wall
   (SW4 partial). Acceptable per W137 Lesson — ship the artifact,
   document the verification gap, defer empirical proof to environment
   where it can succeed (CI Linux).

7. **Tier 3 batch can include "already done" surprise wins** — Phase
   1 Explore-agent finding in W138 was that Playwright /login
   VITE_E2E_MODE refactor was ALREADY in production. Saves time
   without code work.

8. **§Honesty caveat counting is dynamic** — plan target was ≤4 caveats
   post W138; actual = 5. The "extra" caveat is NEW from W138 polish-
   pass discovery (Windows wall on AxeBuilder). This isn't a
   regression — it's a new finding that surfaced honestly via the
   polish process. Empirical findings are sometimes additive to caveat
   count; honest framing is the right response.

9. **Polish-pass discovers gaps in PRIOR-wave audit claims** (NEW from
   W138 polish) — W138 polish discovered W137 polish-v2 "27/27 resolve"
   claim was correct only for `.claude` profile (auto-load source);
   repo side had drift (5 dead links). Polish-pass scope extends
   backwards in audit history. Re-verify claims from prior polish-passes
   with broader assumptions.

10. **Workbox upstream alignment validation via Context7** (NEW from
    W138 polish Phase 1) — when implementing SW-related changes,
    Context7 lookup `/googlechrome/workbox` v7 docs validates whether
    the change matches upstream canonical pattern. ALL Workbox
    examples use `navigator.serviceWorker.register('./sw.js')` classic-
    script form. If our implementation deviates from canonical without
    explicit reason, that's a polish-pass red flag.

11. **Cross-session vitest 5-run is the canonical flake-band measurement**
    (W137 polish-v2 + W138 polish convention) — single-run pass count
    is necessary but insufficient. 5-run sequence reveals timing
    variance + intermittent failures. flake band = 0 means 5/5
    identical pass count. W138 polish: 5/5 × 1052p / 12s / 0f,
    durations 39.52-41.13s (variance 1.61s noise within ±2s).

---

## Build × 3 reproducibility discipline (post-W138 corrected baseline)

Pattern: run `npm run build` × 3 (now via build-orchestrated.mjs with
mtime fix from W136 SW5 + single-source PWA_INJECT_CONFIG from W136
SW6 + W137 SW4-prep `rm -rf dist` Dockerfile fix + W138 SW2 `format:
"iife"` SW eval fix) AFTER each wave's final commit (including docs-
only commits + polish commits).

- **Code-changing SWs**: hash will differ from baseline (size delta
  should match closure size of new exports + import bookkeeping).
- **Docs-only SWs**: hash MUST match the previous code-changing SW's
  bundle exactly. Different hash = something silently touched the
  bundle.
- **W139 first task pattern**: re-establish/preserve byte-identical
  baseline post-any code change. SW1-style verification (~15-20 min)
  is now a reusable pattern.

Windows: build-orchestrated.mjs handles post-prerender hang via
mtime-gated kill-after-artifacts (W136 SW5). frontend.Dockerfile (W137
SW4-prep) clears dist/ before npm run build to force fresh state.
W138 SW2 changed esbuild format to iife (SW eval fix). CI Linux: same
script via `build-orchestrated-linux.yml` workflow_dispatch (W136 SW6).

---

## "безупречно?" probe response template (per `feedback_perfectionism.md`)

Anticipate "безупречно?" probe at any point user-facing claim is made.
Response template:

1. **DO NOT reassure** — это probe для honest self-audit + polish pass
2. **List claims explicitly** with evidence (concrete numbers, command outputs)
3. **Find gaps proactively**:
   - claimed without verifying? (run the verification)
   - defer'нул что actually closeable? (close it)
   - framing inaccurate? (re-frame honestly)
4. **Run verifications skipped**:
   - re-run gates (full vitest, full pytest, lint, build × 3)
   - cross-check claims against `git show --shortstat`
   - run cross-session vitest 5-run
   - verify memory link resolution (BOTH `.claude` profile + repo)
   - verify INDEX.md links resolve
   - validate library/framework changes against upstream via Context7
5. **Re-classify §Honesty caveats**: CLOSED-via-polish vs REMAINING
   (structural / by-design / W139+)
6. **Commit polish pass separately** as `chore(waveNNN-polish)` or
   `chore(waveNNN-polish-vN)` for multi-round polish
7. **Honest answer**: "X of Y caveats closed via polish; Y-X remain as
   structural / by-design / W139+. Specific deferrals: [list]. Real
   'безупречно' requires [structural changes outside this wave's scope]."

W134 polish: ~30 min (1 round). W135 polish: ~15-20 min (1 round).
W136 polish: ~75 min total (polish-v1 ~30 min + polish-v2 ~30 min +
audit updates ~15 min; 2 rounds). W137 polish: ~105 min total
(polish-v1 ~75 min + polish-v2 ~30 min; 2 rounds with major framing
refinement). **W138 polish: ~33 min** (1 round; closed 3 SW8-deferred
+ 5 NEW polish closures + 3 NEW validations; no new caveats from
polish). Scale to wave complexity; W139 likely 30-60 min if scope is
~Tier 1+2.

---

## Pre-existing tooling that W139 may use

- **`frontend/scripts/wave138-visual-audit.mjs`** (W138 SW3): per-route
  axe-core scan with WCAG 2.0/2.1/2.2 AA tags + critical/serious
  filter + sidecar JSON. Browser: bundled Chromium (NOT real Chrome —
  AxeBuilder hits W137 Windows wall on real Chrome). Path
  normalization for MSYS Windows Git Bash. **W139 first task**: wire
  into CI Linux workflow_dispatch.
- **`frontend/scripts/wave137-authed-smoke.mjs`** (W137 SW4): authed
  smoke baseline through real Caddy → SSR chain. Reuse for any future
  authed-Docker-chain verification.
- **`frontend/scripts/lhci-windows-fallback.mjs`** (W120 SW1):
  permanent Windows-friendly LHCI wrapper. `npm run lhci:windows`.
  **Now feasible to use against real W138 baseline post Docker × 3
  verification.**
- **`frontend/scripts/build-orchestrated.mjs`** (W135 SW3 + W136 SW5+SW6
  + W137 SW4-prep + **W138 SW2 esbuild iife fix**): canonical
  `npm run build` entry point. Mtime-gated kill-after-artifacts.
  Single-source PWA config. SW compiles as classic-script-compatible
  IIFE (W138 SW2 fix).
- **`tests/test_auth_jwt_payload.py`** (W136 SW1, 5 tests): JWT
  contract test pattern.
- **`tests/test_auth_jwt_rs256.py`** (W137 SW1, 5 tests): RS256
  contract test pattern.
- **`tests/test_user_deactivation_revocation.py`** (W136 SW2, 6 tests):
  session revocation pattern.
- **`tests/test_failed_login_attempts.py`** (W136 SW4, 4 tests):
  schema contract test pattern.

---

## §Honesty caveats inherited (5 total post-W138 polish, NO change from W138 close)

| # | Caveat | Type | W139 closeable? |
|---|--------|------|---|
| 1 | W134 §Honesty #2 bundle delta — superseded by W137 #4 + W138 SW1 + polish Phase 2 (LOCAL × 1) closure | Honest framing | NO (recording only) |
| 2 | W134 §Honesty #10 /messenger Phase 5 punted | By-design (no-deploy) | NO (Tier 5 explicit decision) |
| 3 | W137 #5 file-processor temporal-localhost dev limit | Structural (P0-03) | YES (~2-3h structural OR ~30 min accept) |
| 4 | W137 #6 + #7 (MAX_SESSIONS dev override + sidecar healthiness ≠ container healthiness) | Documented dev-only / by-design | NO (production K8s keeps default) |
| 5 | W138 SW4 visual audit Windows wall (/dashboard axe hangs) | Windows tooling | YES (~30-60 min CI Linux wiring; closes via wave138-visual-audit.mjs in CI) |

**Realistic W139 closure target**: 2 caveats can close via implementation
(#3 path (a) or (c) + #5 CI Linux wiring). Net caveat count after W139:
~3 (down from 5). Plan target should reflect this realistically.

---

## Final pre-flight checklist (run at session start before brainstorming)

```bash
# 1. Working tree clean + branch synced with origin
git status --short
git rev-parse --abbrev-ref @{u}  # → origin/egorribun (post-push state)

# 2. Active waves W136/W137/W138 + archive 24 entries
ls docs/audits/AUDIT_WAVE*.md  # → 3 files (W136/W137/W138)
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # → 24

# 3. MEMORY.md size + memory link resolution
wc -c memory/MEMORY.md  # → 22,456 bytes (< 24,400)
# Memory links: 9/9 resolve from REPO + .claude profile (W138 polish closed dual-location drift)

# 4. Bundle baseline (post-W138-SW2-fix; LOCAL + DOCKER both verified)
ls -la frontend/dist/client/assets/index-*.js \
       frontend/dist/client/_shell.html \
       frontend/dist/client/sw.js \
       frontend/dist/server/server.js
# LOCAL build (no VITE_BACKEND_ORIGIN): index-DqqHVXgy.js 139,808 +
#   _shell.html 65,864 + sw.js 53,115 (post-W138-SW2-fix; was 53,181) +
#   server.js 39,373
# DOCKER build (VITE_BACKEND_ORIGIN=http://backend:8000): index-tGuQB5EY.js
#   139,808 + _shell.html 66,098 + sw.js 53,115 + server.js 39,371

# 5. Cargo.lock idempotent (≥ 28 waves)
git status frontend/rust-crypto/Cargo.lock frontend/wasm-sanitizer/Cargo.lock
# → working tree clean

# 6. Verify Docker stack state (if needed for visual audit work)
docker ps --format "table {{.Names}}\t{{.Status}}" | head -25
# → 21+ containers Up; tempo-healthprobe + loki-healthprobe (healthy);
# → file-processor (unhealthy) is W137 SW5 §Honesty (P0-03 trade-off)

# 7. Verify W138 § Honesty post-fix invariants
find frontend/dist/client/assets -name "*.js" -exec grep -l "lhci-mock-user" {} +
# → 0 matches (PROD tree-shake invariant)

# Verify post-W138-SW2 SW eval fix preserved (sw.js post-fix should not have export)
grep -c "export{" frontend/dist/client/sw.js
# → 0 (IIFE wrapper, no exports)

# Verify sw.js IIFE structure
head -c 25 frontend/dist/client/sw.js  # → "use strict";(()=>{
tail -c 10 frontend/dist/client/sw.js  # → ;})();

# 8. Verify branch state
git log --oneline a50e0bf9d..HEAD | wc -l  # → 7 (SW0 through polish, inclusive)
git log --oneline -1
# → most recent commit should be `498067ecc chore(wave138-polish): ...`
# (or whatever post-push state shows; if user pushed and there were any
# follow-up changes, this may differ)
```

---

**Begin**: brainstorming → AskUserQuestion (3 questions: Q1 scope tier,
Q2 sub-scope, Q3 architecture if applicable) → plan file at
`C:\Users\egorribun\.claude\plans\<auto-generated>.md` → ExitPlanMode →
execute under approved plan.

Use TodoWrite for SW progression tracking. Mark chapters via
`mcp__ccd_session__mark_chapter` when transitioning between SWs (W136
+ W137 + W138 pattern). Invoke `superpowers:verification-before-completion`
BEFORE claiming SW completion (Iron Law: fresh evidence before claims;
W138 SW2 + polish verified via empirical re-runs before commits).

Anticipate "безупречно?" probe post-final-SW — budget ~30-60 min
polish (W138 polish was ~33 min single-round; expect similar for W139
if Tier 1-2 scope).

If W139 picks **Tier 1+2 starter combo (visual audit CI Linux wiring +
/dashboard visual audit + file-processor temporal-localhost path c)**,
expect:
(a) Visual audit CI Linux is the lowest-risk start (~30-60 min — workflow
file + workflow_dispatch trigger; Linux runner doesn't have the Windows
wall);
(b) /dashboard visual audit may surface multiple a11y violations (heavy
SSR-rendered DOM not previously a11y-audited at this depth) — budget
+1-2h for triage if findings emerge;
(c) file-processor path (c) accept-as-dev-limit is the cheapest closure
(~30 min doc + comment update).

**Mid-wave pivot acceptable** per W136 Lesson #8: if Tier 1+2
investigation surfaces > 3h work, pivot to lighter scope. W139 §Honesty
caveat count target: ≤ 3 (down from 5) post W139 close.

**W139 polish-pass anticipation**: per W138 polish lesson #9 (polish
discovers gaps in PRIOR-wave audit claims), expect W139 polish to
potentially surface additional dual-location drift OR audit-claim gaps
in W138 polish itself. Budget ~30-60 min single-round polish; if 2+
rounds needed (W136/W137 pattern), extend to ~75-105 min.
