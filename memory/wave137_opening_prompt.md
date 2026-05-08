# Wave 137 — opening prompt (NO-DEPLOY scope continued)

## State at session start

**Wave 136 CLOSED + POLISHED ×2** (2026-05-08) — Tier 1 + Tier 2 + Tier 3 per
user-approved 3-question AskUserQuestion (Q1=Tier 1+2+3, Q2=JWT (d) Hybrid,
Q3a=Medium process._getActiveHandles trace, Q3b=Playwright real-Chrome path).

W136 closed **6 of 9 W135 §Honesty caveats via implementation + 1 via polish-v1
memory link rot fix + partial closure of W135 §Honesty #9 via polish-v2 real
Docker chain authed smoke**. Surfaced **3 NEW caveats** (build-orchestrated
upstream hang, Tier 3 partial 3 distroless services, Playwright /login canvas
fragility) + **1 NEW W137 finding from polish-v2** (ssrAuth.ts RS256/HS256
layer mismatch in dev Docker stack).

### 11 git commits ahead of W135 close (`f05836d0d`)

1. `3fb5451cc` SW0 `docs(wave136-sw0-design)` — design doc only (1 file +209)
2. `b37e827e4` SW1 `feat(wave136-sw1-jwt-is-active-embed)` — backend embeds
   `is_active` claim in JWT (2 files +232; 5 tests)
3. `6989637f0` SW2 `feat(wave136-sw2-deactivation-revocation-broadcast)` —
   publish session JTIs on user delete via existing Redis `session:revocations`
   pub/sub (2 files +325; 6 tests; **NO new NATS subject** — leveraged existing
   `revoke_sessions_matching` infrastructure per Explore-agent discovery)
4. `7bccb5ee7` SW3 `feat(wave136-sw3-playwright-visual-smoke)` — real-Chrome
   alternative for Windows wall (2 files +392)
5. `938c797a6` SW4 `fix(wave136-sw4-failed-login-attempts-nullable-user-id)` —
   model + alembic migration; bug REPRODUCED in test SQLite first
   (3 files +255; 4 tests)
6. `c67ac5cce` SW5 `feat(wave136-sw5-build-orchestrated-hang-trace)` —
   identified MessagePort + Worker hang root cause + bonus mtime regression
   fix (3 files +240/-9)
7. `3314364bd` SW6 `feat(wave136-sw6-workbox-export-linux-ci)` — single-source
   `PWA_INJECT_CONFIG` + Linux CI workflow (4 files +251/-44)
8. `51139c2e7` SW7 `chore(wave136-sw7-housekeeping)` — delete obsolete
   `frontend/nginx.conf` + 3 of 6 healthchecks (2 files +34/-148)
9. `db1377adb` SW8 `docs(wave136-sw8-audit-handoff)` — AUDIT + W137 prompt +
   N+3 rotation (W133 → archive) + MEMORY compaction (6 files +1158/-1)
10. `6e3429482` polish-v1 — 11 verification gate re-runs + memory link rot
    fix (34/40 → 40/40 references resolve in MEMORY.md) (2 files +135/-16)
11. `9cc3a2789` polish-v2 — partial closure of W135 §Honesty #9 via real Docker
    chain authed smoke (NEW `wave136-polish-authed-smoke.mjs` Playwright
    script; W136 SW1+SW2 verified in production stack; ssrAuth.ts
    RS256/HS256 mismatch surfaced as NEW W137 candidate) (2 files +473/-3)

Verify session-start: `git log --oneline f05836d0d..HEAD | wc -l` → **11**
(matches expected; if different, investigate before brainstorming).

```bash
git status --short  # Should be clean working tree
ls docs/audits/AUDIT_WAVE*.md  # Should be 3 files: W134/W135/W136
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # Should be 22 (W112-W133)
wc -c memory/MEMORY.md  # Should be ~24,000 bytes (< 24,400 auto-load threshold)
```

---

## Bundle baseline post-W136 (BYTE-IDENTICAL to W134 + W135 — 3-wave invariant)

```
dist/client/assets/index-DqqHVXgy.js  139,808 bytes
dist/client/_shell.html                65,864 bytes
dist/client/sw.js                      53,181 bytes
dist/server/server.js                  39,373 bytes
Workbox precache: 209 files / 4.80 MB
```

Build × 3 reproducible via `npm run build` (= `frontend/scripts/build-orchestrated.mjs`):
- Wave 135 SW3 retired `wave127-build-x3.sh` watch+kill workaround
- Wave 136 SW5 added `WAVE136_HANG_TRACE=1` env diagnostic agent + fixed mtime
  regression (was triggering on stale leftover artifacts)
- Wave 136 SW6 added single-source `frontend/scripts/workbox-config.mjs` —
  no more drift between `vite.config.mts` + `build-orchestrated.mjs`

Build wall-time ~30s/run on Windows (W135 SW3 ~26s; SW5 mtime check waits
slightly longer for fresh artifacts; difference is verification correctness,
not regression).

**Hang root cause** identified in W136 SW5: `MessagePort + Pipe + Socket × 2`
post-prerender = Worker thread spawned by some plugin (likely Rolldown native
pool or `@rolldown/plugin-babel`) not terminated. Filed for upstream W137+.

---

## NO-DEPLOY scope continued (W134/W135/W136 carried forward)

Cluster deployment NOT pursued. Goal: "fully working + visually + internally
flawless локально + структурно". Cluster-dependent items remain removed
(Phase 6 actual rollout, RUM wiring, Caddy weight flip live test, kubectl
apply, etc.).

W125-W133 SSR migration arc remains shipped + locally verified + structurally
correct. W136 closed 6 of 9 W135 §Honesty caveats via implementation; partial
closure of #9 via polish-v2; 5 remaining post-W136 (3 carry + 2 NEW).

---

## Gates baseline (preserved through W136 + polish-v1 + polish-v2)

| Gate | Value | Polish status |
|------|-------|---------------|
| `npx tsc --noEmit` | 0 errors | polish-v1 ✓ |
| `npm run lint` (max-warnings=0) | 0 errors / 0 warnings | polish-v1 ✓ |
| `npx vitest run` single | **1052p / 12s / 0f** | polish-v1 ✓ |
| Cross-session vitest 5-run | **5/5 × 1052p / 12s / 0f** (flake band = 0) | polish-v1 ✓ |
| pytest backend slice | **90p / 0f** (auth + user + login_service + auth_concurrency + W131 cookie + W136 SW1+SW2+SW4) | polish-v1 ✓ |
| `npm audit` | **0 vulnerabilities** | polish-v1 ✓ |
| Cargo.lock no drift | working tree clean (≥ 26 waves idempotent) | polish-v1 ✓ |
| i18n parity | 18 tests passed (CLDR-aware EN/RU) | polish-v1 ✓ |
| Tree-shake invariant | 0 matches for `lhci-mock-user` in PROD dist/client/assets/*.js | polish-v1 ✓ |
| Build × 3 BYTE-IDENTICAL | hash + sizes match across × 3 runs | polish-v1 ✓ |
| AUDIT_WAVE136 commit-stat | 9/9 W136 commits match audit doc claims via `git show --shortstat` | polish-v1 ✓ |
| MEMORY.md size | **23,977 bytes** (< 24,400 auto-load truncation) | polish-v1 ✓ |
| Memory link resolution | **40/40 references resolve** | polish-v1 fix (was 34/40) |
| Real Docker chain authed flow (API/gateway) | HTTP 200 on /api/v1/users/me | polish-v2 ✓ NEW |
| W136 SW4 alembic migration | applied automatically on backend rebuild | polish-v2 ✓ NEW |
| Active waves (N+3) | W134/W135/W136 | SW8 ✓ |
| Archive directory | 22 entries W112-W133 | SW8 ✓ |

---

## SSR routes (8 total — preserved through W136)

W136 added NO new SSR routes. SW1+SW2+SW4 are backend code/schema; SW3 is a
new Playwright tool; SW5+SW6 are build infrastructure; SW7 is housekeeping.

| Route | Status | Wave |
|-------|--------|------|
| `/dashboard` | SSR | W128 SW3 |
| `/events` | SSR | W129 SW1 |
| `/events/$id` | SSR | W129 SW2 |
| `/news` | SSR | W129 SW4 |
| `/news/$id` | SSR | W129 SW5 |
| `/schedule` | SSR (full sequential per W133 SW3) | W130 SW2 + W133 SW3 |
| `/profile` | SSR | W133 SW4 |
| `/settings` | SSR + tab=N URL param + Security-tab sessions prefetch | W133 SW5 + W134 SW2 |

Remaining `ssr: false`: 2 (messenger × 2 — heavy WebSocket + IndexedDB at
render time, deferred indefinitely under no-deploy "production-as-is").

`/map` + `/activity` preserved at `ssr: 'data-only'` (W127 SW6 annotations
under permissive parent `_auth.tsx ssr: true` W128 SW2).

---

## Wave 137 candidates (post-W136)

### Tier 1 — HIGH priority (W136 polish-v2 finding + W135 §Honesty #9 partial)

- **ssrAuth.ts RS256/HS256 layer reconciliation** (~1-2h or ~2-3h, NEW from
  polish-v2). Frontend Node SSR's `frontend/src/ssrAuth.ts` uses
  `jose.createRemoteJWKSet` (defaults to RS256) but dev Docker backend signs
  JWT with HS256. SSR-time `beforeLoad` fails validation → redirect to /login
  even with valid cookie. Two paths:
  - **(a) Backend RS256 in dev** (~2-3h): generate RSA keypair, configure
    backend `JWT_ALGORITHM=RS256` + `JWT_SIGNING_KEYS` for compose env,
    publish public key via existing `/.well-known/jwks.json` endpoint
    (`app/api/well_known.py`). Matches production deploy assumption.
    Recommended.
  - **(b) ssrAuth.ts HS256 fallback** (~1-2h): plumb SECRET_KEY into
    frontend SSR env via docker-compose; `ssrAuth.ts` falls back to HS256
    if env present. Faster but bakes dev-only path into production code.
  - **Outcome of either**: closes W135 §Honesty #9 fully (was partial post-
    polish-v2). Real Docker chain authed visual smoke through 8 SSR routes
    becomes runnable via the existing `wave136-polish-authed-smoke.mjs`
    script.

- **`.env` ↔ `.env.docker` SECRET_KEY sync** (~30 min, polish-v2 bonus
  finding). `start-docker.ps1` generates `.env.docker` with real 64-char
  SECRET_KEY but the project-root `.env` (used by compose's `${SECRET_KEY}`
  substitution) keeps the Pydantic Settings default placeholder
  `dev_secret_key_change_in_production_use_secrets_token_urlsafe_64`.
  Result: gateway `JWT_SECRET` env reads stale value → JWT validation
  fails. Polish-v2 sed-fixed locally (since `.env` is gitignored). Fix:
  `start-docker.ps1` should also update `.env` SECRET_KEY at generation
  time to match `.env.docker`. ~30 min.

### Tier 2 — Real Docker chain authed visual smoke FULL closure (W137 main goal)

- **Real Docker chain authed visual smoke** (~1-2h after Tier 1 lands).
  After ssrAuth.ts layer reconciled, run
  `node ./scripts/wave136-polish-authed-smoke.mjs` end-to-end through 8 SSR
  routes via Caddy → frontend SSR → gateway → backend chain. Verify each
  returns 200 + 0 React hydration errors + sidecar JSON shows expected
  network requests. **Closes W135 §Honesty #9 fully**.

### Tier 3 — Upstream issue files (W136 §Honesty #4 + chrome-devtools wall)

- **vitejs/rolldown upstream hang issue** (~1-2h). File at vitejs/vite OR
  rolldown/rolldown with W136 SW5 trace data: `MessagePort + Pipe +
  Socket × 2` after artifact emission post-prerender on Windows. Worker
  thread spawned by some plugin not terminated. Provide minimal repro
  via `WAVE136_HANG_TRACE=1 npm run build` showing handle dump. If upstream
  fixes, kill-after-artifacts workaround can be retired.

- **chrome-devtools-mcp upstream issue** (~1h). File at chromedevtools/
  chrome-devtools-mcp with W135 SW2 + W136 SW3 repro: `Accessibility.
  getFullAXTree` + `Runtime.evaluate` timeout family on Windows + headless
  Chrome with heavy DOM. Closes W136 §Honesty (chrome-devtools wall) at
  upstream level if fix lands. W136 SW3 Playwright workaround stays.

### Tier 4 — Tier 3 housekeeping carry-forward (3 distroless services)

- **file-processor Dockerfile + grpc_health_probe** (~30 min). COPY
  `grpc_health_probe` binary into `services/file-processor/Dockerfile`
  runtime stage. Add compose-level healthcheck.
- **tempo + loki distroless workaround** (~30-60 min). Either package
  with grpc_health_probe (similar to file-processor) OR use sidecar HTTP
  probe container OR document as accepted limitation if upstream offers
  CLI subcommand for health check.

### Tier 5 — Cross-cutting carry-forward (W134/W135/W136)

- Test infrastructure expansion: a11y-public WebKit OOM (W115 SW1
  remainder), mobile-webkit /404 (W116 SW1 remainder).
- LHCI gate ratchet on local baseline (W120 SW2 ratchet last applied;
  W124 SW4 documented variance band).
- a11y deep-audit cross-browser.
- i18n parity consolidation.
- **Per-page visual audit on 8 SSR routes** (~0.5-1 wave per page,
  opportunistic). NOW FEASIBLE via W136 SW3 Playwright + W136 SW1+SW2
  authed flow + W137 Tier 1 ssrAuth.ts fix.
- Storybook/Chromatic activation (requires user-side
  `CHROMATIC_PROJECT_TOKEN` secret + `vars.CHROMATIC_ENABLED=true`).
- **Playwright /login screenshot fragility** (W136 SW3 honest deferral).
  ParticleAuthBackground canvas blocks Playwright stability check;
  sidecar JSON captures diagnostic value. Fix path: VITE_E2E_MODE-style
  flag refactor to disable canvas in test mode (~30 min).

### Tier 6 — Pre-existing carry-forward (NOT closeable without structural change)

- **W134 §Honesty #2 (bundle delta +259 bytes)** — honest framing
  recording. W136 BYTE-IDENTICAL to W135 (139,808 + 65,864). Not a fix
  target.
- **W134 §Honesty #10 (/messenger Phase 5 punted)** — no-deploy
  "production-as-is" decision unchanged. Tier 7 explicit user decision
  to pursue OR punt indefinitely.

### Tier 7 — Optional big scope (explicit user decision)

- **Messenger × 2 polish arc** (~5-7 waves). Per historical anchoring
  (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard ~10):
  messenger has heavy WebSocket + IndexedDB but smaller surface area
  than Map. Pursue OR punt.
- **/admin polish arc** (~3-5 waves). Admin tooling depth audit + UX
  polish. Lower-traffic page. Pursue OR punt.

---

## Pragmatic recommendation (per `feedback_planning_estimates.md` style)

- **Best ROI immediate**: **Tier 1 (ssrAuth.ts reconciliation) + Tier 2
  (real Docker chain authed visual smoke FULL closure)** (~3-4h combined).
  Closes W135 §Honesty #9 fully. Unlocks Tier 5 per-page visual audits
  for future waves. Largest user-facing impact for budget.

- **Best W137 starter combo**: **Tier 1 + Tier 2 + Tier 4 (file-processor
  Dockerfile)** (~4-5h). Drops to ≤4 § Honesty caveats. file-processor
  healthcheck is structural completion of W136 SW7 deferral; small but
  valuable.

- **Closes most § Honesty deferrals**: **Tier 1 + Tier 2 + Tier 3 (upstream
  issue files) + Tier 4 (3 distroless)** (~6-8h). Drops to ≤3 § Honesty
  caveats post-W137.

- **Tier 7 explicit decision**: confirm Messenger/Admin scope OR punt
  before W138+.

### Anti-pattern to avoid (from W136 polish-v2 lesson)

Don't claim closure of W135 §Honesty #9 without verifying the SSR layer.
Polish-v2 surfaced that "real Docker chain authed visual smoke" has TWO
layers — API/gateway (W136 closed) + SSR auth-at-edge (W137 candidate).
The full claim requires BOTH layers working. If W137 picks Tier 1+2,
polish-pass should re-verify both layers post-fix to genuinely close #9.

---

## Anticipated AskUserQuestion 3-question pattern (W133/W134/W135/W136 success)

1. **Q1 — Primary scope tier**: Tier 1+2 (ssrAuth.ts + real Docker smoke
   FULL closure ~3-4h) vs Tier 1+2+3 (+ upstream issue files ~5-6h)
   vs Tier 1+2+3+4 (+ distroless healthchecks ~6-8h) vs Tier 5 cross-
   cutting (+ XL own-wave per-page audit) vs Tier 7 explicit decision
   (Messenger/Admin OR punt).

2. **Q2 — Within chosen tier, sub-scope**: e.g.
   - Tier 1 → ssrAuth.ts fix path (a) backend RS256 in dev (recommended,
     matches prod) vs (b) ssrAuth.ts HS256 fallback (faster but mixes
     dev/prod paths)
   - Tier 2 → smoke depth — 8 SSR routes only OR include `/messenger × 2`
     (still ssr:false but reachable through Caddy)
   - Tier 3 → which upstream first (rolldown vs chrome-devtools-mcp)

3. **Q3 — Architecture/design (if applicable)**:
   - Tier 1+2 → if ssrAuth.ts reconciliation surfaces NEW backend bugs
     (similar to how polish-v2 surfaced .env SECRET_KEY drift), how to
     handle in W137 vs W138?
   - Tier 4 → distroless service strategy: package probes individually OR
     use sidecar pattern OR accept limitation

---

## Read mandatory files in order (per `superpowers:using-superpowers`)

1. **`docs/audits/AUDIT_WAVE136.md`** — full SW0-SW7 narrative + verification
   matrix + § Honesty probe FINAL post-polish-pass (12 caveats: 7 closed
   via implementation+polish; 5 remain) + polish-v1 + polish-v2 sections
   + W137 candidates list at bottom + lessons-learned
2. **`memory/wave136_backlog.md`** — close-status entry-point with file
   references
3. **`memory/wave137_opening_prompt.md`** — this file
4. **`docs/plans/2026-05-07-wave136-tier-1-2-3-design.md`** — W136 design
   doc (architecture diagrams + JWT (d) Hybrid via existing Redis pub/sub +
   build-orchestrated trace flow)
5. **`docs/plans/2026-05-08-wave133-c-plus-d-design.md`** — W133
   architectural decisions + Bridge mechanism context
6. **`docs/plans/2026-05-01-wave125-ssr-design.md`** § Phase 5-6 — original
   SSR design source
7. **`CLAUDE.md`** ## Audit Trail W136 row + 7 new W136 gotchas:
   - JWT is_active claim chokepoint (`b37e827e4`)
   - Backend session revocation broadcast pattern via existing Redis pub/sub
     (`6989637f0`)
   - Playwright real-Chrome as Windows visual-smoke standard (`7bccb5ee7`)
   - failed_login_attempts.user_id model override (`938c797a6`)
   - build-orchestrated mtime regression fix + hang trace agent (`c67ac5cce`)
   - PWA_INJECT_CONFIG single source (`3314364bd`)
   - 3 docker-compose healthcheck additions (`51139c2e7`)
8. **`memory/MEMORY.md`** — auto-loaded; W136 row at top; W133 collapsed to
   one-liner (rotated W136 SW8); W134/W135/W136 verbose in Active backlog;
   W134/W135 audit history rows compacted (verbose detail in Active backlog
   above)
9. **`memory/feedback_perfectionism.md`** — anticipate "безупречно?" probe
   (60-90 min polish budget — W136 used ~75 min across polish-v1 + polish-v2)
10. **`memory/feedback_planning_estimates.md`** — range estimates over single
    numbers; "production-grade polish" anchor 3-5h base + variance

---

## Skills to invoke immediately (per `superpowers:using-superpowers`)

- **`superpowers:brainstorming`** — invoke FIRST per W134/W135/W136 success
  pattern (3-question AskUserQuestion). MANDATORY before any creative work.
  DO NOT skip.
- **`superpowers:writing-plans`** — for plan file creation in plan mode
  after brainstorming
- **`superpowers:systematic-debugging`** — invoke if hitting bugs (W136 SW4
  + SW5 + polish-v2 surfaced REAL bugs via reproduce-first pattern; expect
  more in W137 Tier 1 ssrAuth.ts work)
- **`superpowers:verification-before-completion`** — invoke BEFORE claiming
  SW completion (Iron Law: fresh evidence before claims; W136 polish
  surfaced gaps because verification was implicit)
- **`superpowers:executing-plans`** — invoke AFTER plan approval

---

## Use Context7 MCP (mandatory for library docs)

W137 likely Context7 lookups:
- **`jose` library** (jwtVerify + createRemoteJWKSet) — for ssrAuth.ts HS256
  fallback path OR understanding RS256+JWKS contract
- **`pyjwt` / `python-jose`** — for backend RS256 enablement
- **TanStack Start v1** — `beforeLoad` redirect semantics, `__ssrAuthGetter__`
  contract
- **vitejs/rolldown** — Worker thread lifecycle (for upstream issue file)
- **Playwright API** — cookie injection patterns, `context.addCookies`

Don't trust agent inferences without Context7 verification. W128 polish + W135
SW3 + W136 polish-v2 each surfaced incomplete diagnoses (W128 said programmatic
vite.build was the fix; W135 found prerender doesn't fire that way; W136
polish-v2 found "real Docker chain works after JWT fix" was incomplete because
SSR layer has separate RS256/HS256 issue). Verify all assumptions empirically.

---

## Lessons from W136 (carry-forward for W137+)

1. **Explore agents pre-implementation save scope** — W136 Tier 1 SW1+SW2
   plan estimate was ~3-4h with NATS subject design. Explore revealed gateway
   already has Redis pub/sub revocation infrastructure. Re-scoped to leverage
   existing pattern; actual SW1+SW2 = ~2.5h. Same pattern likely for W137
   Tier 1 — Explore ssrAuth.ts + jose docs + backend JWKS endpoint before
   committing to fix path (a) vs (b).

2. **Test-first reproduces production bugs in CI** — W135 SW2 NotNullViolation
   was framed as "Docker-only schema drift" in initial SW4 docstring. Writing
   the contract test FIRST surfaced that the bug REPRODUCED in test SQLite
   too — real model-level drift, not just Docker. Polish-v2 similarly:
   curl-only verification of API/gateway layer was sufficient to prove W135
   §Honesty #2 closed; Playwright through SSR layer surfaced NEW finding.
   Pattern: **always exercise the actual end-to-end path users hit, not
   just the layer you changed**.

3. **Diagnostic instrumentation surfaces hidden regressions** — W136 SW5
   trace agent identified hang root cause AND surfaced unrelated W135 SW3
   mtime regression (orchestrator triggered on stale leftover artifacts).
   Apply same pattern in W137: when investigating ssrAuth.ts, also inspect
   surrounding code for related layer mismatches.

4. **Single-source config eliminates entire class of drift bugs** — W136 SW6
   `PWA_INJECT_CONFIG` shared module structurally retired W135 §Honesty #5.
   Consider similar single-source patterns for W137 work: e.g. shared SECRET
   loading between backend `env_file` + compose `${SECRET_KEY}` substitution
   (W136 polish-v2 finding — different paths read different files).

5. **Distroless images need Dockerfile-time decision for healthcheck** —
   W136 SW7 surfaced this. W137 Tier 4 must include Dockerfile changes if
   healthcheck is desired; can't add post-hoc to compose.

6. **Playwright real-Chrome bypass for chrome-devtools-mcp wall** — W136 SW3
   established the alternative tool. Real Chrome (`channel: "chrome"`) uses
   different protocol layer than chrome-devtools-mcp's CDP backchannel,
   bypassing the Windows snapshot/eval timeout family. Pattern recipe for
   W137 visual smoke needs.

7. **Empirical findings disprove plan assumptions** — W128 polish round 2
   said programmatic vite.build was the fix; W135 SW3 found prerender doesn't
   fire that way. W136 polish-v2 found gateway HTTP 200 doesn't mean SSR
   redirect-to-/login is fixed. **Plan time-boxes for "structural fix"
   approaches should include 30-90 min budget for empirical diagnostics
   that may invalidate the plan's premise.**

8. **Honest re-scoping mid-implementation is acceptable** — W135 Q3 was
   "Path B full commitment ~3-5h"; empirical findings showed full structural
   fix isn't possible without deeper investigation. Pivoted to kill-after-
   artifacts (improvement, not structural fix) + documented sub-deferral
   in §Honesty. W137 should anticipate similar pivots in Tier 1 ssrAuth.ts
   work — RS256 path may surface RSA key generation complexity.

9. **Discovered out-of-scope issues should be filed as W+1 candidates
   IMMEDIATELY** — W135 SW2 surfaced 2 backend bugs; AUDIT documentation
   happened during SW4. Better pattern: when surfacing an unrelated issue,
   write the W+1 candidate entry at discovery time (~30s) rather than at
   audit time. W136 polish-v2 followed this — `.env` SECRET_KEY drift
   immediately filed as W137 housekeeping candidate.

10. **Memory file dual-location convention** — backlog + opening_prompt
    files live in BOTH USER `.claude` profile dir (auto-load source for
    MEMORY.md relative links) AND REPO `memory/` (git-tracked archive
    across machines). Keep them in sync via `cp` after each edit.

11. **Polish-pass categories** (from `feedback_perfectionism.md`):
    - **Verification gaps**: claimed without running (full vitest, full
      pytest, lint full, build × 3, npm audit, Cargo, i18n, tree-shake,
      commit-stat cross-check, memory link resolution)
    - **Honest framing**: claims that imply success without evidence
    - **Real polish-pass discoveries**: bugs that surface during
      verification (W136 polish-v1 found memory link rot; polish-v2 found
      ssrAuth.ts RS256/HS256 + .env SECRET_KEY drift)

---

## Build × 3 reproducibility discipline (post-W136)

Pattern: run `npm run build` × 3 (now via build-orchestrated.mjs with mtime
fix from W136 SW5 + single-source PWA_INJECT_CONFIG from SW6) AFTER each
wave's final commit (including docs-only commits + polish commits).

- **Code-changing SWs**: hash will differ from baseline (size delta should
  match closure size of new exports + import bookkeeping)
- **Docs-only SWs**: hash MUST match the previous code-changing SW's bundle
  exactly. Different hash = something silently touched the bundle
- **W137 Tier 1 ssrAuth.ts fix**: bundle delta expected (frontend code
  change). Plan should include "new bundle size baseline" recording in
  audit doc; future waves use new size as reference.

Windows: build-orchestrated.mjs handles post-prerender hang via mtime-gated
kill-after-artifacts (W136 SW5). CI Linux: same script via `build-
orchestrated-linux.yml` workflow_dispatch (W136 SW6).

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
   - verify memory link resolution
5. **Re-classify §Honesty caveats**: CLOSED-via-polish vs REMAINING
   (structural / by-design / W137+)
6. **Commit polish pass separately** as `chore(waveNNN-polish)` or
   `chore(waveNNN-polish-vN)` for multi-round polish
7. **Honest answer**: "X of Y caveats closed via polish; Y-X remain as
   structural / by-design / W138+. Specific deferrals: [list]. Real
   'безупречно' requires [structural changes outside this wave's scope]."

W134 polish: ~30 min (1 round). W135 polish: ~15-20 min (1 round). W136
polish: ~75 min total (polish-v1 ~30 min + polish-v2 ~30 min + audit
updates ~15 min; 2 rounds). Scale to wave complexity.

---

## Pre-existing tooling that W137 may use

- **`frontend/scripts/wave136-polish-authed-smoke.mjs`** (NEW polish-v2):
  Playwright authed smoke with API-direct login + cookie injection. Proven
  to work for API/gateway layer; ready for SSR layer testing once Tier 1
  reconciles ssrAuth.ts. Run via `node ./scripts/wave136-polish-authed-smoke.mjs`
  from `frontend/` after Docker stack up.
- **`frontend/scripts/playwright-visual-smoke.mjs`** (W136 SW3): generic
  Playwright visual smoke for non-authed routes (/, /login, /404) with
  best-effort screenshot. Useful for public-route smoke + non-W137 work.
- **`frontend/scripts/wave136-hang-trace-agent.cjs`** (W136 SW5): NODE_OPTIONS
  --require diagnostic agent. Enable via `WAVE136_HANG_TRACE=1 npm run build`.
  Use to repro the hang for upstream issue file (Tier 3).
- **`frontend/scripts/build-orchestrated.mjs`** (W135 SW3 + W136 SW5+SW6):
  the canonical `npm run build` entry point. Mtime-gated kill-after-
  artifacts. Single-source PWA config.
- **`frontend/scripts/lhci-windows-fallback.mjs`** (W120 SW1): LHCI on
  Windows bypassing EPERM. `npm run lhci:windows`.
- **`tests/test_auth_jwt_payload.py`** (W136 SW1, 5 tests): JWT contract
  test pattern; reuse for W137 RS256 contract test if Tier 1 picks (a).
- **`tests/test_user_deactivation_revocation.py`** (W136 SW2, 6 tests):
  session revocation pattern; reuse if Tier 1 SSR-side revocation needed.
- **`tests/test_failed_login_attempts.py`** (W136 SW4, 4 tests): schema
  contract test pattern; reuse if Tier 1 backend changes touch other
  models.

---

## Final pre-flight checklist (run at session start before brainstorming)

```bash
# 1. Working tree clean + 11 commits ahead of W135 close
git status --short && git log --oneline f05836d0d..HEAD | wc -l  # → 11

# 2. Active waves W134/W135/W136 + archive 22 entries
ls docs/audits/AUDIT_WAVE*.md  # → 3 files
ls docs/audits/archive/AUDIT_WAVE*.md | wc -l  # → 22

# 3. MEMORY.md size + memory link resolution
wc -c memory/MEMORY.md  # → < 24,400 bytes
# Memory links: 40/40 resolve (verified post polish-v1)

# 4. Bundle baseline (BYTE-IDENTICAL to W134/W135 — 3-wave invariant)
ls -la frontend/dist/client/assets/index-*.js \
       frontend/dist/client/_shell.html \
       frontend/dist/client/sw.js \
       frontend/dist/server/server.js
# → index-DqqHVXgy.js 139,808 + _shell.html 65,864 + sw.js 53,181 + server.js 39,373

# 5. Cargo.lock idempotent (≥ 26 waves)
git status frontend/rust-crypto/Cargo.lock frontend/wasm-sanitizer/Cargo.lock
# → working tree clean

# 6. (Optional) Verify Docker stack state if planning Tier 1+2 work
docker ps --format "table {{.Names}}\t{{.Status}}" | head -10
# → 19+ containers Up; backend rebuilt during W136 polish-v2 has
# alembic 202605070001 applied
```

---

**Begin**: brainstorming → AskUserQuestion (3 questions: Q1 scope tier,
Q2 sub-scope, Q3 architecture if applicable) → plan file at
`C:\Users\egorribun\.claude\plans\<auto-generated>.md` → ExitPlanMode →
execute under approved plan.

Use TodoWrite for SW progression tracking. Mark chapters via
`mcp ccd_session__mark_chapter` when transitioning between SWs. Invoke
`superpowers:verification-before-completion` BEFORE claiming SW completion
(Iron Law: fresh evidence before claims). Anticipate "безупречно?" probe
post-final-SW — budget ~30-60 min polish (potentially multi-round if W137
goal is broad like Tier 1+2+3+4).

If W137 picks Tier 1 (ssrAuth.ts reconciliation), expect Explore-agent
discovery during brainstorming may reveal that backend RS256 enablement
requires more steps than `JWT_ALGORITHM=RS256` env (e.g. existing
`JWT_SIGNING_KEYS` registry format, JWKS endpoint key publication, kid
rotation interaction). Plan time-box should include ~30-60 min budget
for empirical diagnostics that may pivot the approach.
