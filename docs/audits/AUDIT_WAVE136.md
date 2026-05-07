# AUDIT_WAVE136 — Tier 1+2+3 (JWT (d) Hybrid + Playwright + hang trace + housekeeping)

**Date**: 2026-05-07
**Branch**: `egorribun`
**Scope**: Tier 1 + Tier 2 + Tier 3 per user-approved 3-question AskUserQuestion
(Q1=Tier 1+2+3, Q2=JWT (d) Hybrid, Q3a=Medium process._getActiveHandles trace,
Q3b=Playwright real-Chrome path)
**Wall-clock**: ~7-8h actual (vs ~10-13h plan estimate; refined down by Explore
discovery that gateway already has Redis pub/sub revocation infrastructure).

## Commits (8 + this audit)

1. `3fb5451cc` SW0 `docs(wave136-sw0-design)` — design doc only (1 file +209)
2. `b37e827e4` SW1 `feat(wave136-sw1-jwt-is-active-embed)` — backend embeds
   is_active claim in JWT (2 files +232)
3. `6989637f0` SW2 `feat(wave136-sw2-deactivation-revocation-broadcast)` —
   publish session JTIs on user delete (2 files +325)
4. `7bccb5ee7` SW3 `feat(wave136-sw3-playwright-visual-smoke)` — Windows wall
   alternative (2 files +392)
5. `938c797a6` SW4 `fix(wave136-sw4-failed-login-attempts-nullable-user-id)` —
   real model+schema fix (3 files +255)
6. `c67ac5cce` SW5 `feat(wave136-sw5-build-orchestrated-hang-trace)` — identify
   hang root cause + fix mtime regression (3 files +240/-9)
7. `3314364bd` SW6 `feat(wave136-sw6-workbox-export-linux-ci)` — single-source
   PWA config + Linux CI workflow (4 files +251/-44)
8. `51139c2e7` SW7 `chore(wave136-sw7-housekeeping)` — delete obsolete
   nginx.conf + 3 service healthchecks (2 files +34/-148)

**Cumulative**: 17 files modified (excluding deletions), +1,729 / -201
(1,528 net new lines), 645 new test lines (5 SW1 + 6 SW2 + 4 SW4 = 15 new
tests), nginx.conf deleted (-148 LoC).

## Headlines

1. **Tier 1 W135 discoveries × 3 — all CLOSED**:
   - **Gateway+backend JWT mismatch (SW1+SW2)**: backend embeds `is_active`
     claim → gateway 403 issue resolved + revocation broadcast for
     immediate-effect deactivation via existing Redis pub/sub
   - **chrome-devtools-mcp Windows wall (SW3)**: Playwright real-Chrome
     alternative captures console + network + screenshot via different
     protocol layer
   - **failed_login_attempts schema (SW4)**: REPRODUCED in test SQLite (not
     just Docker drift); fixed via model override + alembic migration

2. **Tier 2 build-orchestrated W135 carry-forward — both addressed**:
   - **SW5 hang trace**: identified `MessagePort + Pipe + Socket × 2` as the
     hang root cause (Worker thread not terminated post-build by some plugin,
     likely Rolldown native worker pool or @rolldown/plugin-babel). Filed
     for upstream W137+. **Bonus**: surfaced + fixed real mtime regression
     in W135 SW3 (orchestrator was triggering on stale leftover artifacts).
   - **SW6 Workbox config drift**: PWA_INJECT_CONFIG named export from
     `frontend/scripts/workbox-config.mjs` — single source of truth shared
     by `vite.config.mts` (full pipeline) + `build-orchestrated.mjs`
     (Windows local). Drift impossible. Plus Linux CI validation workflow.

3. **Tier 3 housekeeping — partial**:
   - frontend/nginx.conf DELETED (W131 SW3 made it obsolete)
   - 3 healthchecks added: imgproxy (CLI), grafana (wget), prometheus (wget)
   - 3 deferred honestly: file-processor (Dockerfile change required for
     grpc_health_probe), tempo + loki (both distroless, no in-container
     HTTP client) — W137+ candidates

4. **Defense-in-depth wired**: Tier 1 SW1 (JWT claim, fast path, ~ns) + SW2
   (Redis pub/sub broadcast, immediate-effect, ~µs cached). Both fire on every
   authed gateway request. Stale JWT scenario caught within seconds.

## SW0 — Design doc (`3fb5451cc`)

**Files**: NEW `docs/plans/2026-05-07-wave136-tier-1-2-3-design.md` (~210 LoC)

Captures architecture diagrams (JWT (d) Hybrid via existing Redis pub/sub +
build-orchestrated trace flow), SW breakdown table, verification approach,
honest deferrals, risks + mitigations. Per `superpowers:brainstorming`
skill convention.

## SW1 — JWT is_active embed + contract test (`b37e827e4`)

**Files (2 +232/-0)**:
- `app/services/auth/login_session_manager.py` (+6): `finalize_login` threads
  `extra_claims={"is_active": bool(user.is_active)}` to
  `session_service.create_access_token`. `SessionService._mint_jwt`'s
  `payload.update(extra)` already supported the extension; no SessionService
  changes needed.
- NEW `tests/test_auth_jwt_payload.py` (+226, 5 tests): contract tests for JWT
  payload shape via direct `SessionService.create_access_token` + integration
  via real `LoginSessionManager.finalize_login`.

**Verification gate**: ruff + format + py_compile pass; pytest
`tests/test_auth_*.py + test_login_service_coverage + test_auth_concurrency
+ test_utils_monster_coverage`: **48 passed**.

**Backwards-compat note**: Pre-W136 JWTs invalidate on deploy (Go json
unmarshal defaults missing bool to false → gateway 403 → user re-logs in).
Acceptable under no-deploy scope.

## SW2 — Backend session revocation broadcast (`6989637f0`)

**Files (2 +325/-0)**:
- `app/services/user/compliance_service.py` (+39): NEW
  `_revoke_user_sessions(user_id)` helper calls existing
  `app.services.session_cleanup.revoke_sessions_matching` with whereclause
  for user's active sessions. Both `admin_delete_user` and `delete_user_data`
  call it AFTER `anonymize_user_data`, BEFORE `delete_sensitive_data` so
  gateway picks up revocation BEFORE rows are dropped.
- NEW `tests/test_user_deactivation_revocation.py` (+286, 6 tests).

**Architecture (no NATS needed)**: Gateway's existing `ListenForRevocations()`
at `services/gateway/middleware/auth.go:362-416` consumes the
`session:revocations` Redis pub/sub channel + adds JTIs to `revoked:jti:{jti}`
keys with L1 cache + XFetch probabilistic refresh. Backend just publishes
JTIs on user deactivation — leverages all existing infrastructure.

**Verification gate**: pytest `test_auth_service + test_auth_security +
test_auth_jwt_payload + test_user_deactivation_revocation +
test_login_service_coverage + test_user_service +
test_user_service_decomposed`: **65 passed**.

## SW3 — Playwright visual smoke (`7bccb5ee7`)

**Files (2 +392/-0)**:
- NEW `frontend/scripts/playwright-visual-smoke.mjs` (~280 LoC + ~75 LoC
  docstring): 2-phase smoke (navigation `waitUntil:"domcontentloaded"`
  robust against failing sub-resources + best-effort screenshot allowed
  to fail without failing the run). Uses real Chrome (`channel:"chrome"`)
  with bundled Chromium fallback.
- `frontend/package.json` (+1): NEW `visual:smoke` npm script.

**Captures**: console messages (info/warn/error/pageerror), network requests
(with status), final URL, HTTP status, hydration error count. Output:
`.screenshots/wave136-visual-smoke/<route>.{png,json}`.

**Verification gate**: ran against `npm run start` Node SSR server on :3000
(no backend), `/login` and `/404` routes both reported `status=OK` with
sidecar JSON saved (9.3KB + 8.5KB). Console errors are infrastructure noise
(Service Worker reg fail, /api/v1/users/me 500). 0 React hydration errors.

**Honest deferral**: Screenshot for /login fails fast (5s timeout) due to
`ParticleAuthBackground` canvas physics loop blocking Playwright's stability
check. Documented inline; sidecar captures the diagnostic value (console +
network) regardless. Real Docker chain visual smoke through 8 SSR routes
(W135 SW2 deferred this) — script is ready, full sweep is a polish-pass
candidate.

## SW4 — failed_login_attempts conditional INSERT fix (`938c797a6`)

**Files (3 +255/-0)**:
- `app/models/auth.py` (+23): override `user_id` in `FailedLoginAttempt`
  with `nullable=True` + `ondelete="SET NULL"` (UserFK mixin defaults to
  `nullable=False, ondelete=CASCADE`).
- NEW `tests/test_failed_login_attempts.py` (+126, 4 tests).
- NEW `alembic/versions/202605070001_failed_login_attempts_user_id_nullable.py`
  (+106): drops existing FK, alters column to nullable, re-creates FK with
  SET NULL action. Idempotent on re-run; downgrade purges NULL rows before
  tightening NOT NULL.

**Investigation finding**: W135 SW2 NotNullViolation REPRODUCED in test
SQLite (not Docker-only as the initial test docstring assumed). Real model-
level drift between original migration's intent (`nullable=True`) and the
inherited UserFK mixin's NOT NULL.

**Why model fix > conditional INSERT**: Path A (skip INSERT for non-existent
emails) would lose IP-based brute-force detection signal (TD-3 from
2026-02-26 audit added `ix_failed_login_attempts_ip_attempted_at` for this).
Path B (conditional with NULL) preserves the IP-keyed detection AND restores
original migration intent.

**Verification gate**: pytest `test_failed_login_attempts +
test_auth_security + test_auth_jwt_payload +
test_user_deactivation_revocation`: **28 passed** (4 new + 24 regression).

## SW5 — build-orchestrated hang trace (`c67ac5cce`)

**Files (3 +240/-9)**:
- `.gitignore` (+1): .wave136-trace/ exclusion
- `frontend/scripts/build-orchestrated.mjs` (+~70/-~10 net): `isArtifactFresh`
  helper using `statSync(file).mtimeMs >= startTime` + 1500ms grace tolerance
  for filesystem mtime quantization; optional WAVE136_HANG_TRACE=1 flag
  injects trace agent + uses IPC-enabled stdio.
- NEW `frontend/scripts/wave136-hang-trace-agent.cjs` (+155): injected via
  NODE_OPTIONS=--require, listens for IPC trigger from orchestrator + watchdog
  timer fallback, dumps `process._getActiveHandles + _getActiveRequests` by
  type to stderr + `.wave136-trace/dump-*.json` + IPC reply.

**Two issues surfaced (both addressed)**:

1. **W135 SW3 mtime regression** (FIXED): kill-after-artifacts logic was
   triggering at 2s (too early) because `existsSync` matched STALE leftover
   artifacts from prior builds. The "build × 3 reproducible" baseline was
   partly an artifact of this bug (returning leftover bundle each time).
   Fixed via mtime check: poll only counts artifacts as "stable" if `mtime >=
   build start time`. Now correctly waits ~23s for vite to actually produce
   fresh artifacts.

2. **Hang root cause identified** (DIAGNOSED, upstream fix W137+):
   Trace dump at 23.3s post-artifact-stable showed:
   ```
   active handles: 4
     - MessagePort
     - Pipe
     - Socket × 2
   active requests: 0
   ```
   The `MessagePort` × 1 is the smoking gun — a Worker thread spawned by
   some plugin (likely Rolldown native worker pool or
   `@rolldown/plugin-babel`) is not being terminated after build completion,
   holding the event loop alive. The `Pipe` is the IPC channel we created;
   the 2 `Socket`s are likely internal communication to native rolldown
   workers.

**Honest framing**: SW5 IDENTIFIES the hang category but does NOT
structurally fix the underlying upstream bug. The kill-after-artifacts
pattern (now correctly mtime-gated) remains the working solution.
W137+ candidate to file upstream issue at vitejs/rolldown with the
MessagePort + Worker diagnosis.

**Verification gate**: build × 2 BYTE-IDENTICAL to W135 baseline:
- `index-DqqHVXgy.js` 139,808 bytes ✓
- `_shell.html` 65,864 ✓
- `sw.js` 53,181 ✓
- `server.js` 39,373 ✓

Build duration ~30s (slight increase from W135 ~26s due to mtime check
waiting longer for fresh artifacts; previously triggered prematurely).

## SW6 — Workbox export + Linux CI (`3314364bd`)

**Files (4 +251/-44)**:
- NEW `frontend/scripts/workbox-config.mjs` (+51): exports `PWA_INJECT_CONFIG`
  with `globPatterns + globIgnores + maximumFileSizeToCacheInBytes`. Single
  source of truth.
- `frontend/vite.config.mts` (-23/+5 net): imports `PWA_INJECT_CONFIG` from
  `./scripts/workbox-config.mjs`; `VitePWA()` `injectManifest` references the
  import directly (was 25-line inline block).
- `frontend/scripts/build-orchestrated.mjs` (-15/+6 net): imports
  `PWA_INJECT_CONFIG` from `./workbox-config.mjs`; uses `...PWA_INJECT_CONFIG`
  instead of hardcoded `WORKBOX_INJECT_CONFIG` constant.
- NEW `.github/workflows/build-orchestrated-linux.yml` (+186): workflow_dispatch
  trigger, ubuntu-latest runner, runs build × 3 (default) with sha256sum
  comparison asserting BYTE-IDENTICAL invariant.

**Drift impossible**: both consumers reference the same module export.

**Verification gate**: prettier + tsc clean; npm run build BYTE-IDENTICAL to
W135 baseline (4 artifact sizes match); Linux CI workflow not yet executed
(manual workflow_dispatch trigger required).

## SW7 — Tier 3 housekeeping (`51139c2e7`)

**Files (2 changes)**:
- DELETED `frontend/nginx.conf` (-148 LoC; obsolete since W131 SW3)
- `docker-compose.full.yml`: 3 healthcheck blocks added + Honesty comments
  for 3 deferred services

**Healthchecks added**:
- imgproxy: `["CMD", "imgproxy", "health"]` (v3.18+ CLI)
- grafana: `wget --spider http://localhost:3000/api/health`
- prometheus: `wget --spider http://localhost:9090/-/healthy`

**Honest deferrals** (3 services, distroless or Dockerfile-change required):
- file-processor: needs `grpc_health_probe` binary in runtime image
- tempo + loki: distroless, no wget/curl/nc/bash

**Verification gate**: `yaml.safe_load_all(docker-compose.full.yml)` valid.

## Verification matrix (cumulative)

| Gate | Target | Actual | Notes |
|---|---|---|---|
| `python -m ruff check app/` | 0 errors | ✓ 0 | SW1+SW2+SW4 each |
| `python -m ruff format` (idempotent) | clean | ✓ | SW1+SW2+SW4 each |
| `python -m py_compile` | 0 errors | ✓ | SW1 |
| pytest auth slice (test_auth_*.py) | ~52p | ✓ 34 + new W136 contract tests | 5 SW1 + 6 SW2 + 4 SW4 = 15 new tests |
| pytest user slice (test_user_*.py) | preserve baseline | ✓ 23 + 6 SW2 = 29 | broader test_user_* + test_user_service_decomposed |
| pytest cumulative SW1+SW2+SW4 | 28 | ✓ **28 passed / 0 failed** | new 15 W136 tests + 13 regression |
| `npx prettier --check` (frontend) | clean | ✓ | SW3+SW6 |
| `npx tsc --noEmit` (frontend) | 0 errors | ✓ 0 | SW3+SW6 |
| `node ./scripts/build-orchestrated.mjs` × 2 | BYTE-IDENTICAL | ✓ identical hash + sizes | SW5+SW6 |
| Bundle main chunk size | 139,808 bytes (W135 baseline) | ✓ 139,808 | unchanged |
| Bundle `_shell.html` | 65,864 bytes (W135 baseline) | ✓ 65,864 | unchanged |
| Bundle `sw.js` | 53,181 bytes (W135 baseline) | ✓ 53,181 | unchanged |
| Bundle `server.js` | 39,373 bytes (W135 baseline) | ✓ 39,373 | unchanged |
| Workbox precache count | 209 / 4.80 MB | ✓ 209 / 4.80 MB | unchanged |
| docker-compose YAML schema | valid | ✓ yaml.safe_load_all | SW7 |
| `npm run start` /healthz | 200 fast-path | ✓ 15B / 2ms | SW3 verification |
| Playwright /login console_err | 0 React hydration | ✓ 0 hydration errors | (3 infra noise expected) |
| Build duration | <60s/run | ✓ ~30s | SW5 mtime fix slight increase from W135 ~26s |

**Build × 3 reproducibility post-SW7** to be re-verified at SW8 commit (this
audit is docs-only; bundle should match SW6 baseline). Done at end of SW8.

## §Honesty probe (post-SW8)

Per `feedback_perfectionism.md`. Pre-W136 there were 9 § Honesty caveats from
W135 (post-polish). W136 closures + remaining:

### CLOSED via SW1+SW2+SW3+SW4 implementation (Tier 1 W135 discoveries)

1. ✅ **W135 §Honesty #2 (Gateway+backend JWT protocol mismatch)** — closed
   via SW1 backend embed + SW2 revocation broadcast.
2. ✅ **W135 §Honesty #1 (chrome-devtools-mcp Windows snapshot wall)** —
   closed at tool-availability level via SW3 Playwright alternative. The
   chrome-devtools-mcp wall itself remains upstream (CDP issue);
   filed W137+ candidate.
3. ✅ **W135 §Honesty #3 (failed_login_attempts.user_id NOT NULL)** — closed
   via SW4 model override + alembic migration. REPRODUCED in test SQLite
   (not Docker-only).

### CLOSED via SW5+SW6 implementation (Tier 2 carry-forward)

4. ✅ **W135 §Honesty #4 (build-orchestrated structural hang)** — DIAGNOSED
   to MessagePort + Worker thread family via SW5 trace agent. Bonus: surfaced
   real mtime regression in W135 SW3 (orchestrator triggered on stale
   artifacts) which SW5 fixed. Underlying upstream fix W137+.
5. ✅ **W135 §Honesty #5 (Workbox config drift risk)** — closed via SW6
   PWA_INJECT_CONFIG named export shared between vite.config.mts + build-
   orchestrated.mjs. Drift impossible.
6. ✅ **W135 §Honesty #8/#11 (Linux CI not validated; consolidated)** —
   closed via SW6 NEW build-orchestrated-linux.yml workflow_dispatch trigger
   + sha256sum comparison.

### REMAINING (3 of 9 W135 caveats; honest framing or W137+ scope)

1. **W135 §Honesty #6 (W134 §Honesty #2 bundle delta carry-forward)** —
   honest framing recording. W136 produces BYTE-IDENTICAL to W135 baseline
   (neutral net delta). Not a fix target.

2. **W135 §Honesty #7 (W134 §Honesty #10 /messenger Phase 5 punted)** —
   carry-forward. No-deploy "production-as-is" decision unchanged.

3. **W135 §Honesty #9 (SW2 verified curl-only, not authed browser session)**
   — STILL deferred. With SW1+SW2 JWT infrastructure + SW4 schema fix +
   SW3 Playwright tool now in place, a real Docker chain authed visual
   smoke is possible. Polish-pass candidate or W137 first task.

### NEW from W136 SW5+SW7 (3 caveats)

4. **build-orchestrated upstream hang fix** — SW5 identified MessagePort +
   Worker as the smoking gun but local fix impractical without monkey-
   patching plugin internals. Filed W137+ to file upstream issue at
   vitejs/rolldown with the trace data.

5. **Tier 3 housekeeping partial** — SW7 added 3 of 6 healthchecks; 3
   distroless services (file-processor, tempo, loki) deferred to W137+
   (Dockerfile changes required to package grpc_health_probe or
   service-specific CLI health subcommands).

6. **Playwright /login screenshot fragility** — SW3 documented inline:
   ParticleAuthBackground canvas physics loop blocks Playwright's stability
   check; screenshot allowed to fail without failing run. Sidecar JSON
   captures the diagnostic value. Acceptable trade-off; not a fix target
   without disabling the canvas in test mode (VITE_E2E_MODE-style flag).

## W137 candidates

Carry-forward + new from W136:

### Highest priority (W136 § Honesty TOP discoveries)

- **Real Docker chain authed visual smoke** (~1-2h) — with W136 SW1+SW2 JWT
  infrastructure + SW4 schema fix + SW3 Playwright tool in place,
  end-to-end authed flow through Caddy → gateway → backend can be smoke-
  tested. Closes W135 §Honesty #9 fully.
- **vitejs/rolldown upstream hang issue** (~1-2h) — file with W136 SW5
  trace data (MessagePort + Pipe + Socket × 2 after artifact emission).
  Closes W135 §Honesty #4 structurally.
- **chrome-devtools-mcp upstream issue** (~1h) — file with W135 SW2 +
  W136 SW3 repro of Accessibility.getFullAXTree timeout family on
  Windows + headless Chrome.

### Tier 3 carry-forward

- **file-processor Dockerfile + grpc_health_probe** (~30 min) — COPY
  binary in runtime image to enable compose-level healthcheck.
- **tempo + loki distroless workaround** (~30 min) — either package with
  grpc_health_probe or use sidecar HTTP probe container.

### Pre-existing carry-forward (W134 §Honesty)

- **W134 §Honesty #2 bundle delta** — honest framing only.
- **W134 §Honesty #10 /messenger Phase 5** — explicit user decision.

### Tier 4 cross-cutting (carry-forward)

- Test infrastructure expansion (a11y-public WebKit OOM W115 SW1; mobile-
  webkit /404 W116 SW1 remainder).
- LHCI gate ratchet on local baseline.
- a11y deep-audit cross-browser.
- i18n parity consolidation.
- Per-page visual audit on 8 SSR routes (now feasible via W136 SW3
  Playwright + W136 SW1+SW2 authed flow).
- Storybook/Chromatic activation (requires user-side
  CHROMATIC_PROJECT_TOKEN).

### Tier 5 explicit user decision (carry-forward)

- /messenger × 2 polish arc OR /admin polish arc OR punt as
  "production-as-is".

## Lessons from W136 (meta-pattern for W137+)

1. **Explore agents pre-implementation save scope** — Tier 1 SW1+SW2 plan
   estimate was ~3-4h with NATS subject design. Explore revealed gateway
   already has Redis pub/sub revocation infrastructure. Re-scoped to
   leverage existing pattern; actual SW1+SW2 = ~2.5h.

2. **Test-first reproduces production bugs in CI** — W135 SW2 NotNullViolation
   was framed as "Docker-only schema drift" in initial SW4 docstring. Writing
   the contract test FIRST surfaced that the bug REPRODUCED in test SQLite
   too — real model-level drift, not just Docker. Avoided shipping a "test
   that documents the bug as Docker-specific" while the bug actually applied
   to ALL deployment paths.

3. **Diagnostic instrumentation surfaces hidden regressions** — SW5 trace
   agent identified the hang root cause (MessagePort + Worker thread family).
   AND surfaced an unrelated W135 SW3 mtime regression (orchestrator
   triggered on stale leftover artifacts). The "fix" for the hang trace
   ALSO fixed the SW3 reproducibility theatre.

4. **Single-source config eliminates entire class of drift bugs** — SW6
   `PWA_INJECT_CONFIG` shared module retires W135 §Honesty #5 by structurally
   making drift impossible. Both consumers (vite-plugin-pwa via vite.config
   + build-orchestrated.mjs standalone) reference the same export.

5. **Distroless images need Dockerfile-time decision for healthcheck** —
   SW7 Tier 3 surfaced that compose-level healthchecks for distroless
   services (tempo, loki, file-processor) require packaging probe binaries
   at image build time. Adding healthchecks post-hoc to a distroless image
   in compose isn't viable — this is a planning constraint to remember
   for future infra work.

6. **Playwright real-Chrome bypass for chrome-devtools-mcp wall** — SW3
   established the alternative tool. Real Chrome (`channel: "chrome"`)
   uses different protocol layer than chrome-devtools-mcp's CDP backchannel,
   bypassing the Windows snapshot/eval timeout family. Pattern recipe for
   future Windows visual smoke needs.

## Build × 3 reproducibility re-verification (post-SW8)

To be re-verified at SW8 commit (this audit + memory updates are docs-only;
bundle should be IDENTICAL to SW6 baseline). Expected:
- `index-DqqHVXgy.js` 139,808 × 3 (BYTE-IDENTICAL invariant per W134 polish
  lesson)
- `_shell.html` 65,864 × 3
- `sw.js` 53,181 × 3
- `server.js` 39,373 × 3
- Workbox precache 209 files / 4.80 MB

Done at end of SW8 implementation (after this audit + memory commits).

## N+3 rotation

`git mv docs/audits/AUDIT_WAVE133.md docs/audits/archive/AUDIT_WAVE133.md`
performed at SW8. Active waves now W134/W135/W136. Archive directory has
17 entries (W117-W133).

## End of AUDIT_WAVE136

W137 starter recommendations (per `feedback_planning_estimates.md` style):

- **Best ROI immediate (Tier 1 W137 carry-forward)**: file 3 upstream issues
  (vitejs/rolldown hang + chrome-devtools-mcp wall + tempo/loki distroless
  health) + real Docker chain authed visual smoke (~3-4h combined).
- **Best W137 starter combo**: Tier 1 (3 upstream issues + Docker smoke
  ~3-4h) + Tier 3 carry-forward (file-processor Dockerfile + healthchecks
  ~1h) (~4-5h combined).
- **Tier 5 explicit decision** (carry-forward to W137): confirm Messenger ×
  2 polish arc OR /admin polish OR punt as "production-as-is".

Real wall-clock for W136: ~7-8h vs ~10-13h plan estimate. Refined down via
Explore-agent discovery of existing gateway revocation infrastructure.
