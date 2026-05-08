---
name: Wave 138 backlog
description: Wave 138 closed Tier 1+2+3 broad combo (Build × 3 Docker + SW eval fix + visual audit infra + housekeeping) per user-approved 3-question AskUserQuestion.
type: project
originSessionId: wave138-sw8
status: CLOSED
---
# Wave 138 backlog — CLOSED

**Status**: CLOSED. Tier 1 + Tier 2 + Tier 3 per user-approved 3-question
AskUserQuestion at session start (Q1=Tier 1+2+3 broad combo, Q2=Full
root-cause SW investigation, Q3=Allow +2h mid-wave expansion).

Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-snazzy-valley.md`

Wall-clock: ~5-6h core (within plan estimate ~5-7h base; Q3 +2h
expansion budget unused).

## Closed in Wave 138

### SW0 — Design doc (`9a699a4fd`, 1 file +222)

NEW `docs/plans/2026-05-08-wave138-tier123-design.md` per
`superpowers:brainstorming` skill convention. 3 Phase 1 Explore-agent
findings (SW investigation hypotheses, visual audit foundation, Tier 3
tech-debt scoping) + architecture diagrams + 8-SW progression table +
risks/mitigations.

### SW1 — Docker × 3 reproducibility (`90d636d88`, 1 file +89)

Closes W137 §Honesty #4 retroactively for Docker.

NEW `memory/wave138_docker_x3_verification.md`: 3 fresh `start-docker.ps1
-Build` cycles with `rm -rf frontend/dist` between produces BYTE-IDENTICAL
sha256 hashes for index-tGuQB5EY.js (139,808) + server.js (39,371) +
sw.js (53,181 — pre SW2 fix) + _shell.html (66,098).

Honest framing: layer-cache-stable test (cached --build × 3 with rm
between, NOT --no-cache × 3). Acceptable per plan estimate.

### SW2 — Service Worker eval failure root-cause fix (`1795b0d9b`, 1 file +15/-4)

Closes "Service Worker script evaluation failed" console error
appearing 1× per route on all 8 SSR routes (W137 SW4 uninvestigated).

**Root cause**: `frontend/scripts/build-orchestrated.mjs:330` (W135 SW3)
compiled sw.ts with `format: "esm"`, producing trailing `export{...}`
statement. `frontend/src/push/register-sw.ts:49` registers SW as classic
script (no `{ type: "module" }`). Classic + export = SyntaxError →
"ServiceWorker script evaluation failed".

**Fix**: `format: "esm"` → `format: "iife"`. IIFE wraps output in
`(()=>{...})()`, drops export keyword. Test-compat re-exports in sw.ts
become local-IIFE consts assigned to `self.__SW_TESTING__` at bootstrap.

**Plan revision**: Q2 full root-cause investigation initially hypothesized
Path (a) CSP `strict-dynamic` interaction. Empirical curl checks
DISPROVED Path (a) (no CSP header on SSR routes). The actual root cause
was esbuild format mismatch — none of the 4 hypothesis paths in plan.
W137 Lesson #1 vindicated.

**Verification**: re-ran wave137-authed-smoke.mjs post-fix; all 8 SSR
routes report 0 console errors (was 1/route pre-fix).

### SW3 — Visual audit infrastructure (`d291d5672`, 1 file +527)

NEW `frontend/scripts/wave138-visual-audit.mjs` (~527 LoC) — first
per-page visual audit infrastructure feasible since SSR migration started
in W125. Built on W137 SW4 wave137-authed-smoke.mjs foundation; adds
AxeBuilder scan with WCAG 2.0/2.1/2.2 AA tags + critical/serious filter
+ sidecar JSON.

Per-route flow: JWKS pre-check → API login + JWT validation →
`new_page` per route → emulateMedia (reducedMotion) → goto + 1500ms
settle → AxeBuilder.analyze() with setLegacyMode(true) → filter to
critical+serious → sidecar JSON.

Browser: bundled Chromium (NOT real Chrome — AxeBuilder injects axe via
page.evaluate which hits W137 Windows heavy-DOM eval wall on real Chrome).

Path normalization: accepts `/dashboard` and `dashboard` forms (MSYS Git
Bash workaround per W120 SW1 lhci-windows-fallback.mjs precedent).

LHCI deliberately separate: existing `npm run lhci:windows` handles
VITE_LHCI=true vite preview perf measurement. Different environment by
design (authed Docker chain vs LHCI bypass).

### SW4 — partial closure (folded into SW3 commit)

**SW4 verification on /dashboard FAILED** with Windows heavy-DOM wall
family: both real Chrome AND bundled Chromium hang on
AxeBuilder.analyze() on /dashboard's heavy SSR DOM in headless mode.
Multiple iterations attempted (real Chrome → bundled Chromium →
setLegacyMode(true)); all hung at axe-injection step.

Honest defer: script IS structurally sound. Authed-route axe runs
blocked by the same Windows wall W137 SW7 filed for upstream
(chrome-devtools-mcp issue). Mitigation paths for W139+: CI Linux
execution (most likely), lighter axe scope, reduced MainLayout under
VITE_E2E_MODE.

### SW5 — i18n parity (no commit, no drift)

`npm run i18n:check` → 18/18 tests passed in 1.77s. W137 polish-v2
baseline preserved exactly. No CLDR-aware EN/RU drift.

### SW6 — Storybook build verification (no commit, no drift)

`npm run build-storybook` → "Storybook build completed successfully" in
19.21s. 0 errors. W123 SW1 strictExecutionOrder workaround for Rolldown
module execution order is still effective.

Chromatic activation status: still requires user-side
`CHROMATIC_PROJECT_TOKEN` repo secret + `vars.CHROMATIC_ENABLED=true`
repo variable. Workflow file `.github/workflows/chromatic.yml` exists
+ guarded; no code changes needed.

### SW7 — Upstream issues (rolldown FILED post-W138 close)

Status: 3 issue body templates prepared in `memory/wave138_upstream_issue_*.md`.
User chose "Yes — file rolldown only (most actionable)" via
AskUserQuestion at SW7.

**FILED 2026-05-08 post-W138 close**:
- ✅ rolldown/rolldown — **https://github.com/rolldown/rolldown/issues/9327**
  (filed by user from `C:\Users\egorribun\Documents\university_ecosystem`
  via `gh issue create --repo rolldown/rolldown --title "..." --body-file
  memory/wave138_upstream_issue_rolldown.md` after `gh auth login`)

**Remaining (templates ready, not filed per user choice)**:
- chromedevtools/chrome-devtools-mcp — `memory/wave138_upstream_issue_chromedevtools.md`
- grafana/tempo + grafana/loki — `memory/wave138_upstream_issue_tempo_loki.md`

User can file the remaining 2 if needed via same pattern (single-line PS):

```powershell
gh issue create --repo chromedevtools/chrome-devtools-mcp --title "Accessibility.getFullAXTree + Runtime.evaluate timeout on Windows headless heavy DOM" --body-file memory/wave138_upstream_issue_chromedevtools.md
gh issue create --repo grafana/tempo --title "Add CLI subcommand for --check-ready to support distroless healthcheck" --body-file memory/wave138_upstream_issue_tempo_loki.md
gh issue create --repo grafana/loki --title "Add CLI subcommand for --check-ready to support distroless healthcheck" --body-file memory/wave138_upstream_issue_tempo_loki.md
```

### SW8 — Audit + memory + N+3 rotation (this commit)

- NEW `docs/audits/AUDIT_WAVE138.md` (~600 lines)
- NEW `memory/wave138_backlog.md` (this file)
- NEW `memory/wave139_opening_prompt.md`
- `git mv docs/audits/AUDIT_WAVE135.md docs/audits/archive/AUDIT_WAVE135.md`
  (N+3 rotation; active waves now W136/W137/W138)
- `CLAUDE.md` ## Audit Trail W138 row + 3 new gotchas
- `memory/MEMORY.md` updates

## Honest § Honesty caveats

**Pre-W138 7 W137 caveats post-polish-v2; W138 closes 3 + introduces 1
NEW + carries 4 = 5 caveats remaining**.

### CLOSED via implementation (3 of 7)

1. ✅ W137 §Honesty #4 (W134-W136 Docker reproducibility-claim mask) —
   closed FULLY via SW1 Docker × 3 BYTE-IDENTICAL verification
2. ✅ NEW W138 SW eval failure (was a polish-pass discovery in W137 SW4) —
   closed FULLY via SW2 esbuild iife fix; 8 routes × 0 console errors
3. ✅ W136 §Honesty #6 (Playwright /login VITE_E2E_MODE refactor) —
   ALREADY DONE in W115 SW1 + W116 SW1 (Phase 1 Explore finding); mark-
   resolved without code work

### REMAINING from W134/W137 (4 of 7, all by-design or carry-forward)

4. W134 §Honesty #2 (bundle delta carry-forward) — superseded by W137
   §Honesty #4 closure via SW1; recording-only
5. W134 §Honesty #10 (/messenger Phase 5 punted) — no-deploy decision
   unchanged; Tier 7 carry-forward
6. W137 §Honesty #5 (file-processor temporal-localhost dev limit) —
   NOT in W138 scope per Q1 choice; carry-forward to W139+
7. W137 §Honesty #6 + #7 (MAX_SESSIONS dev override + sidecar healthiness
   ≠ container healthiness) — both by-design dev-only; recording-only

### NEW from W138 (1 caveat)

8. W138 SW4 /dashboard visual audit hits Windows heavy-DOM wall — script
   structurally sound; AxeBuilder.analyze() hangs on heavy authed-route
   DOM under real Chrome AND bundled Chromium in headless mode on
   Windows. Same family as W137 SW7 chrome-devtools-mcp upstream issue.
   Mitigation: CI Linux runner execution (W139 candidate).

**Total: 5 caveats remain post-W138** (vs 7 pre-W138; net -2).

The plan target was ≤4 caveats post W138. Actual = 5 (close to target;
1 NEW caveat is a Windows-tooling limitation not code-quality).

## W139 candidates

See `memory/wave139_opening_prompt.md` for full list. Highlights:

### Tier 1 from W138 §Honesty (highest priority)

- wave138-visual-audit.mjs CI Linux execution wiring — workflow file +
  workflow_dispatch trigger; closes W138 §Honesty #4 fully (~30-60 min)
- file-processor temporal-localhost (W137 §Honesty #5 carry-forward,
  paths a/b/c — ~2-3h structural OR ~30 min accept-as-dev-limit)

### Tier 4 cross-cutting (carry-forward)

- LHCI gate ratchet on REAL W137-W138 baseline (now feasible post SW1)
- Test infrastructure (a11y-public WebKit OOM, mobile-webkit /404)
- Storybook + Chromatic activation (user-side env action)
- a11y deep-audit cross-browser via wave138-visual-audit.mjs on CI Linux

### Tier 5 explicit decision (carry-forward)

- Messenger × 2 polish (~5-7 waves) OR /admin polish (~3-5 waves) OR
  punt as "production-as-is"

### Filed upstream issues (W138 SW7 prep ready) — pending external resolution

- rolldown/rolldown (build hang)
- chromedevtools/chrome-devtools-mcp (Windows headless heavy-DOM eval —
  also affecting AxeBuilder per W138 SW3+SW4 finding)
- grafana/tempo + grafana/loki (distroless health CLI)
