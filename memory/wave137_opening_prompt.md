# Wave 137 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 136 CLOSED** (2026-05-07) — Tier 1 + Tier 2 + Tier 3 per user-approved
3-question AskUserQuestion (Q1=Tier 1+2+3, Q2=JWT (d) Hybrid, Q3a=Medium
process._getActiveHandles trace, Q3b=Playwright real-Chrome path).

### 8+1 git commits ahead of W135 close (`f05836d0d`)

1. **`3fb5451cc`** SW0 `docs(wave136-sw0-design)` — design doc only (1 file +209)
2. **`b37e827e4`** SW1 `feat(wave136-sw1-jwt-is-active-embed)` — backend
   embeds is_active claim in JWT (2 files +232; 5 tests)
3. **`6989637f0`** SW2 `feat(wave136-sw2-deactivation-revocation-broadcast)`
   — publish session JTIs on user delete via existing Redis pub/sub
   (2 files +325; 6 tests; NO new NATS subject — leveraged
   `revoke_sessions_matching` infrastructure)
4. **`7bccb5ee7`** SW3 `feat(wave136-sw3-playwright-visual-smoke)` —
   Windows wall alternative via real Chrome (2 files +392)
5. **`938c797a6`** SW4 `fix(wave136-sw4-failed-login-attempts-nullable-user-id)`
   — REPRODUCED in test SQLite + model+schema fix (3 files +255; 4 tests)
6. **`c67ac5cce`** SW5 `feat(wave136-sw5-build-orchestrated-hang-trace)` —
   identified MessagePort + Worker hang root cause + bonus mtime regression
   fix (3 files +240/-9)
7. **`3314364bd`** SW6 `feat(wave136-sw6-workbox-export-linux-ci)` —
   single-source PWA_INJECT_CONFIG + Linux CI workflow (4 files +251/-44)
8. **`51139c2e7`** SW7 `chore(wave136-sw7-housekeeping)` — delete obsolete
   nginx.conf + 3 healthchecks (2 files +34/-148)
9. **(SW8 this commit)** `docs(wave136-sw8-audit-handoff)` — audit + memory +
   N+3 rotation

Verify session-start: `git log --oneline f05836d0d..HEAD | wc -l` → **8-9**.

## Bundle baseline post-W136 (BYTE-IDENTICAL to W135)

```
dist/client/assets/index-DqqHVXgy.js  139,808 bytes
dist/client/_shell.html                65,864 bytes
dist/client/sw.js                      53,181 bytes
dist/server/server.js                  39,373 bytes
Workbox precache: 209 files / 4.80 MB
```

`npm run build` works on Windows via `frontend/scripts/build-orchestrated.mjs`
(W135 SW3 + W136 SW5 mtime fix + SW6 single-source PWA config). Build × 3
reproducible. `WAVE136_HANG_TRACE=1` env enables diagnostic agent (W136 SW5).

Build wall-time ~30s/run on Windows (vs W135 SW3 ~26s; slight increase due
to W136 SW5 mtime check waiting for fresh artifacts; previously triggered
prematurely on stale leftovers).

## NO-DEPLOY scope clarified 2026-05-08 (W134/W135/W136 carried forward)

Cluster deployment NOT pursued. Goal is "fully working + visually + internally
flawless локально + структурно". Cluster-dependent items remain removed
(Phase 6 actual rollout, RUM wiring, Caddy weight flip live test, kubectl
apply, etc.).

W125-W133 SSR migration arc remains shipped + locally verified +
structurally correct. W136 closed 6 of 9 W135 § Honesty caveats; 3 carry
forward + 3 NEW caveats from W136 SW5+SW7 = 6 remaining post-W136.

## Gates baseline (preserved through W136)

- tsc 0 errors, lint 0 warnings (max-warnings=0; broader src/ scan
  including eslint-plugin-react-compiler at error level)
- vitest **TBD post-W136** (W135 baseline 1052p; W136 added 15 backend
  tests but didn't touch frontend tests; full vitest re-run polish-pass
  candidate)
- pytest backend slice **W136 added 15 new tests across SW1+SW2+SW4**;
  slice cumulative 28 tests passed in SW4 verification
- npm audit **0 vulnerabilities** (preserved; W136 added no npm deps)
- Cargo.lock no drift (idempotent ≥ 26 waves at end of W136)
- i18n parity 18p (translationParity.test.ts; W136 added no user-facing strings)
- MEMORY.md size **TBD post-W136** (last known 24,090 bytes pre-W136;
  W136 SW8 adds backlog row but compaction not in W136 scope)
- Archive directory: 17 W117-W133 audit files post-N+3 (W133 newly rotated SW8)
- Tree-shake invariant ✓ (PROD `grep -l "lhci-mock-user" dist/client/assets/*.js` → 0)
- **Build × N reproducibility post-W136 SW5+SW6**: BYTE-IDENTICAL to W135
  baseline confirmed across 2+ runs

**Active waves after N+3 rotation**: W134 / W135 / **W136**

## SSR routes (8 total — preserved through W136)

W136 added NO new SSR routes. SW1+SW2 are infrastructure-level changes
(JWT claim + Redis pub/sub broadcast); SW3+SW5+SW6 are tooling/build
infrastructure; SW4+SW7 are model+infra cleanup.

## Wave 137 candidates (post-W136)

### Highest priority (W136 § Honesty TOP discoveries / closures)

- **Real Docker chain authed visual smoke** (~1-2h, HIGH) — with W136
  SW1+SW2 JWT infrastructure + SW4 schema fix + SW3 Playwright tool now
  in place, end-to-end authed flow through Caddy → gateway → backend
  can be smoke-tested via real authed browser session. Closes W135
  § Honesty #9 fully. Approach: register test user → activate → login
  via Playwright → capture authed cookie → run visual smoke against 8
  SSR routes through Caddy chain.

- **vitejs/rolldown upstream hang issue** (~1-2h) — file with W136 SW5
  trace data: `MessagePort + Pipe + Socket × 2` after artifact emission;
  Worker thread spawned by some plugin (likely Rolldown native or
  `@rolldown/plugin-babel`) not terminated post-build. Reproduces on
  Windows + clean dist/. Closes W135 § Honesty #4 structurally if
  upstream fix lands.

- **chrome-devtools-mcp upstream issue** (~1h) — file with W135 SW2 +
  W136 SW3 repro of Accessibility.getFullAXTree timeout family on
  Windows + headless Chrome. Closes W136 § Honesty #1 carry-forward
  if upstream fix lands.

### Tier 2/3 carry-forward (W136 deferrals)

- **file-processor Dockerfile + grpc_health_probe** (~30 min) — COPY
  binary in runtime image to enable compose-level healthcheck.
- **tempo + loki distroless workaround** (~30-60 min) — either package
  with grpc_health_probe or use sidecar HTTP probe container.
- **Playwright VITE_E2E_MODE flag** (~30 min) — disable
  ParticleAuthBackground canvas in test mode so SW3 visual smoke
  screenshots can capture cleanly. Closes W136 § Honesty #12.

### Pre-existing W134 carry-forward (NOT closeable without structural change)

- **W134 § Honesty #2 (bundle delta +259 bytes)** — honest framing
  recording. W136 produces BYTE-IDENTICAL to W135 baseline (neutral
  net delta).
- **W134 § Honesty #10 (/messenger Phase 5 punted)** — no-deploy
  "production-as-is" decision unchanged.

### Tier 4 cross-cutting (carry-forward)

- Test infrastructure expansion (a11y-public WebKit OOM W115 SW1;
  mobile-webkit /404 W116 SW1 remainder)
- LHCI gate ratchet on local baseline
- a11y deep-audit cross-browser
- i18n parity consolidation
- **Per-page visual audit on 8 SSR routes** (~0.5-1 wave per page) — now
  feasible via W136 SW3 Playwright + W136 SW1+SW2 authed flow
- Storybook/Chromatic activation (requires user-side
  CHROMATIC_PROJECT_TOKEN)

### Tier 5 explicit user decision (carry-forward)

- /messenger × 2 polish arc (~5-7 waves) — pursue OR explicitly punt as
  "production-as-is"
- /admin polish arc (~3-5 waves) — pursue OR punt

### Polish-pass candidates (anticipated post-W136 SW8 / handoff)

- Cross-session vitest 5-run (~2.5 min) — closes any potential post-W136
  flake band
- Build × 3 post-SW8 reproducibility check (~1.5 min) — invariant proof
- AUDIT_WAVE136.md commit-stat cross-check via `git show --stat`
  (~1 min) — invariant proof
- Memory file dual-location sync (~30s) — both USER `.claude` + REPO
- Archive directory presence verification (~30s)
- MEMORY.md size check < 24,400 (~30s)

## Anticipated AskUserQuestion 3-question pattern

W133/W134/W135/W136 successful pattern:

1. **Q1 — Primary scope tier**: Tier 1 W136 § Honesty TOP closures (Real
   Docker chain authed smoke + upstream issue files) vs Tier 2 carry-
   forward (file-processor + tempo/loki healthchecks + Playwright
   VITE_E2E_MODE) vs Tier 4 cross-cutting (per-page audit, LHCI ratchet,
   a11y deep-audit, i18n consolidation) vs Tier 5 explicit decision
   (Messenger/Admin OR punt).

2. **Q2 — Within chosen tier, sub-scope**: e.g. Tier 1 → which upstream
   issue first OR all 3? Real Docker smoke depth — 8 routes vs subset?
   Authed user setup approach — Playwright cookie capture vs direct
   backend JWT mint?

3. **Q3 — Architecture/design (if applicable)**: e.g. Tier 1 + 2 → if
   real Docker smoke surfaces NEW backend bugs (like W135 SW2 surfaced
   JWT mismatch + failed_login_attempts), how to handle in W137 vs W138?
   Tier 4 → per-page visual audit ordering (highest-traffic first?
   simpler pages first as quick wins?)

## Read mandatory files in order

1. **`docs/audits/AUDIT_WAVE136.md`** — full SW0-SW7 narrative + verification
   matrix + § Honesty probe (12 caveats: 6 closed via implementation;
   3 W135 carry; 3 NEW from W136) + W137 candidates + lessons-learned
2. **`memory/wave136_backlog.md`** — close-status entry-point file refs
3. **`memory/wave137_opening_prompt.md`** — this file
4. **`docs/plans/2026-05-07-wave136-tier-1-2-3-design.md`** — W136 design
   doc (architecture diagrams + decision trees)
5. **`docs/plans/2026-05-08-wave133-c-plus-d-design.md`** — W133
   architectural decisions + Bridge mechanism context
6. **`docs/plans/2026-05-01-wave125-ssr-design.md`** § Phase 5-6 — original
   SSR design source
7. **`CLAUDE.md`** ## Audit Trail W136 row + new W136 gotchas:
   - JWT is_active claim contract
   - Backend session revocation broadcast pattern (existing Redis pub/sub)
   - Playwright real-Chrome as Windows visual-smoke standard
   - failed_login_attempts conditional INSERT (model + alembic)
   - build-orchestrated mtime regression fix + hang trace agent
   - PWA_INJECT_CONFIG single source
   - 3 docker-compose healthchecks added
8. **`memory/MEMORY.md`** — auto-loaded; W136 row at top
9. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?" probe
10. **`memory/feedback_planning_estimates.md`** — range estimates; "production-
    grade polish" anchor

## Skills to invoke immediately

- **`superpowers:brainstorming`** — invoke FIRST per W134/W135/W136 success
  pattern (3-question AskUserQuestion). MANDATORY before any creative work.
- **`superpowers:writing-plans`** — for plan file creation in plan mode
  after brainstorming
- **`superpowers:systematic-debugging`** — invoke if hitting bugs (W136 SW4
  + SW5 surfaced REAL bugs via reproduce-first pattern; expect more W137)
- **`superpowers:verification-before-completion`** — invoke BEFORE claiming
  SW completion
- **`superpowers:executing-plans`** — invoke AFTER plan approval

## Use Context7 MCP

For TanStack Start v1 / vite 8 / Rolldown / vite-plugin-pwa /
workbox-build / Playwright API / Caddy / chrome-devtools-mcp /
Go middleware patterns / SQLAlchemy 2.0 / Alembic docs.

W136 likely Context7 lookups for W137:
- vitejs/rolldown Worker thread lifecycle (for upstream issue file)
- Playwright cookie capture + reuse for authed smoke
- Distroless image healthcheck patterns

## "безупречно?" probe response template (per memory/feedback_perfectionism.md)

When user invokes "безупречно?" / "всё ли идеально?" / "полностью выполнено?"
after I claim wave completion:

1. **DO NOT reassure** — это probe для honest self-audit + polish pass
2. **List claims explicitly** with evidence
3. **Find gaps proactively** — claimed without verifying? defer'нул что
   actually closeable? framing inaccurate?
4. **Run verifications skipped** — re-run gates, cross-check claims against
   `git show --stat`, run cross-session vitest
5. **Re-classify § Honesty** — CLOSED-via-polish vs REMAINING (structural /
   by-design / W137+)
6. **Commit polish pass separately** as `chore(waveNNN-polish)`
7. **Honest answer**: "X of Y caveats closed via polish; Y-X remain as
   structural / by-design / W137+. Specific deferrals: [list]."

W134 polish budget was ~30 min; W135 polish ~15-20 min. Scale to wave
complexity. W136 polish budget anticipated ~30-60 min given 12 § Honesty
caveats list (6 closed + 3 carry + 3 new).

## Pragmatic recommendation (для Q1 ответа)

- **Best ROI immediate**: **Real Docker chain authed visual smoke + 3
  upstream issue files** (~3-4h combined). All structural follow-throughs
  on W136 closures.
- **Best W137 starter combo**: **Tier 1 (3-4h) + Tier 2 carry-forward
  (file-processor + tempo/loki + Playwright VITE_E2E_MODE ~1.5h)** (~4.5-5.5h)
  — closes most W136 deferrals to ≤3 § Honesty post-W137.
- **Tier 5 explicit decision**: confirm Messenger/Admin scope OR punt as
  "production-as-is" before W138+.

---

**Begin**: brainstorming → AskUserQuestion (3 questions) → plan file →
ExitPlanMode → execute.

Use TodoWrite for SW progression tracking. Mark chapters via
mcp ccd_session__mark_chapter when transitioning between SWs. Invoke
`superpowers:verification-before-completion` before claiming SW
completion. Anticipate "безупречно?" probe post-SW8 — budget ~30-60 min
polish.
