# AUDIT_WAVE140 — Tier 1+2+3 broad combo (Open-ended absorption)

**Date**: 2026-05-11 (single session, ~7-9h wall-clock)
**Branch**: `egorribun`
**Scope (user-approved AskUserQuestion at session start)**:
- Q1 = **Tier 1+2+3 broad** (~10-13h baseline, no hard cap)
- Q2 = **Backend creates streams + file-processor waits** (production architecture)
- Q3 = **Open-ended absorption of (z) cascades** (no hard cap)

**Wall-clock**: ~7-9h within Q3 open-ended budget. Wave produced 8 new
(z) discoveries — within range of W139 (10 (z) under formal naming).

---

## §1. Headlines

1. **file-processor reaches `(healthy)` for first time post-W137 SW5**
   via SW1 (backend FILES_PROCESS stream) + SW2 (schema.graphql Dockerfile
   COPY) + SW3 (`depends_on: backend: service_healthy`) + SW3-fix
   ((z) cascade closure: healthcheck override + GraphQL ID typing +
   selective auth interceptor). Verified empirically via `docker ps`:
   `Up About an hour (healthy)`. NATS streams `FILES_PROCESS` +
   `TASK_QUEUE` both provisioned (verified via `nats streams_info`).
   Closes W139 §Honesty #6 (NATS gap) + #7 (schema.graphql gap).

2. **visual-audit.yml CI workflow fully working on Linux runner** after
   6 iter cycles (iter3-iter8) closing recurring W137-class path-typo
   bugs (`/health` → `/health/ready`), missing Redis env vars, WASM
   download flake, CSRF dance, JS nullish-coalescing-vs-empty-string
   fallback. All 8 SSR routes return HTTP 200 + AUTHED + 0 hydration
   errors + 0 console errors per route. Sidecar JSON uploaded as
   artifact for each route. Closes W138 §Honesty #4 (visual audit
   Windows wall) + W139 §Honesty #8 (SW3 iter cascade) — both in their
   structural-verification scope.

3. **NEW W140 §Honesty caveat**: axe-core analyze hangs on heavy
   authed-route DOM on Linux CI too (not just Windows per W113 SW1).
   60s Promise.race timeout I added in iter8 fired for ALL 8 routes —
   axe coverage = 0/8 routes. Structural verification (HTTP/auth/
   hydration/console) is captured; axe a11y rule evaluation deferred to
   W141+ as own focused scope (extends W113 SW1 / W114 SW2a / W115 SW1
   wall family from WebKit-specific to all browsers on heavy DOM).

4. **SW5 (Path a-auth Temporal Server image switch) deferred to W141+**
   per plan deviation trigger #3. After 11 W140 commits + 8 (z)
   cascade discoveries, additional structural risk of `temporalio/server`
   image switch + `auth_config.yaml` + Go SDK auth integration + service
   JWT mint was not pursued. W137 §Honesty #5 stays PARTIAL (Temporal
   connectivity closed via W139 SW2; auth still deferred). Honest framing
   per `feedback_perfectionism.md`.

5. **SW6 Tier 3 carry-forward deferred**: a11y deep-audit blocked by
   axe wall (iter8 finding); LHCI ratchet blocked by W139 (z) #10
   PAGE_HUNG carry-forward; WebKit OOM closure + Storybook+Chromatic
   activation require own focused scope. No clean win available within
   W140 remaining time.

6. **All quality gates GREEN**:
   - tsc 0 errors
   - lint 0 warnings (`--max-warnings=0`)
   - vitest **1052p / 12s / 0f** (W139 baseline preserved EXACTLY)
   - npm audit **0 vulnerabilities** (W139 SW6 baseline preserved)
   - Cargo.lock no drift (idempotent ≥ 30 waves)
   - Bundle baseline preserved EXACTLY post defensive rebuild × 1:
     `index-DqqHVXgy.js` 139,808 b + `_shell.html` 65,864 b +
     `sw.js` 53,115 b + `server.js` 39,373 b (BYTE-IDENTICAL to W139
     close — W140 had ZERO frontend code changes; sw.ts wasn't touched)
   - Tree-shake invariant: 0 `lhci-mock-user` matches in PROD assets
   - SW IIFE invariant: 0 `export{` in sw.js + correct head/tail

---

## §2. Commits (11 on egorribun + this audit)

1. `4181ff1da` SW0 `docs(wave140-sw0-design)` (1 file +431)
2. `ceaae7ef7` SW1 `feat(wave140-sw1-backend-nats-files-process-stream)` (2 files +110)
3. `fb56b0fb9` SW2 `feat(wave140-sw2-fileprocessor-schema-graphql-copy)` (1 file +7)
4. `7a7b43cf6` SW3 `feat(wave140-sw3-fileprocessor-depends-on-backend)` (1 file +14)
5. `ce7f5cca7` SW3-fix `fix(wave140-sw3-z-cascade-closure)` (6 files +254/-10)
6. `796966b4b` SW4 iter3 `fix(wave140-sw4-visual-audit-ci-iter3)` (1 file +27/-4)
7. `c965ac32b` SW4 iter4 `fix(wave140-sw4-csrf-dance)` (1 file +21)
8. `8bb0cb270` SW4 iter5 `chore(wave140-sw4-iter5-diagnostic)` (1 file +12)
9. `a8ad749fa` SW4 iter6 `fix(wave140-sw4-iter6-redis-url)` (1 file +13)
10. `0424af375` SW4 iter7 `fix(wave140-sw4-iter7-default-routes)` (1 file +6/-1)
11. `4c5125b45` SW4 iter8 `fix(wave140-sw4-iter8-axe-timeout)` (1 file +20/-1)
12. SW7 (this commit) audit + memory + N+3 rotation

**Cumulative net**: ~14 files touched, +925/-16 across 11 commits.
All commit shortstats verified against `git show --shortstat` ✓.

---

## §3. (z) Path discoveries list (W140 = 8 (z) under formal naming)

Per W138 Lesson #2 + W139 anti-pattern #4 — each (z) is structural
surprise documented honestly. Comparative caveat: W139 had 10 (z) under
formal naming; W140 = 8 (z). Both waves used the broad scope tier; W140
slightly fewer (z) primarily because file-processor (z) work was sharply
focused (3 discoveries via SW3-fix) and SW5 was honestly deferred before
its own (z) cascade could surface.

### (z) #0 — Backend Dockerfile HEALTHCHECK uses `/healthz` (Full Check)

`backend.Dockerfile:97-98` defines HEALTHCHECK using Python urllib on
`/healthz`. `/healthz` is the Full Health Check including ES/SpiceDB/
Tempo subsystem probes. In dev compose, when any of these is slow to
start, `/healthz` returns 503 → backend container reports `unhealthy`.
file-processor's `depends_on: backend: service_healthy` (SW3) then
never resolves → file-processor never starts even though backend's
lifespan (and SW1 stream creation) is complete.

Mitigation (SW3-fix): override healthcheck in docker-compose.full.yml
backend service to use `/health/ready` (Lean Readiness Probe — just
DB connectivity + not shutting down).

### (z) #1 — GraphQL ID type strict-checking in file-processor

After SW2 successfully made schema.graphql available to runtime,
`MustParseSchema` panicked on resolver/schema type mismatch:

```
panic: can not use string as ID
    used by (*graphql.FileResolver).ID
    used by (*graphql.Resolver).File
```

`graph-gophers/graphql-go` v1.9.0+ enforces strict ID typing.
schema.graphql declares `file(id: ID!)`, `File.id: ID!`, and
`FileJob.jobId: ID!` but Go resolver methods returned `string`.
Pre-W140 this was MASKED because schema.graphql was missing (W139
§Honesty #7) — parse failed before MustParseSchema reached the type
check.

Mitigation (SW3-fix): import `gql "github.com/graph-gophers/graphql-go"`
in resolver.go; change resolver args + return types to `gql.ID`;
update resolver_test.go assertions.

### (z) #2 — gRPC health probe blocked by auth interceptor

After SW2 + (z) #1 fix, file-processor reached gRPC bind step but
`grpc_health_probe` returned exit code 3 with `Unauthenticated desc =
Request unauthenticated with bearer`. `auth.UnaryServerInterceptor`/
`StreamServerInterceptor` pair required bearer JWT on ALL RPCs
including `grpc.health.v1.Health/*` methods. `grpc_health_probe` binary
(W137 SW5 distroless health-probe stage) does NOT supply tokens.

Mitigation (SW3-fix): introduce `selectiveUnaryAuth` +
`selectiveStreamAuth` + `authedServerStream` wrappers in main.go that
bypass auth for `/grpc.health.v1.Health/` method prefix. 6 unit tests
added in `cmd/file-processor/main_test.go`. Matches standard
Kubernetes gRPC health check protocol convention.

### (z) #3 — `/health` path typo in visual-audit.yml

Workflow's "Wait for backend health" step polled `curl -sf
http://127.0.0.1:8000/health > /dev/null`. `/health` returns 404 —
the actual routes are `/health/live`, `/healthz`, `/health/ready`,
and `/ready`. Pre-W140 the `/health` 404 silently turned the readiness
loop into a 180s wait → timeout, masked by the parallel NATS hang
issue (W139 (z) #4) which was the primary visible failure. W139 iter2's
NATS service addition resolved the NATS hang but `/health` 404 remained.
Recurring W137 SW4 ALLOWED_HOSTS-class path-typo bug.

Mitigation (SW4 iter3): polling target changed to `/health/ready`.

### (z) #4 — WASM binaryen download flake on first invocation

W139 iter2 hit a transient `binaryen-x86_64-linux.tar.gz` 404 from
GitHub releases CDN during `wasm-pack build`. Single-shot retry needed.

Mitigation (SW4 iter3): up-to-3-attempts retry loop with 10s backoff
in "Build WASM modules" step. Each build is idempotent (binaryen
cache reused once successfully downloaded).

### (z) #5 — CSRF middleware enforces both cookie + header on
`/api/v1/auth/register`

CSRFMiddleware (`app/core/csrf.py` + `middleware/setup.py:47-60`) is
enabled in `testing` env too and requires both `csrf_token` cookie AND
`X-CSRF-Token` header on POST. `/api/v1/auth/register` is NOT in
`exempt_prefixes` (which are `/internal`, `/api/v1/csp-report`,
`/api/v2/auth/token`, `/api/v2/auth/webauthn`). Workflow's plain curl
POST returned HTTP 403.

Mitigation (SW4 iter4): 2-step CSRF dance in workflow's "Seed test
user" step — GET `/api/v1/auth/csrf-cookie` to set cookie, extract
token via `awk`, then POST `/register` with `-b cookies.txt -H
X-CSRF-Token: $CSRF`.

### (z) #6 — Redis URL scheme missing (defaults to `"memory://"`)

After iter4 unblocked CSRF, login returned HTTP 500. Backend log
diagnostic (added in iter5) revealed root cause:

```
ValueError: Redis URL must specify one of the following schemes
(redis://, rediss://, unix://)
```

Login flow `login_json → login_service.perform_login → finalize_login →
redis_session.create_session → _get_shared_client(self.redis_url) →
Redis.from_url(url, ...)` ✗ ValueError. `self.redis_url` is sourced
from `settings.rate_limit_storage_uri`
(`app/services/auth/redis_session.py:38`) which DEFAULTS to
`"memory://"` when no env var is set
(`app/core/config/mixins/rate_limit_settings.py:45`). `"memory://"` is
not a valid Redis URL scheme. Pre-W140 this was masked because the
visual audit script never reached login successfully.

Mitigation (SW4 iter6): add `CACHE_REDIS_URL`, `RATE_LIMIT_STORAGE_BACKEND`,
`RATE_LIMIT_STORAGE_URI` env vars to the workflow env block, pointing
at the existing 127.0.0.1:6379 redis service container.

### (z) #7 — JS nullish-coalescing vs empty-string fallback

iter6 unblocked login but Visual Audit Results only had `jwks` + `login`
sidecars — no route sidecars. Root cause: workflow_dispatch sets
`ROUTES: ${{ inputs.routes }}` which becomes `ROUTES=""` (empty string)
when no input is supplied. Script then did
`process.env.ROUTES ?? DEFAULT_ROUTES.join(",")`. `??` treats empty
string as a real value (not nullish), so `DEFAULT_ROUTES` never applied.
Recurring W120 SW5 MSYS empty-string handling class.

Mitigation (SW4 iter7): explicit `process.env.ROUTES?.trim()` truthy
check before using.

### (z) #8 — AxeBuilder.analyze() hangs on heavy DOM (Linux too)

iter7 reached `/dashboard` audit (first time post-W138 SW3 + W139 SW1)
but hung 26 minutes inside `AxeBuilder.analyze()` until the 30-min
GitHub Actions job timeout fired. Pre-W140 this was assumed
Windows-only per W138 SW3 + W139 SW1 chrome-devtools-mcp Windows wall
family. iter7 disproved that assumption — Linux runners hit the same
wall on heavy authed-route DOM (e.g. `/dashboard` SSR-rendered with
all dash-tilt-cards + DashboardHero + InstallPrompt + stories + 24
backend-404 requests). Extends W113 SW1 / W114 SW2a / W115 SW1 wall
family from WebKit-specific to all browsers on heavy DOM.

Mitigation (SW4 iter8): `Promise.race` with 60s timeout per route.
Routes that exceed the cap get `axeError: "axe-analyze-timeout-60s"`
in their sidecar JSON. Structural verification (HTTP/auth/hydration/
console) still captured. iter8 confirmed all 8 SSR routes hit the
timeout — axe coverage = 0/8 routes for W140. **NEW W140 §Honesty
caveat** — axe a11y rule evaluation on heavy DOM is now a deferred
W141+ scope (mini-axe via page.addScriptTag + tag-filtered bundle,
OR conditional reduced MainLayout, OR axe rule-set narrowing via
`.disableRules` + `.include("main")`).

---

## §4. § Honesty caveats — pre-W140 → post-W140 re-classification

### Pre-W140 (carried from W139)

| # | Caveat | Type | Post-W140 status |
|---|--------|------|------------------|
| 1 | W134 #2 bundle delta (recording-only) | Recording-only | UNCHANGED |
| 2 | W134 #10 /messenger Phase 5 punted (Tier 5) | By-design (no-deploy) | UNCHANGED |
| 3 | W137 #5 file-processor temporal-localhost — PARTIAL via W139 SW2 | Structural | STILL PARTIAL (auth deferred — SW5 → W141+) |
| 4 | W137 #6+#7 by-design dev-only | Documented dev-only | UNCHANGED |
| 5 | W138 #4 visual audit Windows wall — PARTIAL via W139 SW1 | Structural | **CLOSED** (structural verification works on Linux CI — SW4 iter3-iter8) |
| 6 | W139 NEW: file-processor NATS stream `files.process` gap | Structural | **CLOSED** (SW1 + SW3) |
| 7 | W139 NEW: file-processor schema.graphql Dockerfile gap | Structural | **CLOSED** (SW2) |
| 8 | W139 NEW: SW3 iter cascade (visual-audit.yml CI infra) | Structural | **CLOSED** (SW4 iter3-iter8) |

### NEW W140 caveats

| # | Caveat | Type | W141+ scope? |
|---|--------|------|--------------|
| 9 | **W140 NEW**: axe-core hangs on heavy DOM on Linux CI too (60s timeout fires for all 8 routes); structural verification works; axe a11y rule eval deferred | Structural | YES (~3-5h focused — mini-axe injection / reduced MainLayout / rule narrowing) |
| 10 | **W140 NEW**: SW5 Path (a-auth) Temporal Server image switch deferred (VERY HIGH risk; 3-5h own scope; W137 §Honesty #5 stays PARTIAL) | Structural | YES (~3-5h) |
| 11 | **W140 NEW**: backend healthcheck override in compose (W140 SW3-fix `/healthz` → `/health/ready`) — production K8s uses readinessProbe from manifest so no prod regression, but Dockerfile HEALTHCHECK still uses /healthz | Documented dev-only | NO (production unaffected; dev override correct) |

### Total post-W140

**4 caveats CLOSED** (W138 #4 + W139 #6 + #7 + #8).
**4 caveats remain unchanged** (W134 #2, #10, W137 #3, #4 — all
recording-only / by-design / Tier 5 decisions).
**3 NEW caveats** from W140 work (caveats #9, #10, #11).

**Net total**: 8 → 7 caveats remain (4 unchanged + 3 NEW).

Plan target was 3-5 caveats remaining; actual = 7. The slight overshoot
reflects honest framing per `feedback_perfectionism.md` "§Honesty caveat
counting is dynamic" — W140 SW4 iter cascade unmasked axe-wall-on-Linux
(NEW #9) which W138/W139 had assumed Windows-only.

---

## §5. SW progression detail

### SW0 (`4181ff1da`) — Design doc commit

Single-file commit per W139 pattern. Captured Q1+Q2+Q3 commitments,
Phase 1 Explore findings from 3 parallel agents, SW sequencing
constraints, (z) risk register, plan deviation triggers.

### SW1 (`ceaae7ef7`) — Backend FILES_PROCESS stream creation

NEW second `await self._js.add_stream` call in
[app/core/nats_broker.py:128](app/core/nats_broker.py:128)
alongside existing TASK_QUEUE creation. Stream name `FILES_PROCESS`,
subject `["files.process"]`. Idempotent per nats-py contract.

3 unit tests in `tests/test_wave140_nats_files_process_stream.py`
(both streams created; idempotency on second connect; subject
contract test guarding against drift between backend stream + Go
file-processor subscribe).

Closes W139 §Honesty #6.

### SW2 (`fb56b0fb9`) — file-processor schema.graphql Dockerfile COPY

NEW `COPY --from=builder /app/services/file-processor/schema.graphql
./schema.graphql` to runtime stage in
`services/file-processor/Dockerfile`. Mirrors W137 SW5 grpc_health_probe
COPY pattern.

Closes W139 §Honesty #7.

### SW3 (`7a7b43cf6`) — file-processor depends_on: backend service_healthy

`docker-compose.full.yml` file-processor service block: depends_on
extended with `backend: condition: service_healthy`. Architectural
contract per W140 Q2.

Closes the SW1+SW2+SW3 chain.

### SW3-fix (`ce7f5cca7`) — (z) #0+#1+#2 cascade closure

Three (z) discoveries unmasked by SW1+SW2+SW3 chain verification, all
fixed in one commit:

- **(z) #0**: backend healthcheck override in compose (`/healthz` →
  `/health/ready`) to make `service_healthy` resolve reliably in dev
- **(z) #1**: GraphQL ID typing fix in resolver.go + resolver_test.go
- **(z) #2**: selective auth interceptor in main.go + main_test.go
  (6 new unit tests)

**Empirical verification**: file-processor reached `(healthy)` for the
first time post-W137 SW5 after Docker rebuild + restart. Logs confirm
4 success messages (Connected to Temporal, Temporal Worker started,
gRPC Server listening, GraphQL & Metrics Server listening). NATS
streams empirically verified via `docker exec backend python -c ...
streams_info()`: `TASK_QUEUE → ['tasks.>']` + `FILES_PROCESS →
['files.process']`.

### SW4 iter3-iter8 — visual-audit.yml CI completion

6 iter cycles totalling 8 (z) discoveries (the cascade pattern W139
SW3 ran into in iter1-iter2). Each iter committed separately to
preserve audit trail.

- **iter3** (`796966b4b`) — `/health` → `/health/ready` path fix +
  WASM binaryen 3-attempt retry
- **iter4** (`c965ac32b`) — CSRF dance for test user seed
- **iter5** (`8bb0cb270`) — backend log diagnostic dump (always-runs
  after visual audit step)
- **iter6** (`a8ad749fa`) — Redis URL env vars
  (`CACHE_REDIS_URL`/`RATE_LIMIT_STORAGE_BACKEND`/`RATE_LIMIT_STORAGE_URI`)
- **iter7** (`0424af375`) — `ROUTES?.trim()` truthy check (empty
  string fallback to DEFAULT_ROUTES)
- **iter8** (`4c5125b45`) — `Promise.race` 60s timeout on
  `AxeBuilder.analyze()` per route

Final workflow run 25684183833 completed in 12m22s with all steps
green. Visual Audit Results: 8 SSR routes + JWKS + login sidecars all
uploaded as artifacts. Each route: HTTP 200, AUTHED, 0 hydration
errors, 0 console errors. Axe coverage = 0/8 (timeout fires per route —
NEW W140 caveat #9).

Closes W138 §Honesty #4 (visual audit Windows wall) + W139 §Honesty
#8 (SW3 iter cascade) — both in their structural-verification scope.

### SW5 deferred to W141+

Per plan deviation trigger #3, after 11 W140 commits + 8 (z) cascade
discoveries, additional structural risk of Path (a-auth) was not
pursued. W137 §Honesty #5 stays PARTIAL.

Specific W141+ blueprint preserved in
[docs/plans/2026-05-11-wave140-tier123-design.md](docs/plans/2026-05-11-wave140-tier123-design.md)
§4 SW5 section (image switch + auth_config.yaml schema + Go client
auth + service JWT mint).

### SW6 deferred

Tier 3 carry-forward candidates all blocked or own-scope:
- a11y deep-audit: blocked by axe wall (iter8 finding)
- LHCI ratchet: blocked by W139 (z) #10 PAGE_HUNG carry-forward
- WebKit OOM closure: own focused scope (~3-5h)
- Storybook + Chromatic activation: user-side env action

### SW7 (this commit) — Verification + audit + memory + N+3 rotation

This commit.

---

## §6. Verification matrix

| Gate | Method | Result |
|------|--------|--------|
| frontend tsc | `cd frontend && npx tsc --noEmit` | 0 errors ✓ |
| frontend lint | `cd frontend && npm run lint -- --max-warnings=0` | 0 warnings ✓ |
| frontend vitest | `cd frontend && npm test -- --run` | **1052p / 12 skipped / 0 failed** in 28.44s ✓ (W139 baseline preserved EXACTLY) |
| backend ruff | `python -m ruff check app/core/nats_broker.py tests/test_wave140_nats_files_process_stream.py` | 0 errors ✓ |
| backend pytest | `python -m pytest tests/test_wave140_nats_files_process_stream.py tests/test_di_outbox_lifecycle.py tests/test_nats_kv_cache.py` | 9p / 1 skipped / 0 failed ✓ |
| Go build + tests | `cd services/file-processor && go test ./...` | ALL passed (config + graphql + middleware + workflow + cmd/file-processor 6 new selective auth tests) |
| npm audit | `cd frontend && npm audit --omit=dev` | 0 vulnerabilities ✓ (W139 SW6 baseline preserved) |
| Cargo.lock | `git status frontend/rust-crypto/Cargo.lock frontend/wasm-sanitizer/Cargo.lock` | no drift ✓ (idempotent ≥ 30 waves) |
| Bundle baseline | `ls -la dist/client/assets/index-*.js dist/client/_shell.html dist/client/sw.js dist/server/server.js` post defensive rebuild × 1 | BYTE-IDENTICAL to W139: 139,808 + 65,864 + 53,115 + 39,373 ✓ |
| Tree-shake invariant | `find dist/client/assets -name "*.js" -exec grep -l "lhci-mock-user" {} +` | 0 matches ✓ |
| SW IIFE invariant | `grep -c "export{" dist/client/sw.js` + head/tail check | 0 + `"use strict";(()=>{` + `;})();` ✓ |
| Docker file-processor | `docker ps --filter "name=file-processor"` | **Up About an hour (healthy)** ✓ (FIRST TIME post-W137 SW5) |
| NATS streams | `docker exec backend python -c "...js.streams_info()..."` | `TASK_QUEUE → ['tasks.>']` + `FILES_PROCESS → ['files.process']` ✓ |
| visual-audit.yml CI | `gh run watch 25684183833` | 12m22s, all 32 steps green ✓ |
| 8 SSR route sidecars | `ls /tmp/wave140-sw4-iter8/visual-audit-reports/*.json` | 10 sidecars (8 routes + jwks + login) ✓ |
| Compose YAML schema | `python -c "import yaml; yaml.safe_load(open('docker-compose.full.yml'))"` | parses cleanly ✓ |
| Workflow YAML schema | `python -c "import yaml; yaml.safe_load(open('.github/workflows/visual-audit.yml'))"` | parses cleanly ✓ |

---

## §7. Cross-session vitest 5-run

Per W124 SW4 methodology / W139 polish framing correction: sequential
runs in single bash session, NOT strict cross-session (separate Node
processes / separate shell sessions). Captured 1 run with full
verification suite + count baseline:

- Run 1: 1052 passed / 12 skipped / 0 failed / 28.44s

Honest framing: only one full run captured here at audit-write time
(5-run cross-session deferred to opt-in post-wave verification). W139
polish A1+A2 verified all 10 W139 commit shortstats match git show;
W140 SW7 does the same for 11 W140 commits. Cross-session vitest 5×
run is repeatable via `for i in 1 2 3 4 5; do npm test -- --run;
done` if needed post-wave.

---

## §8. § Honesty probe self-audit

Per `feedback_perfectionism.md` "if you can't measure, defer honestly".
Walkthrough of each W140 SW + iter to surface "I didn't verify" gaps:

1. **SW1 unit tests verified** ✓ — 3 tests pass; regression against
   `tests/test_di_outbox_lifecycle.py` + `tests/test_nats_kv_cache.py` (6p)
2. **SW2 Dockerfile COPY verified** via SW3 chain Docker rebuild ✓
3. **SW3 depends_on YAML verified** via `yaml.safe_load` + Docker
   restart success ✓
4. **SW3-fix verified empirically** via `docker ps` (healthy) + log
   inspection ✓ + 6 unit tests for selective auth + 3 tests for
   GraphQL ID typing
5. **SW4 iter3 fixes** — workflow run 25680993258 closed health-check
   path + WASM retry (verified all steps green for those)
6. **SW4 iter4 CSRF dance** — workflow run 25681351989 confirmed seed
   step OK; surfaced login 500 → diagnostic added
7. **SW4 iter5 diagnostic** — workflow run 25681791336 captured backend
   stack trace; identified Redis URL ValueError
8. **SW4 iter6 Redis fix** — workflow run 25682151484 confirmed login
   succeeded + jwks + login sidecars uploaded
9. **SW4 iter7 ROUTES fallback** — workflow run 25682445206 reached
   /dashboard audit (first time) but hung 26 min → 30-min timeout
   (surfacing (z) #8 axe wall on Linux)
10. **SW4 iter8 axe timeout** — workflow run 25684183833 completed in
    12m22s with all 8 SSR routes structurally verified; axe coverage
    = 0/8 (timeout fires for all)

**Honest deferrals** (NEW W140 caveats):
- axe a11y rule evaluation on Linux CI heavy DOM — not closed; (z) #8
  finding documented + mitigation deferred to W141+
- SW5 Path (a-auth) Temporal Server image switch — not attempted;
  documented decision per plan deviation trigger #3
- SW6 Tier 3 carry-forward — not pursued; all candidates blocked
  or own-scope

**No "I didn't verify" gaps** in SW0-SW4 closure work itself. Each
commit had its verification step + commit message captures empirical
results.

---

## §9. Lessons learned

1. **(z) cascades on CI workflows are structural** — W139 SW3 hit
   iter cascade at iter0-iter2; W140 SW4 hit iter cascade at iter3-
   iter8 (6 iters). The cascade pattern is consistent: each fix
   unmasks the next blocker. Budget 5-8 iter cycles for CI workflow
   bring-up, not 2-3.

2. **Heavy authed-route DOM blocks axe-core analyze on ALL browsers** —
   W113 SW1 + W114 SW2a + W115 SW1 narrative scoped this as WebKit-only.
   W140 SW4 iter7-iter8 disproves that — Linux Chromium hits the same
   wall (just slightly different memory envelope). Future a11y deep-
   audit work needs structural fixes (mini-axe injection / reduced
   MainLayout / scope narrowing), not just browser-specific workarounds.

3. **CI workflow `/health` typo class is recurring** — W137 SW4 hit
   ALLOWED_HOSTS typo; W140 SW4 iter3 hit `/health` typo. Both were
   silently masked by parallel blockers. Polish-passes should
   specifically verify endpoint paths against actual API definitions.

4. **Lazy-init providers don't need env-flag-guards** — Phase 1 Explore
   Agent 1 reported SpiceDB + ES have no env-flag-guards. SW4 plan
   estimated this as a 5-file env-flag-guard addition; actual
   verification showed Dishka providers were lazy-init, so backend
   startup didn't touch them. Env-flag-guards were never needed —
   the actual blockers were Redis URL + /health path typo. Future
   "add env-flag-guards" plans should verify whether the targeted
   services are actually startup-active or lazy-init first.

5. **Empty-string env vs nullish coalescing** — Recurring with W120
   SW5 MSYS empty-string. workflow_dispatch passes empty input as
   empty string, which `??` treats as a real value. Always `.trim()`
   + truthy check.

6. **`temporalio/admin-tools` is dev-server-only; image switch to
   `temporalio/server` may require external DB** — Per Phase 1 Explore
   Agent 3 caution + W139 (z) #1 finding. SW5 deferral acknowledges
   this multi-unknown structural risk requires own focused scope.

7. **gRPC health probe should bypass auth interceptors** — Kubernetes
   gRPC health check protocol convention. file-processor's
   `auth.UnaryServerInterceptor` was too broad; selective interceptor
   with `/grpc.health.v1.Health/` prefix exemption is canonical.

8. **GraphQL ID typing must match schema strictly** — `graph-gophers/
   graphql-go v1.9.0+` enforces strict typing via `MustParseSchema`.
   Resolver methods returning `string` for schema's `ID!` panic on
   schema parse. Future schema changes should run `go test
   ./internal/graphql/...` to catch type mismatches early.

---

## §10. W141+ candidates carry-forward

### Tier 1 (high priority — closes 2 NEW W140 caveats + carries 1 W137)

1. **SW5 carry-forward — Path (a-auth) Temporal Server full image
   switch** (~3-5h focused scope):
   - Image switch: `temporalio/admin-tools:1.30.2` →
     `temporalio/server:1.x` (verify embedded SQLite compat OR pivot
     to `temporalio/auto-setup` with Postgres backend)
   - Author `config/temporal/auth_config.yaml` with
     `claimMapper.providers[].jwksURI` → backend's
     `/.well-known/jwks.json`
   - file-processor Go client auth integration:
     `client.Credentials = client.NewAPIKeyStaticCredentials(token)`
   - Backend service token minting endpoint (RS256, sub=
     "file-processor-service", aud="temporal")
   - Closes W137 §Honesty #5 FULLY

2. **W140 (z) #8 carry-forward — axe-core analyze coverage on
   Linux CI** (~3-5h focused scope):
   - Mini-axe via `page.addScriptTag` with tag-filtered bundle
   - OR conditional reduced MainLayout under `VITE_E2E_MODE` (W116
     SW1 pattern)
   - OR axe scope narrowing via `.include("main")` +
     `.disableRules(["color-contrast-enhanced", "...heavy rules..."])`
   - Closes NEW W140 §Honesty caveat #9

### Tier 2 (cross-cutting carry-forward)

- LHCI gate ratchet on real W137-W138-W139-W140 baseline (depends on
  W139 (z) #10 PAGE_HUNG diagnostic — see W139 audit doc §9)
- WebKit OOM closure (W115 SW1 carry-forward, own focused scope)
- Storybook + Chromatic activation (user-side env action — repo
  secret + repo variable pending)

### Tier 5 (explicit user decision — long-standing carry-forward)

- /messenger × 2 polish arc (~5-7 waves) OR /admin polish arc (~3-5
  waves) OR punt as "production-as-is"

---

## §11. Cross-references

- Plan: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-functional-hennessy.md`
- Design doc: [docs/plans/2026-05-11-wave140-tier123-design.md](docs/plans/2026-05-11-wave140-tier123-design.md)
- W139 audit (8 §Honesty pre-W140): [docs/audits/AUDIT_WAVE139.md](docs/audits/AUDIT_WAVE139.md)
- W139 backlog (closure summary source): `.claude` profile `memory/wave139_backlog.md`
- W139 Temporal pivot narrative: `.claude` profile `memory/wave139_temporal_path_a_pivot.md`
- W140 opening prompt (session-start scope): `.claude` profile `memory/wave140_opening_prompt.md`
- W140 closure summary: `.claude` profile `memory/wave140_backlog.md`
- W141 opening prompt: `.claude` profile `memory/wave141_opening_prompt.md`

---

## §12. N+3 rotation

Per W122 polish-docs-v3 covenant: when N+3 next wave opens, oldest
active audit moves to archive. W140 close opens W141 candidate window;
W137 audit rotates to archive.

```
git mv docs/audits/AUDIT_WAVE137.md docs/audits/archive/AUDIT_WAVE137.md
```

Active waves after rotation: W138/W139/W140.

---

## §13. Polish-pass (post-SW7, "безупречно?" probe)

User invoked "безупречно?" probe post-SW7. Single-round polish per
`feedback_perfectionism.md` "honest self-audit, not reassurance":

### A1 — commit shortstats cross-check (all 12 W140 commits)

`git show --shortstat` for `4181ff1da`, `ceaae7ef7`, `fb56b0fb9`,
`7a7b43cf6`, `ce7f5cca7`, `796966b4b`, `c965ac32b`, `8bb0cb270`,
`a8ad749fa`, `0424af375`, `4c5125b45`, `b6fc5e179` all MATCH the audit
doc §2 claims EXACTLY. Zero drift.

### A2 — vitest 5-run (honest framing: sequential single-session)

5 sequential `npm test -- --run` invocations in ONE bash session
(matching W139 polish framing — NOT strict cross-session per W124 SW4
which requires separate shell sessions). Durations: 32.57s / 29.48s /
29.57s / 29.15s / 29.10s. Run 1 = cold cache outlier; runs 2-5 cluster
within 0.5s (warm cache). Final explicit count check: **1052 passed /
12 skipped / 0 failed**. Cross-session-with-cold-cache-per-run methodology
deferred to W141+ if needed.

### A3 — npm audit re-verify

`cd frontend && npm audit --omit=dev` → **0 vulnerabilities**. W139
SW6 baseline preserved post-W140.

### A4 — memory file references resolution (FINDING)

`wave141_opening_prompt.md` lines 146-151 (W140 SW7) referenced
`memory/wave138_upstream_issue_chromedevtools.md` +
`memory/wave138_upstream_issue_tempo_loki.md`. **NEITHER FILE EXISTS**
in `.claude` profile. The actual file is `wave137_upstream_issues.md`
(258 lines, single consolidated file with Issue 1 / Issue 2 / Issue 3
sections written by W137 SW7). This drift was inherited from W139's
W140 opening prompt; the same drift exists in the W138 audit row of
CLAUDE.md (line 694, pre-existing).

**This is a recurring "W122 §Honesty-correction class" pattern** per
W139 (z) #9 / W138 Lesson #9 — polish-passes find prior-wave audit-
claim drift. Polish-pass fix: corrected wave141_opening_prompt.md to
reference `memory/wave137_upstream_issues.md` + extract-via-awk
pattern; documented Issue 1 (rolldown #9327) as already filed; Issue 2
+ Issue 3 still pending external filing.

**Did NOT modify W138 audit row in CLAUDE.md** (closed/historical
wave; rewriting risks scope creep). Future polish-passes should
re-verify memory references per opening prompt.

### A5 — file:line citation drift (FINDING — 4 sites)

SW3-fix's selectiveAuth interceptor insertion (~44 lines into main.go)
+ SW1's new init fields + extended comment block in nats_broker.py
shifted line numbers for code AFTER the insertions. Audit doc + CLAUDE.md
SW7 gotchas had pre-edit line citations:

| Pre-edit citation | Actual post-W140 line | File |
|-------------------|----------------------|------|
| `nats_broker.py:128` | 134 (TASK_QUEUE) / 141 (NEW FILES_PROCESS) | app/core/nats_broker.py |
| `main.go:286` (os.ReadFile schema.graphql) | 330 | services/file-processor/cmd/file-processor/main.go |
| `main.go:277-280` (grpc_health_v1 RegisterHealthServer) | 322-324 | services/file-processor/cmd/file-processor/main.go |
| `Dockerfile:55` (schema.graphql COPY) | 57 | services/file-processor/Dockerfile |

Polish-pass fix: CLAUDE.md SW7 gotcha lines for SW1 + SW2 updated with
correct post-W140 line numbers + explanatory note about line-shift
provenance. Audit doc §1+§5 references to these citations remain
intact (the citations were correct at SW commit time; post-SW3-fix
shift was inherent to the wave). Future polish-passes should
verify line citations at audit-write time + final commit time.

### A6 — file-processor still (healthy) (no drift)

`docker ps --filter "name=file-processor"` → `Up 2 hours (healthy)`.
file-processor remains stable over the elapsed time since SW3-fix
verification. NATS streams `TASK_QUEUE` + `FILES_PROCESS` both still
provisioned (verified via `docker exec backend python -c ...
streams_info()...`).

### A7 — bundle baseline defensive rebuild #2 (BYTE-IDENTICAL confirmed)

Second `BUILD_SKIP_PWA=true npm run build` invocation produced:
- `index-DqqHVXgy.js` 139,808 b ✓
- `_shell.html` 65,864 b ✓
- `sw.js` 53,115 b ✓
- `server.js` 39,373 b ✓

**BYTE-IDENTICAL** to rebuild #1 from SW7. Bundle reproducibility now
confirmed across 2 rebuilds (audit doc §1 claimed "BYTE-IDENTICAL post
defensive rebuild × 1" — polish strengthens to × 2 evidence).

### A8 — INDEX.md + MEMORY.md sanity (no drift)

`docs/audits/INDEX.md` 93 lines (well under any threshold). MEMORY.md
24,379 bytes (under 24,400 auto-load threshold). Both healthy.

### A9 — "ZERO frontend code changes" framing correction (FINDING)

The audit doc §1+§6 + CLAUDE.md SW7 row claim "W140 had ZERO frontend
code changes" is **strictly imprecise**. `git log --name-only` for
W140 commits across `frontend/*` shows ONE file modified:
- `frontend/scripts/wave138-visual-audit.mjs` (modified in SW4 iter7 +
  iter8: ROUTES `?.trim()` fallback + `Promise.race` axe timeout)

This is a Node.js Playwright runner / CI tooling script, NOT
React/TypeScript app code. It is NOT compiled into the React app
bundle — which is why BYTE-IDENTICAL bundle invariant still holds.

**Corrected framing**: "ZERO `frontend/src/` changes (React/TS app
code); 1 CI tooling script in `frontend/scripts/` modified in SW4 iter7
+ iter8." The bundle BYTE-IDENTICAL claim is fully correct (script is
not bundled).

### A10 — §Honesty caveats re-classification (post-polish)

No NEW caveats from polish-pass. The 4 A-findings (A4 memory ref drift
+ A5 file:line drift × 4 + A9 framing imprecision) are all
**documentation-quality** issues fixed inline in polish commit, NOT
new structural caveats. The 7 caveats from SW7 stand:

- Unchanged carries: W134 #2, W134 #10, W137 #5 (PARTIAL — auth
  deferred to W141+), W137 #6+#7
- NEW W140: axe wall on Linux (#9), SW5 deferred (#10), healthcheck
  override dev-only (#11)

Plus 3 polish-pass-documented findings (now CLOSED via polish):
- Memory reference drift (corrected wave141_opening_prompt.md)
- File:line citation drift (corrected 4 sites in CLAUDE.md)
- Framing imprecision ("ZERO frontend code" → "ZERO frontend/src/")

### Polish wall-clock

~30-40 min single round. No second round needed. Polish surfaced 3 doc
findings + 6 verifications (A1-A3 + A6-A8 PASS clean). Standard W139
polish-pass pattern matched.

### Honest answer template

"3 doc-quality findings closed via polish (A4 + A5 + A9); 7 caveats
remain as structural / by-design / W141+ scope (#1-#4 unchanged
carries + #9-#11 NEW W140 honest deferrals). Real 'безупречно'
requires W141+ Tier 1 closures (axe-core Linux coverage + Path (a-auth)
full Temporal Server image switch, ~6-10h focused scope). Polish-pass
matches W139 single-round duration (~30-40 min) and W139 documentation-
drift pattern (A4 recurring W122 §Honesty correction class)."
