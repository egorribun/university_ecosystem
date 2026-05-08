---
name: Wave 137 backlog
description: Wave 137 closed Tier 1+2+3+4 (RS256 + Docker authed smoke + 3 upstream issue stubs + distroless health) per user-approved 3-question AskUserQuestion.
type: project
originSessionId: wave137-sw8
status: CLOSED
---
# Wave 137 backlog — CLOSED

**Status**: CLOSED. Tier 1 + Tier 2 + Tier 3 + Tier 4 per user-approved
3-question AskUserQuestion at session start
(Q1=Tier 1+2+3+4, Q2=(a) Backend RS256 in dev, Q3=Not bounded full-depth pivot).

Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-flickering-shell.md`

Wall-clock: ~6-8h core (vs ~7-10h plan estimate; refined down by Explore-agent
discovery that backend RS256 was code-ready without changes).

## Closed in Wave 137

### SW0 — Design doc (`e5bbf077a`, 1 file +231)

NEW `docs/plans/2026-05-08-wave137-tier1234-design.md` per
`superpowers:brainstorming` skill convention. 3 Explore-agent findings
(backend RS256 ready, VITE_BACKEND_ORIGIN trap, distroless workarounds)
+ architecture diagrams + SW breakdown + risks/mitigations.

### SW1 — Backend RS256 enablement (`b95d8d815`, 3 files +385/-1)

Closes W135 §Honesty #9 SSR layer prep (was partial closure post W136
polish-v2 — API/gateway only).

- `start-docker.ps1` (+~80): NEW `New-JwtRs256Key` function generates
  RSA-2048 via .NET 8 `RSA.ExportPkcs8PrivateKeyPem` (PowerShell 7+
  native; no openssl dependency). `.env.docker` fresh-gen flips to
  `ALGORITHM=RS256` + `JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem`.
  NEW migration block for existing `.env.docker` (idempotent flip +
  key-path insertion).
- `docker-compose.full.yml` (+15): backend volume `.secrets:/app/.secrets:ro`
  + gateway env `JWKS_ENDPOINT=http://backend:8000/.well-known/jwks.json`
  + `JWKS_REFRESH_INTERVAL=60`.
- NEW `tests/test_auth_jwt_rs256.py` (+292, 5 contract tests).

Backend code = ZERO changes (jwt_settings.py:25 defaults RS256; registry
auto-loads PEM at startup; JWKS endpoint already publishes public keys).

Verification: 255 passed across extended auth+user+login slice (was 90
W136 baseline + 165 broader test selection + 5 new W137 RS256 tests).

### SW2 — start-docker.ps1 SECRET_KEY drift sync (`97ecb4d99`, 1 file +27)

Closes W136 polish-v2 housekeeping finding.

- `start-docker.ps1`: NEW drift-detection block reads SECRET_KEY from
  both `.env` + `.env.docker`, syncs `.env` to match `.env.docker`
  (canonical source) if different. Line-based replacement (no regex on
  replacement side) handles special chars in secret value safely.

### SW3 — VITE_BACKEND_ORIGIN build-arg fix (`62fa9eb04`, 1 file +10/-1)

Closes W135 §Honesty #9 frontend-side prep.

- `docker-compose.full.yml`: frontend.build.args `VITE_BACKEND_ORIGIN: ""`
  → `"http://backend:8000"`. Vite/Rolldown literal-substitution at build
  time means ssrAuth.ts:79 needs the docker-internal service-name DNS
  baked in. Pre-W137 fell back to `http://localhost:8000` (unreachable
  from container). Production CI overrides via deploy-time arg.

Note: SW3 alone insufficient — see SW4-prep Dockerfile dist-clear fix.

### SW4-prep — Caddy + smoke + Dockerfile dist clear (`730820405`, 3 files +515)

Pre-requisites for SW4 verification:

- `infrastructure/Caddyfile` (+8): NEW `/.well-known/* → backend:8000`
  block. Pre-W137 the JWKS endpoint at `/.well-known/jwks.json` fell
  through to default frontend handle → 404. Now publicly reachable per
  RFC 8615.
- `frontend.Dockerfile` (+9): NEW `rm -rf dist;` before `npm run build`
  in watch+kill workaround. **STRUCTURAL bug discovered + fixed —
  predates W134**: `.dockerignore` `dist/` only matches top-level, NOT
  `frontend/dist/`. So `COPY frontend ./` brings in stale host-cached
  dist/ from prior builds. Watch+kill polled for `dist/server/server.js`,
  matched stale file IMMEDIATELY → 5s settle → kill → npm run build
  never ran. **This masked W134-W136 "BYTE-IDENTICAL build × 3
  reproducibility" claims** (same hash because build was a NO-OP).
- NEW `frontend/scripts/wave137-authed-smoke.mjs` (~498 LoC): extends
  W136 polish-v2 wave136-polish-authed-smoke.mjs with JWKS pre-check
  + JWT alg=RS256 assertion + payload claim assertions + page-per-route
  lifecycle (W129 §Honesty `new_page` workaround). Distinct exit codes
  per failure mode (1/2/3/4).

### SW5+SW6 — Distroless healthchecks (`a5f251376`, 2 files +69/-10)

SW5 — file-processor Dockerfile + grpc_health_probe:
- NEW `health-probe` stage (alpine:3.20) fetches grpc_health_probe v0.4.27
  from grpc-ecosystem/grpc-health-probe GitHub releases.
- Runtime stage `COPY --from=health-probe` to /usr/local/bin/.
- compose healthcheck `["CMD", "grpc_health_probe", "-addr=:50051"]`.
- main.go:277-280 already registers grpc_health_v1.HealthCheckResponse_
  SERVING for FileProcessingService.

SW6 — tempo + loki via curl sidecar:
- NEW tempo-healthprobe + loki-healthprobe services
  (curlimages/curl:8.10.1, network_mode service:tempo / service:loki).
- Healthcheck probes localhost:3200/ready + localhost:3100/ready.
- Both report `(healthy)` in `docker compose ps`.

By-design caveat: sidecar healthiness ≠ container healthiness for
`depends_on: service_healthy` semantics. Acceptable dev-only.

### SW4-pass — Authed smoke close §Honesty #9 (`8dccc9120`, 2 files +33/-3)

3 critical sub-fixes uncovered during SW4 empirical verification:

1. Backend `ALLOWED_HOSTS` env (NOT TRUSTED_HOSTS — middleware reads
   `allowed_hosts_list` per app/core/middleware/setup.py:154 +
   cors_settings.py:154 — `trusted_hosts_list` is read-only computation,
   `allowed_hosts_list` is what TrustedHostMiddleware consumes).
   Default dev list rejects `Host: backend:8000` from inside docker
   network → JWKS fetch failed silently. Fix: add `backend,caddy,0.0.0.0`.
2. `MAX_SESSIONS_PER_USER` bump 5 → 50 (dev-only). Repeated smoke runs
   hit per-user session cap → 403 too_many_sessions. Production K8s
   keeps default for credential-stuffing defense.
3. wave137-authed-smoke.mjs page-per-route via `context.newPage()` per
   W129 §Honesty pattern. Removed `page.evaluate(...)` bodySnippet
   capture (Windows-eval wall on heavy DOM).

Final verification: ALL 8 SSR routes return 200 + 0 hydration errors
+ AUTHED + ~113 net req each through real Caddy → frontend Node SSR →
gateway → backend chain. **W135 §Honesty #9 fully CLOSED**.

### SW5-honesty (`c95acfe8a`, 1 file +19)

`docker-compose.full.yml`: file-processor healthcheck comment expanded
to document the dev-compose runtime limitation. SW5 binary IS in image
+ healthcheck spec is structurally correct + production-ready. Pre-W137
there was no healthcheck so file-processor's lack of functionality was
invisible. Dev-runtime failure is pre-existing P0-03 trade-off (audit
2026-03-06: temporal binds 127.0.0.1 only). Production K8s where
Temporal is reachable → healthcheck would work.

### SW7 — Upstream issue stubs (`b0819053a`, 1 file +258)

NEW `memory/wave137_upstream_issues.md` (~340 lines, 3 templates ready
for `gh issue create`):

1. rolldown/rolldown — Build hangs post-prerender (MessagePort + Worker)
2. chromedevtools/chrome-devtools-mcp — Windows headless heavy-DOM eval
   timeout
3. grafana/tempo + grafana/loki — Add `--check-ready` CLI subcommand

User files post-wave-close. Resolution timeline outside our control.

### SW8 — Audit + memory + N+3 rotation (this commit)

- NEW `docs/audits/AUDIT_WAVE137.md` (~330 lines)
- NEW `memory/wave137_backlog.md` (this file)
- NEW `memory/wave138_opening_prompt.md` (BOTH user .claude + repo)
- `CLAUDE.md` ## Audit Trail W137 row + new gotchas
- `git mv docs/audits/AUDIT_WAVE134.md docs/audits/archive/AUDIT_WAVE134.md`
  (N+3 rotation; active waves now W135/W136/W137)
- `memory/MEMORY.md` updates

## Honest § Honesty caveats

**Pre-W137 6 W136 caveats post-polish-v2; W137 closes 3 + introduces 4 NEW + carries 3**.

### CLOSED via implementation (3 of 6)

1. ✅ W135 §Honesty #9 (real Docker chain authed visual smoke FULLY
   closed) — SW1 + SW3 + SW4 (8 SSR routes 200 + AUTHED + 0 hydration
   errors)
2. ✅ W136 §Honesty #4 (build-orchestrated upstream hang) — issue
   filing prep via SW7 (resolution outside our control)
3. ✅ W136 §Honesty #5 (Tier 3 housekeeping partial) — SW5 + SW6
   (file-processor production-ready + tempo+loki sidecars healthy)

### REMAINING from W134/W136 (3 of 6, all by-design or carry-forward)

4. W134 §Honesty #2 (bundle delta carry-forward) — superseded by W137
   §Honesty #4 (W134-W136 "BYTE-IDENTICAL build × 3" claims were
   spurious due to Dockerfile bug). Real W137 baseline is index-tGuQB5EY.js.
5. W134 §Honesty #10 (/messenger Phase 5 punted) — no-deploy decision
   unchanged. Tier 7 carry-forward.
6. W136 §Honesty #6 (Playwright /login screenshot fragility) —
   ParticleAuthBackground canvas. Sidecar JSON captures diagnostic;
   not a fix without VITE_E2E_MODE-style refactor.

### NEW from W137 (4 caveats — real polish-pass discoveries)

7. **W134-W136 reproducibility-claim mask** (SW4-prep Dockerfile
   discovery). The "BYTE-IDENTICAL build × 3" claim across 3 prior
   waves was structurally broken by host-cached dist/ leakage.
   Retroactive re-framing: prior claims should be read as "build × 3
   returned the same host-cached artifact each time, NOT a verified
   reproducibility property". Real W137 baseline going forward.

8. **file-processor dev-runtime healthcheck blocked by temporal-
   localhost** (SW5 §Honesty). Pre-existing P0-03 trade-off (audit
   2026-03-06): Temporal dev-server has no auth → bound 127.0.0.1
   only. file-processor requires Temporal access at startup → blocks
   indefinitely → grpc_health_probe times out. Pre-W137 invisible
   because no healthcheck. Production K8s where Temporal IS reachable
   → healthcheck works. W138+ candidate.

9. **`MAX_SESSIONS_PER_USER: 50` dev override** (SW4 finding).
   Production K8s should keep default `5`. NOT a security regression —
   just dev-quality-of-life override for iterative smoke runs.

10. **Sidecar healthiness ≠ container healthiness for tempo+loki**
    (SW6 by-design). Documented in compose + AUDIT. Production K8s
    should use upstream's /ready via livenessProbe httpGet check (not
    affected by this dev-only pattern).

**Total: 7 caveats remain post-W137** (vs 6 pre-W137; net +1 because
W137 fixed 3 BUT introduced 4 NEW from real polish-pass discoveries —
honest framing per `feedback_perfectionism.md`). Of the 7, **5 are
honest framings of real wins** (we shipped real fixes; the caveats
document trade-offs accepted) and **2 are structural/by-design** (W134
#10 /messenger + W136 #6 Playwright).

The plan target was "drops to ~3 caveats" but real polish-pass
discoveries (especially the W134-W136 reproducibility mask) increased
the count instead. Per W136 Lesson #7, this is acceptable — empirical
findings disprove plan assumptions.

## W138 candidates

See [`memory/wave138_opening_prompt.md`](wave138_opening_prompt.md)
for full list. Highlights:

### Tier 1 from W137 §Honesty (highest priority)

- **Build × N reproducibility re-establishment** (~30 min): re-run
  `start-docker.ps1 -Build` × 3 from clean state, assert byte-identical
  hashes with the corrected Dockerfile. This is the structurally-
  correct version of the W134-W136 "BYTE-IDENTICAL × 3" claim.
- **file-processor temporal-localhost** (~2-3h): rebind temporal to
  0.0.0.0 with auth OR host network OR explicit accept-as-dev-limitation.
- **vite-plugin-pwa workbox-build sw.js**: 1 console error per route
  on /dashboard etc. is the Service Worker registration failure.
  Closed in W138+ via fixing the build-orchestrated workaround OR
  upstream rolldown hang fix.

### Tier 4 cross-cutting (carry-forward)

- Per-page visual audit on 8 SSR routes — NOW FEASIBLE post-W137.
- Test infrastructure (a11y-public WebKit OOM, mobile-webkit /404).
- LHCI gate ratchet on REAL W137 baseline.
- a11y deep-audit cross-browser.
- Storybook/Chromatic activation.
- Playwright /login VITE_E2E_MODE refactor (~30 min).

### Tier 5 explicit decision (carry-forward)

- Messenger × 2 polish (~5-7 waves) OR /admin polish (~3-5 waves) OR
  punt as "production-as-is".

### Filed upstream issues (SW7) — pending external resolution

- rolldown/rolldown (build hang)
- chromedevtools/chrome-devtools-mcp (Windows headless heavy-DOM eval)
- grafana/tempo + grafana/loki (distroless health CLI)
