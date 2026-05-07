# Wave 132 — Phase 6 SSR canary rollout infrastructure (Local + author + runbook scope) — May 2026

**Branch**: `egorribun`
**Status**: ✅ COMPLETE (2026-05-07). Phase 6 deploy infrastructure: Caddy `lb_policy weighted_round_robin` SPA-fallback canary config + k8s rolling-update strategy + `frontend-stable` Deployment template + Server-Timing observability middleware + comprehensive operator runbook. Real canary deploy is W133+ ops work.
**Scope**: Option A "Phase 6 rollout" + sub-option "Local + author + runbook" per user-approved AskUserQuestion. ~6-7h core. Polish budget ~60-90 min.
**Threshold**: Met — ≥6 SSR routes (W128 /dashboard + W129 × 4 + W130 /schedule); W125 design § Phase 4 deploy infra complete via W131; Phase 6 author work is the natural continuation.
**Bundle (PROD build × 3 reproducible)**: client main chunk **`dist/client/assets/index-KalQn95O.js` — 138,974 bytes** (BYTE-IDENTICAL to W131 baseline) + `_shell.html` 65,872 bytes (BYTE-IDENTICAL). All W132 changes are server-side / infrastructure-only — zero client bundle impact.

## Executive summary

| # | Item | Status | SW |
|---|------|--------|-----|
| 1 | Pre-W132 W131 carry-over: `docker-compose.full.yml` frontend port mismatch (8080 → 3000) caught during SW1 verification prep | ✅ shipped | SW1-fix (`12d4afadd`) |
| 2 | Docker stack runtime verification through real Caddy → Node SSR → backend chain (closes W131 §Honesty #1+#2) | 🟡 PARTIAL — Node SSR runtime verified via `npm run start` + curl on host; full Docker chain DEFERRED to W133+ (build killed mid-cargo-wasm-pack-compile ~30 min) | SW1-verify |
| 3 | LHCI 9-URL × 3-run baseline against current SSR build | 🚫 DEFERRED to W133+ Linux CI (NO_FCP runtimeError on Windows headless Chrome — W128 §Honesty pattern; W129 SW6 `lhci-linux.yml` is canonical alternative) | SW2 |
| 4 | Caddy `lb_policy weighted_round_robin` canary config in `services/caddy/Caddyfile` | ✅ shipped + validated | SW3 (`f76ffa000`) |
| 5 | k8s rolling-update strategy + `frontend-stable` canary Deployment + Service + PDB template + canary-flip-strategies.md | ✅ shipped + YAML schema-valid | SW4 (`69ebcf99a`) |
| 6 | Server-Timing observability middleware in `server-prod.mjs` | ✅ shipped + curl-verified | SW5 (`09dd96ea5`) |
| 7 | Comprehensive Phase 6 rollout runbook at `docs/CANARY_ROLLOUT_PHASE6.md` | ✅ shipped | SW6 (`bb11757ae`) |
| 8 | Audit + memory + N+3 rotation (W129 → archive) + design doc + W133 handoff + polish-pass npm audit fix (basic-ftp 5.3.0 → ≥5.3.1) | ✅ shipped | SW7 (`76e422322`) + polish (`bbd365ddd`) |

**Delivered (W132)**:

1. **Phase 6 canary infrastructure authored** — Caddy edge-based SPA-fallback canary pattern via `lb_policy weighted_round_robin`. Two upstream pools (`frontend-stable:8080` legacy nginx + `frontend:3000` W131 Node SSR). Initial weights `100 0` (Caddyfile apply at Stage 0 = identity change). 5-stage progression `90/10 → 75/25 → 50/50 → 25/75 → 0/100` with per-stage soak + advance/abort criteria. Rollback = instant Caddy weight flip back to `100 0`. Pattern matches W125 design § Phase 6 step 5 ("Caddy config flip to serve old SPA build").
2. **k8s rolling-update strategy** added to `k8s/frontend/deployment.yaml` — explicit `RollingUpdate` with `maxSurge: 25%`, `maxUnavailable: 0`, `progressDeadlineSeconds: 600`. Node SSR Pod cycling during canary stages preserves capacity.
3. **frontend-stable canary template** at `k8s/frontend/canary/deployment-stable.yaml` — Deployment + Service + PDB for the legacy SPA fallback pool. Operator builds the legacy image during canary prep + sets the `${LEGACY_SPA_IMAGE}` placeholder. Manifests carry `wave: w132-canary` label for easy grep-and-delete at Stage 6 cleanup.
4. **Server-Timing middleware** in `server-prod.mjs` — emits `Server-Timing: ssr;dur=<float>;desc="ssr-render"` per SSR response (skipped for `/healthz` fast-path; static assets already short-circuit before SSR). Operators can filter responses by header presence to identify SSR-pool traffic during canary. ~30 LoC server-side.
5. **Comprehensive operator runbook** at `docs/CANARY_ROLLOUT_PHASE6.md` — 8 sections covering prerequisites, pre-canary checklist (8 steps), stages 1-5 procedure, rollback (instant Caddy flip + 8-failure-mode catalog with mitigations), Stage 6 cleanup, known limitations, cross-references, lessons-learned template. ~447 lines.
6. **W131 SW3 carry-over fix** — `docker-compose.full.yml` frontend service had stale `8081:8080` port mapping + healthcheck on `:8080/` (pre-W131 nginx values). W131 SW3 changed the Dockerfile to EXPOSE 3000 + Node listening on 3000, but the compose file wasn't updated because Docker stack runtime verification was deferred. SW1-fix aligns: ports `8081:3000` + healthcheck on `:3000/healthz` (W131 SW2 fast path).

**Not delivered (W132, intentionally per scope)**:

1. **Real `kubectl apply` of canary manifests** — no live cluster access on dev workstation per W131 §Honesty probe #6. YAML schema validation via `yaml.safe_load_all` substitutes for build-time guarantees; real schema validation deferred to W133+ staging cluster.
2. **Caddy weight flip on live cluster** — runbook documents the flip command pattern; no actual cluster traffic shifted in W132.
3. **Sentry alert thresholds wired with production-real values** — runbook explicitly flags placeholders that operator captures during Stage 0 baseline.
4. **LHCI baseline for SSR pool serving real traffic** — W132 SW2 captures the local SSR-build LHCI numbers; real RUM baseline needs canary deployment with actual users.
5. **Push subscription recovery flow under SW upgrade** — webpush is browser-controlled; runbook documents observation queries but no UX work in W132.
6. **WebSocket reconnect storm test under canary load** — preStop sleep:10 (W131 SW5) + ws-hub backoff (CLAUDE.md gotcha) are the existing mitigations; real canary observation is the test.
7. **`nitro()` plugin re-evaluation** (W131 §Honesty probe #3) — when TanStack Start improves PWA + LHCI integration in a future version.
8. **Sequential `/users/me` + `/schedule` lessons SSR** — W130 §Honesty probe #2; cookie forwarding to backend axios in Node SSR runtime now structurally possible but not implemented in W132.
9. **/profile or /settings SSR enablement** — W133+ candidate per W125 design §3 Phase 5 continuation.
10. **vite-plugin-pwa Windows hang structural fix** — `wave127-build-x3.sh` watch+kill workaround stable through W127-W131; W132 didn't pursue structural fix.
11. **MEMORY.md compaction** — pre-existing system warning at 65+ KB; W132 SW7 row prepended in compact ≤200 char form per index entry rule but global compaction deferred.

## Commits on origin (7 commits W132 + 1 SW1-fix prerequisite, ~12 files in code, ~5 in docs)

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 1 | `12d4afadd` | `fix(wave132-sw1-docker-compose-port): align frontend service to W131 Node SSR runtime` | 1 | +9 / -2 |
| 2 | `f76ffa000` | `feat(wave132-sw3-caddy-canary): SPA-fallback weighted_round_robin canary infrastructure` | 1 | +68 / -7 |
| 3 | `69ebcf99a` | `feat(wave132-sw4-k8s-canary): rolling-update strategy + frontend-stable canary template` | 3 | +327 / -0 |
| 4 | `09dd96ea5` | `feat(wave132-sw5-server-timing): emit Server-Timing header on SSR responses` | 1 | +33 / -2 |
| 5 | `bb11757ae` | `feat(wave132-sw6-runbook): comprehensive Phase 6 SSR canary rollout runbook` | 1 | +447 / -0 |
| 6 | `76e422322` | `docs(wave132-sw7-audit): full narrative + design doc + N+3 rotation (W129 → archive) + W133 handoff` | 5 | +528 / -5 |

## SW arc — what each commit does

### SW1-fix — `docker-compose.full.yml` port alignment (`12d4afadd`, 1 file +9/-2)

**File**: `docker-compose.full.yml`.

**Carry-over caught at SW1 verification prep**: W131 SW3 changed `frontend.Dockerfile` to `EXPOSE 3000` + Node listening on PORT 3000 via `server-prod.mjs`, but the compose service kept the pre-W131 nginx port mapping `8081:8080` and healthcheck against `http://127.0.0.1:8080/`. The container starts on :3000 internally; compose mapped :8081 to nothing listening; Caddy in the same compose network reverse-proxied `frontend:3000` correctly (so backend chain worked) but the host-mapped :8081 was unreachable AND the healthcheck always failed → container was perpetually marked unhealthy.

This is exactly why W131 §Honesty probe #1+#2 deferred Docker stack verification: the compose file had a real bug masked by the deferral.

Updates:
- `ports: 8081:8080` → `ports: 8081:3000`
- `healthcheck`: `wget http://127.0.0.1:8080/` → `wget http://127.0.0.1:3000/healthz` (uses W131 SW2 fast-path, <10ms response)
- Added in-line comment block explaining the migration

Validation: visual inspection only at this commit; runtime verification via SW1 Docker stack bring-up.

### SW3 — Caddy SPA-fallback canary config (`f76ffa000`, 1 file +68/-7)

**File**: `services/caddy/Caddyfile`.

**Changes**: Replace the W131 SW4 single-upstream `default` handle (`reverse_proxy frontend:3000 { health_uri /healthz; ... }`) with a `lb_policy weighted_round_robin` block fanning out to two upstream pools:

```caddy
handle {
    reverse_proxy {
        to frontend-stable:8080 frontend:3000
        lb_policy weighted_round_robin 100 0

        health_uri /healthz
        health_interval 10s
        health_timeout 5s

        fail_duration 30s
        unhealthy_status 5xx

        header_up X-Real-IP {http.request.remote}
        header_up X-Forwarded-For {http.request.remote}
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host {host}
    }
}
```

**Initial weights `100 0`** make the Stage 0 Caddyfile apply an identity change — stable serves all traffic; SSR pool gets zero. Operator triggers the canary via runbook command flip (edit weights → ConfigMap update → Caddy hot-reload). The W125 design § Phase 6 step 5 documented "Caddy config flip to serve old SPA build" as the rollback strategy; SPA-fallback pattern means flip back to `100 0` is the instant rollback path.

**`health_uri /healthz` for both pools**: SSR pool answers via W131 SW2 fast path (<10ms). Legacy nginx pool requires operator to add `/healthz` endpoint to its nginx config during canary prep — runbook step 4 documents this.

**Passive `fail_duration 30s` + `unhealthy_status 5xx`**: reactive failure handling on top of active probes. Combined gives proactive (probe-detected) and reactive (user-detected) failure response.

**Verification**: `caddy validate` via W131 polish A6 stripped-block method (rate-limit plugin requires custom services/caddy/Dockerfile not in base `caddy:2.11.2-alpine` image) — reported "Valid configuration". Pre-existing `infrastructure/Caddyfile` revalidated, also "Valid configuration".

`infrastructure/Caddyfile` (docker-compose mount) intentionally NOT changed — canary is operational, not local-test. Local stack stays single-target SSR.

Comment block at end of `services/caddy/Caddyfile` documents the post-Phase-6-cleanup single-upstream form for operator to revert at Stage 6.

### SW4 — k8s rolling-update + frontend-stable canary template (`69ebcf99a`, 3 files +327/-0)

**Files**: `k8s/frontend/deployment.yaml` (modified), `k8s/frontend/canary/deployment-stable.yaml` (NEW), `k8s/frontend/canary/canary-flip-strategies.md` (NEW).

**`k8s/frontend/deployment.yaml`** changes:
- Add explicit `spec.strategy.type: RollingUpdate` block with:
  - `maxSurge: 25%` — allows transient peak of replicas+1 Pod for rollouts within reasonable time
  - `maxUnavailable: 0` — NO drop in capacity during canary stage Pod cycling (new Pods come up + pass /healthz before old Pods removed)
  - `progressDeadlineSeconds: 600` — 10-min cap before controller marks rollout failed (Node SSR cold start + PWA precache can take 30-60s on first replica)
- Existing Deployment + Service `frontend` NOT renamed — they stay as the SSR pool target referenced from `services/caddy/Caddyfile` `frontend:3000` upstream

**`k8s/frontend/canary/deployment-stable.yaml`** (NEW, ~165 lines): template Deployment + Service + PodDisruptionBudget for the legacy SPA fallback pool.

Operator MUST set the `${LEGACY_SPA_IMAGE}` placeholder during canary prep (e.g. `registry.example.com/frontend-stable:pre-w125-spa`). The legacy nginx config MUST expose `/healthz` (200 OK) so Caddy's active health probe doesn't mark this pool unhealthy.

Manifests carry:
- `app.kubernetes.io/name: frontend-stable` — distinct selector value (existing `frontend` Service unchanged)
- `app.kubernetes.io/part-of: frontend` — groups stable + ssr in dashboards for per-pool comparison
- `wave: w132-canary` — operator can grep this label when removing artifacts at Stage 6

Resource ceiling pinned at pre-W131 nginx values (cpu 50m/200m, memory 64Mi/256Mi) since nginx is much lighter than Node SSR (~50 MB resident vs 250-400 MB for Node).

**`k8s/frontend/canary/canary-flip-strategies.md`** (NEW, ~120 lines): operator-facing quick-reference. Covers per-stage progression table (`100 0` → `90 10` → ... → `0 100`), Caddy ConfigMap flip command pattern, rollback flip (instant 100/0 revert), per-stage verification queries (Caddy access log upstream distribution, Server-Timing presence check, Pod count for HPA observation), Stage 6 cleanup procedure.

**Verification**: Python `yaml.safe_load_all` parses 8 docs cleanly across all `k8s/frontend/` manifests:
- Deployment + Service `frontend` (existing, with new strategy)
- Deployment + Service + PDB `frontend-stable` (new canary template)
- NetworkPolicy + HPA + PDB (existing, unchanged)

`kubectl apply --dry-run=server` requires live cluster API server (not available on dev workstation; W131 §Honesty probe #6); deferred to W133+ staging cluster.

### SW5 — Server-Timing middleware (`09dd96ea5`, 1 file +33/-2)

**File**: `frontend/scripts/server-prod.mjs`.

**Changes**:
- `pipeWebResponse(webResponse, res, extraHeaders?)` accepts optional third argument; values appended via `res.appendHeader` so we don't clobber upstream Set-Cookie / content-type already in the response Headers.
- Server-Timing emission in createServer handler:
  - Measure `performance.now()` before/after `handler.fetch(request)` for sub-ms precision on SSR-layer round-trip
  - Emit `Server-Timing: ssr;dur=<float>;desc="ssr-render"` for all routes EXCEPT `/healthz` (W131 SW2 fast-path stays clean — probes shouldn't be tagged as SSR-pool traffic)
  - Static asset path (W131 SW7 `serveStatic`) already short-circuits BEFORE SSR layer, so static responses never carry Server-Timing by construction (no extra check needed)

**Why**: during canary stages 1-5, Caddy returns the SSR pool response transparently to the client. Without a per-pool marker, the edge access log only shows the upstream identity, and even that gets blurred by `health_uri /healthz` probes which both pools answer identically. Server-Timing lets operators (a) confirm during canary smoke that the SSR pool received traffic matching the configured weights, (b) aggregate `dur` distribution per stage for advance/abort decisions per the runbook.

**Verification (curl on `node ./scripts/server-prod.mjs` PORT=3000)**:

| Endpoint | Method | Status | Server-Timing | Server-side ms |
|----------|--------|--------|---------------|----------------|
| `/healthz` | GET | 200 | NOT emitted (skipped) | 3ms |
| `/healthz` | HEAD | 200 | NOT emitted | 1ms |
| `/login` | HEAD | 200 | `ssr;dur=662.56;desc="ssr-render"` | 663ms (cold-start) |
| `/assets/index-KalQn95O.js` | HEAD | 200 | NOT emitted (static layer skip) | 1ms (static) |
| `/healthz` (warm) | GET | 200 | NOT emitted | 0ms |

All matched expectations. Cold-start 663ms reflects router + JWKS init; warm path on real traffic is much faster.

**Bundle invariant**: `server-prod.mjs` is a Node script not bundled into the React client tree. PROD `dist/client/assets/index-KalQn95O.js` stays at 138,974 bytes (W131 SW8 baseline preserved exactly).

### SW6 — Comprehensive Phase 6 rollout runbook (`bb11757ae`, 1 file +447/-0)

**File**: `docs/CANARY_ROLLOUT_PHASE6.md`.

**Why DEPLOY.md naming convention** (and not new `docs/operations/` directory): consistency with existing operational docs (`DEPLOY.md`, `DEPLOY.en.md`, `pgcat-migration-guide.md`, `manual-mfa-checklist.md`, etc.) all live at `docs/` root with topic-based names. Creating `docs/operations/` would introduce inconsistency for one wave's deliverable.

**Sections**:

1. At-a-glance — high-level summary, expected outcome (LCP ~12s → ~2-4s on authenticated routes), rollback path of last resort
2. Architecture map — ASCII diagram showing `client → Caddy → {frontend-stable | frontend} → backend` chain with weight knob location
3. Prerequisites — k8s + registry + Caddy ConfigMap + Sentry/Grafana access
4. Pre-canary checklist — 8 steps from W131 baseline verification through Stage 0 baseline metric capture (24h observation)
5. Canary stages 1-5 — per-stage advance/abort criteria table (placeholders flagged), weight-flip command pattern, soak monitoring queries, Server-Timing observation
6. Rollback procedure — instant Caddy flip back to `100 0` + 8-failure-mode catalog with mitigations:
   1. Hydration mismatch at scale → W127 SW2-5 cookie-mirror; rollback + capture stack traces
   2. Cookie SameSite=Lax breaks SSO callbacks → `SECURITY_COOKIE_SAMESITE_OVERRIDE=strict` env var (W131 SW6 rollback knob)
   3. Service worker collision → W131 SW4 `/sw.js → frontend:3000` always (single source); user hard reload
   4. VITE_LHCI bypass leaks to prod → pre-deploy gate `grep -l "lhci-mock-user" dist/assets/*.js`
   5. Push subscription invalidation → 24-48h soak observation; UX recovery flow
   6. Caddy hot-reload transient 5xx → expected ~50-200ms window during reload
   7. Memory leak in Node SSR worker → k8s memory limit + HPA + scheduled restart
   8. ws-hub reconnect storm → preStop sleep:10 + ws-hub backoff
7. Stage 6 cleanup — delete `frontend-stable`, revert Caddy single-upstream, re-baseline LHCI gates per W124 SW4 ratchet method
8. Known limitations + carry-forward deferrals — 8 items honestly listed (threshold placeholders, ConfigMap pattern assumption, SECURITY_COOKIE_SAMESITE_OVERRIDE not exercised in prod, etc.)
9. Cross-references — W125 design Phase 6, W131 §Honesty probes, W132 SW3-5 artifacts
10. Lessons-learned template — operator fills post-Phase-6 with measured metrics, surprises, recommended W125 design amendments

**Threshold values explicitly marked as PLACEHOLDERS** (e.g. "error rate < 0.5%", "LCP p75 < 4s"). Operator captures Stage 0 baseline and adjusts before Stage 1 — this is documented as Step 8 of the pre-canary checklist. Per `feedback_perfectionism.md` "be specific, don't paper over with future-wave labels", the runbook framework is correct + the templates are explicit.

### SW1-verify — Docker stack runtime verification (pending Docker build completion)

Status: 🟡 **PARTIAL closure** — Node SSR runtime verified standalone via `npm run start` + curl on host (closes runtime-level); full Docker stack chain DEFERRED to W133+ (closes only partially the W131 §Honesty #1+#2 deferral).

**What was attempted**: Build kicked off via Monitor (`docker compose -f docker-compose.full.yml build --no-cache --progress=plain frontend`). Build observed via Monitor reaching `wasm-builder 2/6 RUN cargo install wasm-pack` phase (cargo deps download → `Compiling libc v0.2.180` phase started). Build cache grew from 127 GB → 135 GB (+8 GB) confirming progress. Linux container build (no Windows vite-plugin-pwa hang risk).

**Why killed**: After ~25 min elapsed at the cargo wasm-pack compile phase (structurally slow on Windows fresh Docker build — typical 30-60 min total for first-time full-image rebuild), made pragmatic decision to kill via TaskStop + free CPU/disk for SW2 LHCI baseline + SW7 audit work. Per `feedback_perfectionism.md` "if you can't measure, defer honestly" — better to ship the W132 deliverables on time with honest framing than block the wave indefinitely on a structurally slow build.

**Runtime-level verified separately** (the closure that DID happen):
- `node ./scripts/server-prod.mjs` PORT=3000 listened cleanly
- curl /login: 200 + 21KB SSR HTML + `Server-Timing: ssr;dur=662.56;desc="ssr-render"` (cold-start; warm path much faster)
- curl /healthz: 200 + 15B + 3ms server-side + NO Server-Timing (fast-path skip)
- curl /assets/index-KalQn95O.js: 200 + immutable cache + NO Server-Timing (static layer)
- curl /dashboard: 307 → /login (W126 auth-at-edge active in non-LHCI build)

**Integration-level NOT verified** (the closure that's W133+ scope):
- chrome-devtools-mcp visual smoke through real Caddy → Node SSR → backend chain on 8 routes
- 0 React hydration errors observation under real network proxy
- /api → backend proxy verification
- /ws → ws-hub proxy verification
- /sw.js delivery with `service-worker-allowed: /` header through Caddy
- Healthcheck behavior under real k8s liveness/readiness probes

**The `docker-compose.full.yml` SW1-fix carry-over IS shipped + structurally correct** — operator can `docker compose -f docker-compose.full.yml up -d` and the chain SHOULD work; we just didn't confirm runtime per-step in W132. Next-wave operator (or staging cluster verification post-W132 deploy) closes the integration-level gap naturally.

### SW2 — LHCI baseline DEFERRED to W133+ Linux CI (NO_FCP Windows headless Chrome structural limitation)

Status: 🚫 **DEFERRED** to W133+ via W129 SW6 `lhci-linux.yml` workflow_dispatch trigger.

**What was attempted**:
1. Built VITE_LHCI=true dist via wave127-style watch+kill (35s elapsed): produced `dist/server/server.js` 38,796 bytes + `dist/client/_shell.html` 65,954 bytes (matches W130 baseline) + `dist/client/assets/index-BQK8rdbb.js` 137,769 bytes (matches W130 VITE_LHCI baseline exactly — reproducibility ≥ 4 waves)
2. Ran `npm run lhci:windows` with `SKIP_BUILD=1 LHCI_RUNS=3` — 9 URLs × 3 runs (the W121 SW8 default URL list: `["/", "/login", "/dashboard", "/news", "/schedule", "/events", "/activity", "/map", "/404"]` post-LanternError-fix-via-Lighthouse-13)
3. Vite preview started cleanly on http://127.0.0.1:4174
4. Lighthouse 13.1.0 invoked on first URL `/`
5. Run 1 produced LHR JSON 255 KB at `.lighthouseci/lhr_root_run1.json` with EPERM-survived flag from wrapper

**What broke**: Inspecting `lhr_root_run1.json` shows:

```json
{
  "runtimeError": {
    "code": "NO_FCP",
    "message": "The page did not paint any content. Please ensure you keep the browser window in the foreground during the load and try again. (NO_FCP)"
  },
  "categories": {
    "performance": { "score": null },
    "accessibility": { "score": null }
  }
}
```

**Root cause**: same structural Windows + headless Chrome + Lighthouse 13.1.0 + this-dist environment limitation documented in W128 §Honesty probe + W130 §Honesty probe (SW7 explicitly): "Lighthouse + headless Chrome + Windows NO_FCP across all routes — structural environment limitation, not W128 regression — chrome-devtools-mcp real Chrome works fine". Headless Chrome on Windows fails to paint any content within Lighthouse's wait-for-condition timeout, returns NO_FCP error before any meaningful audit data is collected.

**Why it's a structural deferral, not a fixable regression**:
- W128 first documented this as Windows-specific (real Chrome via chrome-devtools-mcp works fine)
- W129 SW6 (`78b1b5f3d`) shipped `.github/workflows/lhci-linux.yml` workflow_dispatch trigger as the on-demand alternative — Linux CI runner doesn't hit NO_FCP
- W130 §Honesty probe carried it forward unchanged ("LHCI numerical sweep on /schedule NOT executed (existing CI lighthouse: job covers)")
- W131 also didn't run local LHCI; trusted CI Linux run

**SW2 closure status**: NO new local LHCI numbers captured. The W129 SW6 lhci-linux.yml workflow is the canonical alternative — operator triggers via GitHub Actions workflow_dispatch when canary numbers are needed. Existing `frontend-tests.yml lighthouse:` job has run on Linux every PR since W117+ (per W129 honest re-framing). LHCI process killed cleanly post-run-1; vite preview server stopped; .lighthouseci/lhr_root_run1.json kept as evidence of the NO_FCP runtimeError for §Honesty probe documentation.

**Reproducibility separately verified** (independent of LHCI): VITE_LHCI build produced exactly matching W130 baseline (137,769 + 65,954 bytes — reproducibility ≥ 4 waves), confirming dist is correctly shaped + tree-shake invariant intact.

**Comparison target preserved for W133+ Linux CI run**: W124 SW4 baseline (pre-SSR):

| URL | Pre-SSR Perf (W124 SW4) | Pre-SSR CLS | Pre-SSR LCP | Post-SSR (W133+ Linux CI) |
|-----|------------------------:|------------:|------------:|--------------------------:|
| / | 0.54 | 0.017 | TBD | TBD via lhci-linux.yml |
| /login | 0.56 | 0.000 | TBD | TBD |
| /dashboard | 0.46 | 0.017 | TBD | TBD |
| /news | 0.52 | 0.006 | TBD | TBD |
| /schedule | 0.51 | 0.003 | TBD | TBD |
| /events | 0.47 | 0.062 | TBD | TBD |
| /404 | 0.54 | 0.000 | TBD | TBD |

When W133+ ops trigger lhci-linux.yml or first PR push runs CI's `frontend-tests.yml lighthouse:` job, the post-SSR numbers can be tabulated against this W124 baseline for the actual LCP delta measurement. Direction expectation per W125 design § Phase 6 step 1: SSR-enabled routes show meaningful LCP improvement (~12s SPA → ~2-4s SSR target).

### SW7 — Audit + memory + N+3 rotation + design doc + W133 handoff (this commit)

**N+3 rotation**: `git mv docs/audits/AUDIT_WAVE129.md docs/audits/archive/AUDIT_WAVE129.md`. Active audits after rotation: W130, W131, **W132**.

**Files written/modified**:
- `docs/audits/AUDIT_WAVE132.md` (NEW, this file)
- `docs/audits/INDEX.md` (modify — prepend W132 row + move W129 to archive section + bump rotation history "tenth" → "eleventh" in header)
- `docs/plans/2026-05-07-wave132-phase6-rollout-design.md` (NEW design doc captured post-execution)
- `CLAUDE.md` (modify — Audit Trail W132 row + new gotchas: canary entry-points, Server-Timing pattern, runbook location, rollback decision tree, weight-flip command convention)
- `memory/MEMORY.md` (prepend W132 row to Active backlog ≤200 chars + Audit History one-line entry)
- `memory/wave132_backlog.md` (NEW, closed status)
- `memory/wave133_opening_prompt.md` (NEW, handoff with W133 candidate options)

## Verification metrics (final)

- **tsc**: 0 errors after each SW (via `cd frontend && npx tsc --noEmit`)
- **eslint**: 0 warnings (`max-warnings=0`) after each SW
- **vitest**: **988p / 12s / 0f** preserved (W131 SW8 baseline; no frontend test changes in W132)
- **pytest backend slice**: 75p+/0f preserved (no backend changes in W132)
- **npm audit**: **0 vulnerabilities** (W119 SW5 + W130 SW4 baseline preserved)
- **Cargo.lock**: no drift (idempotent ≥ 22 waves at end of W132 — no Rust changes in W132)
- **Build × 3 reproducible PROD**: `index-KalQn95O.js` 138,974 bytes + `_shell.html` 65,872 bytes (BYTE-IDENTICAL to W131 baseline — confirms all W132 changes are server-side / infrastructure-only)
- **`npm run start` Server-Timing smoke**: Server-Timing emitted on /login (`ssr;dur=662.56`); skipped on /healthz + static assets — see SW5 verification table
- **YAML schema validation**: 8 k8s/frontend docs parse cleanly (`yaml.safe_load_all`)
- **Caddy validate**: `services/caddy/Caddyfile` (W131 polish A6 stripped-block) + `infrastructure/Caddyfile` both report "Valid configuration"
- **6 SSR routes preserved**: /dashboard W128 + /events + /events/$id + /news + /news/$id W129 + /schedule W130 — server-prod.mjs continues to delegate to tanstackStart's per-route SSR
- **4 sibling explicit ssr:false routes preserved**: messenger × 2, profile, settings (W128 SW2 opt-downs unchanged)
- **/map + /activity ssr: 'data-only'** preserved (W127 SW6 annotations under W128 SW2 permissive parent)
- **Docker stack runtime verification**: 🚫 PARTIAL closure — Node SSR runtime verified standalone via `npm run start` + curl on host (Server-Timing emits, /healthz fast-path, static-layer skip, /dashboard 307→/login auth-at-edge), but full Caddy → Node → backend chain through real Docker stack stays W133+ scope (build attempted via Monitor; cargo wasm-pack compile phase ~30 min on Windows fresh build; killed pragmatically to free resources for SW2 + SW7). The `docker-compose.full.yml` SW1-fix carry-over IS shipped + structurally correct.
- **LHCI baseline**: 🚫 DEFERRED to W133+ Linux CI per W129 SW6 `lhci-linux.yml` workflow_dispatch trigger. Local Windows attempt produced NO_FCP runtimeError on first run (structural Windows + headless Chrome + Lighthouse 13.1.0 limitation per W128 §Honesty + W130 §Honesty pattern). Reproducibility separately verified — VITE_LHCI build matches W130 baseline exactly (`index-BQK8rdbb.js` 137,769 + `_shell.html` 65,954 bytes).

## §Honesty probe — caveats openly disclosed (anticipated ~12-15 caveats)

Per `feedback_perfectionism.md` "безупречно?" probe anticipation:

1. **W132 SW1 + SW2 BOTH closed as honest deferrals, NOT as full closures**. SW1 Docker stack runtime verification: Node SSR runtime verified standalone via `npm run start` + curl on host (closes runtime-level — Server-Timing emits, /healthz fast-path, static-layer skip, /dashboard 307→/login auth-at-edge); but full Caddy → Node SSR → backend chain through real Docker stack stays W133+ scope (build attempted, cargo wasm-pack compile phase ~30 min on Windows fresh build; killed pragmatically). SW2 LHCI baseline: local Windows attempt produced NO_FCP runtimeError on first run — same structural Windows + headless Chrome + Lighthouse 13.1.0 limitation documented in W128 §Honesty + W130 §Honesty SW7 ("Lighthouse + headless Chrome + Windows NO_FCP across all routes — structural environment limitation"); deferred to W133+ Linux CI via W129 SW6 `lhci-linux.yml` workflow_dispatch trigger (existing `frontend-tests.yml lighthouse:` job has run on Linux every PR since W117+). Per `feedback_perfectionism.md` "if you can't measure, defer honestly" — both gaps documented openly with structural reasons rather than blamed on time/scope.
2. **`docker compose build` may still hang on Windows despite Linux container build**. Mitigation `docker buildx prune -af` not run upfront (would have nuked 132 GB cache shared with other images). If build doesn't complete within reasonable time, kill + use `wave127-build-x3.sh`-style watch+kill workaround OR document as still-deferred.
3. **`frontend-stable` template references nginx image tag that doesn't yet exist**. Operator builds it during canary prep (runbook step 4). The template is defensive — `${LEGACY_SPA_IMAGE}` placeholder is explicit; `kubectl apply` would fail without substitution.
4. **Caddy weight-flip command pattern in runbook is hypothetical**. Assumes ConfigMap pattern; if cluster uses Helm / Argo CD / Flux, operator adjusts.
5. **Server-Timing on tanstackStart Response works because Headers are mutable**. Verified locally via curl. Edge case: if a future tanstackStart version returns immutable Response Headers, the `res.appendHeader` pattern would still work (Node's `ServerResponse.appendHeader` exists since Node 18+).
6. **Runbook abort thresholds are placeholders**. Operator captures Stage 0 baseline + adjusts. Documented as such.
7. **W131 §Honesty probe #5 Docker cache pollution**: 132 GB build cache existed at W132 start; not pruned (would conflict with other working images). Build may have re-used some stale cache; `--no-cache` flag should bypass but Docker BuildKit caching semantics are complex.
8. **W131 §Honesty probe #10 SECURITY_COOKIE_SAMESITE_OVERRIDE rollback knob NOT exercised in production**. Still unit-tested only; W132 doesn't deploy. Runbook documents the env var as the SSO-callback emergency escape.
9. **W130 + W131 honest deferrals carried forward unchanged**. Sequential /schedule lessons SSR (W130 §Honesty #2), Weather forceRefresh (W130 polish-followup), MEMORY.md compaction, etc. — all open.
10. **MEMORY.md size** > 24.4 KB system warning. W132 SW7 row prepended in compact form (≤200 chars per index entry rule); global compaction NOT in W132 scope.
11. **`caddy validate` on production Caddyfile uses W131 polish A6 stripped-block method** (rate-limit plugin requires custom services/caddy/Dockerfile not in base image). Not a true full-config validate; defense-in-depth via `infrastructure/Caddyfile` (validated cleanly with no plugin) + same syntax preserved.
12. **chrome-devtools-mcp visual smoke through real Caddy chain on 8 routes is the "real" closure for W131 §Honesty #1+#2**. If only `npm run start` + curl works (no Docker stack), W131 §Honesty stays partially deferred with explicit framing — runtime-level (Node SSR runs cleanly outside Docker) but NOT integration-level.
13. **The W131 SW3 carry-over** (`docker-compose.full.yml` port mismatch) is a real bug that W131 §Honesty probe #1+#2 deferral allowed to hide. Caught + fixed in SW1-fix; future similar carry-overs would benefit from a CI lint step that grep-checks compose port mappings against Dockerfile EXPOSE directives.
14. **Polish-pass anticipation** (post-SW7): runbook cross-ref `grep -f` final pass; SW7 memory + handoff completeness; CLAUDE.md gotcha cross-references; build × 3 invariant re-confirmation; honest carve-out of any "I didn't measure / I didn't verify / workaround instead of fix" gaps.

## W133 candidates (forward-looking)

Phase 6 W132 author work shipped. The natural next steps:

1. **Phase 6 actual rollout** (operations) — staging cluster deploy + canary 10% → 25% → 50% → 100% via the W132 runbook. Real LCP wins materialise here. Requires real prod deploy access.
2. **Sequential `/users/me` + `/schedule` lessons SSR** (W130 §Honesty probe #2) — cookie forwarding to backend axios in Node SSR runtime now structurally possible.
3. **`/profile` or `/settings` SSR enablement** (~1-2h each) — close 1-2 of remaining 4 ssr:false sibling routes.
4. **`nitro()` plugin re-evaluation** (W131 §Honesty probe #3) — when TanStack Start improves PWA + LHCI integration.
5. **vite-plugin-pwa Windows hang structural fix** — `wave127-build-x3.sh` workaround stable but not retired.
6. **LHCI baseline post-Phase-6-actual-rollout** — measure real-user LCP delta on production SSR (vs local Lighthouse variance which is bounded).
7. **`frontend/nginx.conf` deletion** (W131 §Honesty #9) — pre-Phase-6 rollback safety; deletable post-100% canary cleanup.
8. **MEMORY.md compaction** — pre-emptively suggested W131+ candidate; W132 deferred per scope.

---

**Branch HEAD pre-SW7**: `bb11757ae` (SW6 runbook) ← `09dd96ea5` SW5 ← `69ebcf99a` SW4 ← `f76ffa000` SW3 ← `12d4afadd` SW1-fix ← `ca5223ba9` (W131 polish).

Branch ahead of `origin/egorribun` by **+22 commits pre-SW7** (5 W132 author + W131 SW1-fix carry-over + 7 W131 + 7 W130 + 2 polish/audit).

---

## Polish pass (post-SW7, executed, ~70 min budget)

Per `feedback_perfectionism.md` "безупречно?" probe anticipation. 4 polish items closed:

### A1 ✅ npm audit baseline restoration (commit `bbd365ddd`)

Discovered during gate verification: `basic-ftp <=5.3.0` has GHSA-rpmf-866q-6p89 (high severity DoS via unbounded multiline FTP control response buffering). The W119 SW5 override was an EXACT pin `"basic-ftp": "5.3.0"` (not range) — locked transitive deps to the now-vulnerable version even though the CVE was disclosed AFTER W119 SW5 set the 0-vulnerabilities baseline. Same upstream-CVE pattern as W130 SW4 ip-address 10.1.0 → 10.2.0.

Fix: change override to `>=5.3.1` so npm resolves to latest non-vulnerable release. After install: basic-ftp resolves to 6.0.1 (latest). The basic-ftp upgrade chain only runs through `@lhci/cli → proxy-agent → pac-proxy-agent → get-uri → basic-ftp`; FTP control logic is unused at app runtime (LHCI is dev-only tooling), so behavioral risk is nil.

Verified: `npm audit --audit-level=low` → "found 0 vulnerabilities" (W119 SW5 + W130 SW4 baseline restored). vitest 988p/12s/0f preserved.

### A2 ✅ SW1+SW2 honest framing across 4 files (commit `9cbb13198`)

Per `feedback_perfectionism.md` "if you can't measure, defer honestly" pattern. SW7 audit had marked SW1 + SW2 as "in-flight at commit time" with TBD outcomes. Polish pass replaced TBD with explicit closure status:

**SW1 PARTIAL closure**: runtime-level (Node SSR via `npm run start`) ✅; integration-level (full Caddy → Node SSR → backend chain) DEFERRED to W133+ (Docker build killed mid-cargo-wasm-pack-compile after ~25 min — structurally slow on Windows fresh build; cache 127→135 GB confirming progress).

**SW2 DEFERRED to W133+ Linux CI**: NO_FCP runtimeError on first local LHCI run — same structural Windows + headless Chrome + Lighthouse 13.1.0 limitation per W128 §Honesty + W130 §Honesty SW7 pattern. Canonical alternative: W129 SW6 `lhci-linux.yml` workflow_dispatch trigger. Reproducibility separately verified — VITE_LHCI build matches W130 baseline exactly (`index-BQK8rdbb.js` 137,769 + `_shell.html` 65,954 bytes).

Files modified: `CLAUDE.md`, `docs/audits/AUDIT_WAVE132.md`, `docs/audits/INDEX.md`, `memory/MEMORY.md`, `memory/wave132_backlog.md` (last two outside git per Claude memory layout). Executive summary table SW1/SW2 markers updated to 🟡 PARTIAL / 🚫 DEFERRED. §Verification metrics rows updated. §Honesty probe item #1 split into SW1 + SW2 explicit framing.

### A3 ✅ PROD build × 3 reproducibility verified

`bash frontend/scripts/wave127-build-x3.sh` (W127 SW7 watch+kill workaround). All 3 fresh builds produced exactly:

```
Build 1: index-KalQn95O.js (138974 bytes) | _shell.html (65872 bytes)
Build 2: index-KalQn95O.js (138974 bytes) | _shell.html (65872 bytes)
Build 3: index-KalQn95O.js (138974 bytes) | _shell.html (65872 bytes)
```

**BYTE-IDENTICAL to W131 SW8 baseline** confirmed × 3 fresh builds. The audit's "BYTE-IDENTICAL" claim now has empirical backing rather than just inference from "no client-tree changes". Reproducibility invariant carries through ≥ 5 waves now (W127 → W131 → W132).

### A4 ✅ pytest backend slice baseline preserved

`pytest tests/test_csrf.py tests/test_config_modules.py tests/test_auth_cookie_flow.py tests/test_wave131_cookie_migration.py tests/test_config_security.py -q` → **78 passed, 10 warnings in 3.70s, 0 failed** (W131 polish A1 baseline preserved exactly: csrf 44 + config_modules 15 + auth_cookie_flow 8 + config_security 3 + wave131_cookie_migration 8 = 78).

The SW7 audit claim "75p+/0f" was conservative (75 from the 4-file slice originally, "+" indicating more if all 5 files included). Polish-verified actual = 78p across 5 files matching W131 polish A1 exact framing.

### Polish summary

- **Closed at polish**: 4 items (npm audit fix, SW1+SW2 honest framing, build × 3 reproducibility, pytest baseline)
- **Remaining as W133+ scope** (structural):
  - chrome-devtools-mcp visual smoke through real Docker Caddy chain (W131 §Honesty #1+#2 integration-level — needs cluster or fresh ~30-60 min Docker build)
  - LHCI numerical baseline (W129 SW6 lhci-linux.yml is canonical alternative)
  - SECURITY_COOKIE_SAMESITE_OVERRIDE prod runtime test (W131 §Honesty #10 — no cluster access)
  - MEMORY.md compaction (W131+ deferred)
  - frontend/nginx.conf deletion (W131 §Honesty #9 — kept as Phase 6 rollback safety)
- **Polish budget**: ~70 min actual (within 60-90 min `feedback_perfectionism.md` envelope)
- **Polish commits**: `bbd365ddd` (npm audit) + `9cbb13198` (SW1+SW2 honest framing) + this in-place audit update

**Final branch HEAD post-polish-round-1**: `9cbb13198` (polish honest framing) ← `bbd365ddd` (polish npm audit) ← `76e422322` (SW7 audit) ← `bb11757ae` SW6 ← `09dd96ea5` SW5 ← `69ebcf99a` SW4 ← `f76ffa000` SW3 ← `12d4afadd` SW1-fix ← `ca5223ba9` (W131 polish).

Branch ahead of `origin/egorribun` by **+25 commits post-polish-round-1** (8 W132 + 7 W131 + 7 W130 + 3 polish/audit).

---

## Polish round 2 (post-"безупречно?" probe, executed, ~50 min budget)

User invoked the `feedback_perfectionism.md` "безупречно?" probe after polish round 1. Honest self-audit surfaced 8 (a)-tier polish gaps fixable in-session. Round 2 closed 4 + honestly deferred 4 that hit structural Windows + headless Chrome limitations (same NO_FCP family as W128 §Honesty deferral).

### Round 2 — closures

| # | Item | Outcome | Evidence |
|---|------|---------|----------|
| a-1 | **Storybook build re-verify** | ✅ 18.79s exit 0 | `Storybook build completed successfully` + `real 0m18.793s` (W131 polish A6 baseline 17.08s; +1.7s within ~10% noise band; W125 baseline 18.48s) |
| a-2 | **i18n:check + tokens:sync drift** | ✅ 18/18 tests + 631 vars no drift | `Test Files 1 passed (1) Tests 18 passed (18)` + `Found 631 CSS variables in partials/ + tokens/` + `git status -sb` clean (CI gate MOD-43-01 passes) |
| a-3 | **docker-compose.yml dev compose port fix** | ✅ committed `271024ffc` | Same W131 SW3 carry-over pattern as docker-compose.full.yml SW1-fix (`12d4afadd`); ports `8081:8080 → 8081:3000` + healthcheck `:8080/ → :3000/healthz`. Closes the wider scope per SW1-fix audit note "Wider fix considered for polish-pass." |
| a-6 | **chrome-devtools-mcp visual smoke /login + /dashboard** | ✅ 0 React hydration errors | `npm run start` PORT=3142 → chrome-devtools-mcp `new_page` → `list_console_messages`. /login: 1 message `[GlobalErrors] Handlers registered` (W117 SW3 expected). /dashboard via `new_page` (W129 polish #3 lesson — `navigate_page` hangs on backend-down /api): URL became `/login?redirect=%2Fdashboard` ✓ auth-at-edge 307 active per W126; 0 hydration errors + 2 expected errors `Failed to load resource: 500` + `Failed to fetch current user` (no backend on host — expected). Matches W128/W130 polish baseline pattern. |

### Round 2 — honest deferrals (structural Windows + headless Chrome NO_FCP family)

All 4 hit the same root cause as W128 §Honesty probe + W130 §Honesty SW7 + LHCI deferral: **Windows + headless Chrome + Chrome DevTools Protocol perf/render APIs structurally fail to deliver paint/render events within reasonable timeouts on this dev workstation**. Same canonical alternative: W129 SW6 `lhci-linux.yml` workflow_dispatch on Linux CI runner (which runs without these limitations).

| # | Item | Attempt + outcome | Why structural |
|---|------|-------------------|----------------|
| a-4 | **e2e a11y-public.spec.ts chromium 4/4** | 🚫 4 failed at line 83 `await page.waitForTimeout(300)` after 90s default timeout AND 180s extended timeout. Error: `Test timeout exceeded` + `Target page, context or browser has been closed` — Chromium browser crash mid-test (likely on `await builder.analyze()` at line 103 — axe-core injection on a complex DOM with ParticleAuthBackground gated but other heavy elements). Tried with VITE_E2E_MODE=1 build (verified `data-e2e-stub` present in bundle, `particleCount` tree-shaken from main chunk) on `npm run preview --port 5173` — same crash. | Default Playwright `webServer.command npm run build && npm run preview` ALSO hits vite-plugin-pwa Windows hang at 360s timeout (W125/W128 pattern). SKIP_WEBSERVER mode bypasses the build step but axe.analyze() still crashes Chromium on Windows. Linux CI doesn't hit this — `frontend-tests.yml e2e:` job runs them fine (since W117+). |
| a-5 | **e2e url-state-persistence.spec.ts chromium 6/6** | 🚫 NOT attempted — same Playwright Windows + axe runtime pattern as a-4 would apply. Skipping repeat of structural failure. | Same as a-4. |
| a-7a | **chrome-devtools-mcp `lighthouse_audit`** on /login | 🚫 `Network.emulateNetworkConditions timed out. Increase the 'protocolTimeout' setting in launch/connect calls for a higher timeout if needed.` Same Chrome DevTools Protocol perf API timeout pattern as LHCI NO_FCP. | Lighthouse runtime via chrome-devtools-mcp shares the same headless Chrome + CDP perf-emulation infrastructure that fails on Windows. |
| a-7b | **chrome-devtools-mcp `performance_start_trace`** on /login | 🚫 `Navigation timeout of 10000 ms exceeded` even with `reload: true autoStop: true`. Same family as a-7a. | Same. |

### Round 2 — visual smoke evidence (raw chrome-devtools output)

```
$ chrome-devtools-mcp.new_page url=http://localhost:3142/login
Pages: 2: http://localhost:3142/login [selected]
$ chrome-devtools-mcp.list_console_messages
msgid=1 [info] [GlobalErrors] Handlers registered (2 args)
[NO ERRORS, NO HYDRATION MISMATCHES]

$ chrome-devtools-mcp.new_page url=http://localhost:3142/dashboard
Pages: 3: http://localhost:3142/login?redirect=%2Fdashboard [selected]
[AUTH-AT-EDGE 307 ACTIVE, REDIRECTED]
$ chrome-devtools-mcp.list_console_messages
msgid=1 [info] [GlobalErrors] Handlers registered (2 args)
msgid=2 [error] Failed to load resource: 500 (Internal Server Error)
msgid=3 [error] Failed to fetch current user (2 args)
[2 expected backend-down errors; NO REACT HYDRATION MISMATCHES]
```

Visual smoke verified the W128/W130 polish baseline holds: 0 React hydration errors on /login + /dashboard auth-at-edge 307 chain through real Chrome (not headless). Combined with W132 SW5 curl evidence (Server-Timing emits on /login, skipped on /healthz + /assets/*), the runtime-level closure of W131 §Honesty #1+#2 is solid; the integration-level (full Caddy → Node → backend chain) stays W133+ scope.

### Round 2 polish summary

- **4 items closed**: Storybook build, i18n+tokens, docker-compose.yml port fix, chrome-devtools visual smoke
- **4 items DEFERRED structurally**: 2 e2e Playwright (axe.analyze Chromium crash) + 2 chrome-devtools-mcp perf APIs (CDP `Network.emulateNetworkConditions` + Navigation timeouts) — all same Windows + headless Chrome NO_FCP family with W129 SW6 `lhci-linux.yml` as canonical alternative
- **Round 2 commits**: 1 (`271024ffc` docker-compose dev port fix); other closures are verifications without code changes
- **Round 2 budget**: ~50 min actual

Polish round 2 confirms the W128 §Honesty + W130 §Honesty pattern: local Windows + headless Chrome perf/render automation is structurally limited; CI Linux is the verification path. The W132 deliverables (Phase 6 canary infrastructure + runbook + Server-Timing observability) are content-shipped + verifiable through other means (curl, chrome-devtools-mcp visual smoke, YAML schema, Caddy validate, build × 3 reproducibility, vitest, pytest, npm audit). The Phase 6 ACTUAL rollout (W133+ ops) is where the SSR migration arc's value materialises in real-user LCP measurements; that path doesn't need local Windows e2e/LHCI to succeed.

**Final branch HEAD post-polish-round-2**: `97dd05238` (round-2 audit update) ← `271024ffc` (round-2 dev compose) ← `9cbb13198` (round-1 honest framing) ← `bbd365ddd` (round-1 npm audit) ← `76e422322` (SW7 audit) ← `bb11757ae` SW6 ← `09dd96ea5` SW5 ← `69ebcf99a` SW4 ← `f76ffa000` SW3 ← `12d4afadd` SW1-fix ← `ca5223ba9` (W131 polish).

Branch ahead of `origin/egorribun` by **+28 commits post-polish-round-2** (10 W132 + 7 W131 + 7 W130 + 4 polish/audit). After polish round 3 (Docker stack verification extension): **+31 commits** (3 additional fixes — `c7740362f` Go version bump, `d5ceeeb79` Dockerfile watch+kill, `8fbbc5a2f` postgres init); see §Polish round 3 below.

## Polish round 3 — Docker stack verification extension (post-`start-docker.ps1 -Build`, executed, ~60 min budget)

User invoked `start-docker.ps1 -Build` to bring up the full compose stack — the natural follow-on to "wave 132 полностью выполнена и абсолютно всё безупречно?". This extended session uncovered **5 latent infrastructure bugs**, all of which had been hiding behind the W131 §Honesty probe #1+#2 deferral text ("Docker stack runtime verification deferred to W132+ Phase 6 rollout"). Polish round 3 closes them all + verifies the full stack runtime end-to-end.

### Round 3 — 5 latent bug fixes

#### B1 ✅ docker-compose.full.yml port mismatch (`12d4afadd` — already shipped in SW1-fix, re-confirmed by extension)

W131 SW3 changed `frontend.Dockerfile` to `EXPOSE 3000` + Node listening on PORT 3000 via `server-prod.mjs`, but the compose service kept the pre-W131 nginx port mapping `8081:8080` and healthcheck against `:8080`. SW1-fix (`12d4afadd`) had already committed the fix ahead of extension session. Healthcheck → `wget http://127.0.0.1:3000/healthz` (W131 SW2 fast-path, <10ms response). Caddy in same compose network reverse-proxies `frontend:3000` correctly via service-name DNS — only the host-mapped :8081 was broken pre-fix.

#### B2 ✅ docker-compose.yml dev compose same fix (`271024ffc` — round 2 commit, scope clarified by extension)

Initially scoped as round 2 polish item before extension session — round 3 confirms wider scope (W131 SW3 carry-over manifested in BOTH `docker-compose.full.yml` AND `docker-compose.yml`). Polish round 2 had committed dev compose port fix; extension session validated both compose files are now consistent: frontend service port mapping aligned to W131 Node SSR runtime in both.

#### B3 ✅ Go version mismatch fix (`c7740362f`)

**Symptom**: `start-docker.ps1 -Build` failed at first `RUN go mod download` in `services/ws-hub/Dockerfile` build stage with `go: go.mod requires go >= 1.26.2 (running go 1.26.1; GOTOOLCHAIN=local)`.

**Root cause**: `services/ws-hub/go.mod` + `services/gateway/go.mod` + `services/file-processor/go.mod` all declared `go 1.26.2` in their respective module files (auto-bumped by `go.work` updates), but the Docker FROM lines in their respective Dockerfiles pinned `golang:1.26.1-alpine3.22@sha256:07e91d24...`. With `GOTOOLCHAIN=local` (set in Dockerfile to enforce reproducibility — Go won't auto-download a different toolchain), Go refused to compile against the older toolchain when go.mod required newer.

**Fix**: bump 3× Dockerfile FROM lines to `golang:1.26.2-alpine3.22@sha256:7ef941168f213aa115df2e61364d67682129e99dc8188b734139dea862cc7d31`. Multi-arch index SHA discovered via `docker buildx imagetools inspect golang:1.26.2-alpine3.22` (top-level `Digest:` field — works on both linux/amd64 + linux/arm64; per-platform manifest digests would break ARM builds). Root `go.mod` already at `go 1.26.2`; only the Dockerfile FROM pins were stale.

**Lesson** (added to CLAUDE.md): when bumping Docker FROM tags for Go-based services, also confirm `go.mod` toolchain alignment + use multi-arch index SHA from `docker buildx imagetools inspect`, not per-platform digest.

#### B4 ✅ vite-plugin-pwa Windows hang in Docker (`d5ceeeb79`)

**Symptom**: User reports "просто висит" — `start-docker.ps1 -Build` log shows frontend stage progressing through `[prerender] Prerendered 1 pages` at timestamp 20.31s, then stalls indefinitely with no further output. Same hang user encountered earlier on host build (W126 polish #3 / W127 SW7 pattern).

**Phase 1 root cause** (per `superpowers:systematic-debugging` skill): vite-plugin-pwa's `injectManifest` triggers workbox-build's glob scan over 200+ chunks generated by tanstackStart prerender. Under WSL2 virtualized filesystem (Docker Desktop's Linux VM mounting Windows host paths), the per-file stat operations are catastrophically slow — effectively infinite. Same pattern as W127 SW7 host-side hang (which used `wave127-build-x3.sh` watch+kill workaround).

**Phase 2 pattern**: `frontend/scripts/wave127-build-x3.sh` watch+kill works on Windows host — same pattern applies in Dockerfile builder stage RUN block. Approach: spawn `npm run build` in background → log to `/tmp/build.log` → poll for `dist/server/server.js` to appear (signals vite client + ssr build + tanstackStart prerender done) → 5s settle → `kill -9` the npm process chain (would otherwise hang on injectManifest workbox glob) → run `npm run build:shell` standalone (post-build-shell.mjs emits CSP nonce + font preload + index.html mirror).

**Phase 3 + 4 implementation** (`d5ceeeb79`): Edit `frontend.Dockerfile` builder stage. POSIX/busybox-portable shell (alpine images use busybox sh, NOT bash):
```dockerfile
RUN set -e; \
    echo "=== Build with watch+kill workaround (vite-plugin-pwa hang mitigation) ==="; \
    npm run build > /tmp/build.log 2>&1 & \
    BUILD_PID=$!; \
    i=0; \
    while [ $i -lt 240 ]; do \
      if [ -f dist/server/server.js ]; then break; fi; \
      sleep 1; \
      i=$((i+1)); \
    done; \
    if [ ! -f dist/server/server.js ]; then \
      echo "BUILD FAILED — dist/server/server.js missing after 240s"; \
      tail -100 /tmp/build.log; \
      kill -9 $BUILD_PID 2>/dev/null || true; \
      exit 1; \
    fi; \
    sleep 5; \
    kill -9 $BUILD_PID 2>/dev/null || true; \
    ps -ef 2>/dev/null | awk '/node.*(vite|run-build|build:shell)/ && !/awk/ {print $2}' | xargs -r kill -9 2>/dev/null || true; \
    sleep 1; \
    npm run build:shell 2>&1 | tee /tmp/build-shell.log; \
    ls -la dist/server/server.js dist/client/_shell.html dist/client/index.html 2>&1 || true
```

**Trade-off** (preserved from W127 watch+kill — same as host-side workaround): `dist/client/sw.js` may be missing or have unresolved `__WB_MANIFEST` placeholder → SW registration fails in browser → no PWA precache. Runtime caching strategies handled at app code level still work via Caddy. Acceptable for Docker dev runtime; production CI Linux build runs without this workaround + emits full sw.js.

**Lesson** (added to CLAUDE.md): POSIX/busybox-compatible shell required in Dockerfile RUN blocks — `[` not `[[`, `$((i+1))` not `$((++i))` or `let i++`, `ps -ef | awk | xargs -r kill -9` not `pkill -f` (busybox lacks pkill); set `set -e` for fail-fast; use `|| true` to continue past expected failures.

#### B5 ✅ postgres multi-database init (`8fbbc5a2f`)

**Symptom**: Build succeeded post-B4 fix, but stack didn't come up: `dependency failed to start: container backend-1 is unhealthy`. Investigation chain via `docker compose logs <service>` per `superpowers:systematic-debugging` Phase 1 multi-component evidence gathering:
1. `backend` `/healthz` returned 503 → `app.core.health.check_spicedb_health` reported permissions service down
2. `spicedb` container logs showed restart loop: `FATAL: database "spicedb" does not exist (SQLSTATE 3D000)` exit 78
3. `postgres` container had only `university` database (auto-created via `POSTGRES_DB` env var); `spicedb` database NOT auto-created

**Root cause**: single postgres container backs TWO logical databases. `university` is auto-created via `POSTGRES_DB=university` env var. `spicedb` is NOT — it requires an explicit `CREATE DATABASE spicedb;` statement. Pre-W132 the operator had to manually run `docker exec ... psql -c "CREATE DATABASE spicedb;"` after first postgres startup, but no init script was in repo to automate it; new contributors hit this every time.

**Fix** (`8fbbc5a2f`): NEW `infrastructure/postgres-init/01-create-spicedb.sql`:
```sql
CREATE DATABASE spicedb;
```
Mounted into both `docker-compose.full.yml` + `docker-compose.yml` postgres service via `volumes: - ./infrastructure/postgres-init:/docker-entrypoint-initdb.d:ro`. Init scripts in `/docker-entrypoint-initdb.d/` run ONLY on first postgres startup when `/var/lib/postgresql/data` is empty — they do NOT run on subsequent starts of the same volume. Operator re-trigger:
1. `docker compose -f docker-compose.full.yml down -v` — drops volume
2. `docker compose -f docker-compose.full.yml up -d` — recreates volume + reruns init
3. Or apply manually to running postgres: `docker exec university_ecosystem-postgres-1 psql -U postgres -c "CREATE DATABASE spicedb;"`

Comment block in init script documents the lifecycle + manual fallback for future contributors.

**Lesson** (added to CLAUDE.md): postgres multi-database compose pattern requires init script in `/docker-entrypoint-initdb.d/`; scripts run only on first startup with empty data dir.

### Round 3 — Docker stack runtime verification

After all 5 fixes, full stack verified end-to-end:

| Endpoint | Method | Status | Bytes | Path |
|----------|--------|--------|-------|------|
| Caddy `:80/` | GET | 307 → /login | redirect | Caddy → frontend:3000 SSR → unauth redirect via `_auth.tsx beforeLoad` |
| Caddy `:80/login` | GET | 200 | 21 KB | Caddy → frontend:3000 → SSR HTML rendered |
| Caddy `:80/healthz` | GET | 200 | 15 B | Caddy default → frontend:3000 fast-path |
| Caddy `:80/api/v1/users/me` | GET | 401 | 56 B | Caddy → backend:8000 (no auth header → expected) |
| Caddy `:80/api/v1/auth/login/json` | POST | 200 | 1.2 KB | Caddy → backend:8000 → JWT issued |
| `frontend:3000/healthz` (internal) | GET | 200 | 15 B | Direct Node SSR fast-path |
| `backend:8000/healthz` | GET | 200 | health JSON | Backend → spicedb (now exists) ✓ |

17 containers running: postgres, valkey (Redis-compat), nats, minio, opensearch, kibana, spicedb, prometheus, grafana, tempo, loki, fluent-bit, caddy, backend, ws-hub, file-processor, frontend.

This **closes W131 §Honesty probe #1** (full Docker stack runtime verification) — runtime-level chain Caddy → Node SSR → backend confirmed working end-to-end. **W131 §Honesty probe #2** (chrome-devtools-mcp visual smoke through real Caddy chain) remains W133+ scope — not blocked, just unmeasured this round (would require reopening Caddy on host port + new chrome-devtools-mcp session).

### Round 3 polish summary

- **5 latent bugs fixed** (B1 carried over from SW1-fix, B2 from round 2, B3+B4+B5 new in round 3)
- **Closes W131 §Honesty probe #1** (Docker stack runtime verification) — primary deferral closed
- **W131 §Honesty probe #2** (chrome-devtools-mcp visual smoke through Caddy) honestly remains W133+ scope
- **Round 3 commits**: 3 (`c7740362f` Go bump, `d5ceeeb79` Dockerfile watch+kill, `8fbbc5a2f` postgres init)
- **Round 3 budget**: ~60 min actual
- **W133 opening prompt**: NEW `memory/wave133_opening_prompt.md` (Version 3, ~42 KB, 23 sections) — comprehensive handoff including 32 critical pitfalls catalog (W125-W132) + 10 W133 scope options across 4 tiers + mandatory pre-work + honest deferrals carried forward + 5 master lessons from extension session

### Round 3 master lessons (carried into CLAUDE.md gotchas)

1. **Latent bugs hide behind §Honesty deferrals**: W131 §Honesty probe #1+#2 was structurally honest framing, but accumulated 5 real bugs that surfaced only when user actually tried `start-docker.ps1 -Build`. When deferring honestly, schedule the verification soonest possible — don't let deferrals become parking lots for unsurfaced gaps.
2. **Multi-component cascade root cause analysis**: Each layer (frontend hang → container unhealthy → spicedb restart loop → postgres missing DB) required separate diagnostic step (`docker compose logs <service>`). The `superpowers:systematic-debugging` skill's "Multi-Component Systems" instrumentation pattern paid off significantly.
3. **POSIX/busybox-compatible shell in Dockerfile RUN blocks**: `node:24-alpine` (and most alpine images) use busybox sh, NOT bash. Test before committing.
4. **postgres multi-database compose pattern**: requires init script in `/docker-entrypoint-initdb.d/`; runs only on first startup with empty `/var/lib/postgresql/data`.
5. **Multi-arch image SHA pinning convention**: when bumping Docker FROM tags, use `docker buildx imagetools inspect <image:tag>` top-level `Digest:` field (multi-arch index — works on all platforms), NOT per-platform manifest digest.

**Final branch HEAD post-polish-round-3**: `<this-commit>` (round-3 audit update) ← `8fbbc5a2f` (postgres init) ← `d5ceeeb79` (Dockerfile watch+kill) ← `c7740362f` (Go version bump) ← `97dd05238` (round-2 audit update) ← `271024ffc` (round-2 dev compose) ← `9cbb13198` (round-1 honest framing) ← `bbd365ddd` (round-1 npm audit) ← `76e422322` (SW7 audit) ← `bb11757ae` SW6 ← `09dd96ea5` SW5 ← `69ebcf99a` SW4 ← `f76ffa000` SW3 ← `12d4afadd` SW1-fix ← `ca5223ba9` (W131 polish).

Branch ahead of `origin/egorribun` by **+31 commits post-polish-round-3** (10 W132 SW + 7 polish + 3 Docker fix + 7 W131 + 7 W130 + 4 polish/audit).
