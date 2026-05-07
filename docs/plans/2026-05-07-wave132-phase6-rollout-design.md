# Wave 132 — Phase 6 SSR canary rollout infrastructure (design doc)

> Captured post-execution per the `superpowers:brainstorming` skill workflow. Plan-mode plan file lives at `~/.claude/plans/wave-131-closed-proud-whistle.md` (auto-generated session name); this doc consolidates the design content for git-tracked reference.
>
> Execution outcome documented at `docs/audits/AUDIT_WAVE132.md`.

## Context

Wave 131 closed Phase 4 of the W125-designed SSR migration arc — production frontend container migrated nginx static-serve → Node 24 Alpine SSR runtime via custom `server-prod.mjs` wrapper, Caddy multi-service routing, k8s manifests aligned to port 3000, cookie SameSite=Lax. ≥6 SSR routes threshold met (W128 /dashboard + W129 × 4 + W130 /schedule).

W132 ships **Phase 6 of the W125 design** — the canary-rollout infrastructure that turns the W131 deploy capability into a measurable user-facing LCP improvement. Per user-approved AskUserQuestion at session start: scope is **"Local + author + runbook"** with no staging/prod cluster access, all artifacts authored locally, real canary deploy is W133+ ops work.

Side-benefit: W131 §Honesty probe #1+#2 (Docker stack runtime verification deferred) closure attempted via SW1 verification step.

## Constraints

- **Local-only**: dev workstation Windows + Docker Desktop; no live k8s cluster API server
- **Author-only**: artifacts ship to git; cluster apply happens in W133+ ops
- **Bundle invariant**: PROD `dist/client/assets/index-KalQn95O.js` must stay BYTE-IDENTICAL to W131 baseline (138,974 bytes) — all changes server-side / infra
- **SSR routes preserved**: 6 routes (W128 /dashboard + W129 × 4 + W130 /schedule); /map + /activity stay `ssr: 'data-only'`; 4 sibling explicit `ssr: false` routes preserved (messenger × 2, profile, settings)
- **Test baselines preserved**: vitest 988p/12s/0f, pytest backend slice 75p+/0f, npm audit 0, Cargo.lock no drift
- **Polish-pass budget**: 60-90 min per `feedback_perfectionism.md` "безупречно?" probe anticipation
- **W131 §Honesty probe carry-forwards**: 12 caveats; 2 (Docker stack #1+#2) addressable; 1 (cookie SSO #10) documented in runbook; rest carried unchanged

## Approach

### Canary pattern: SPA-fallback edge-based via Caddy `lb_policy weighted_round_robin`

Two upstream pools live alongside during canary stages 0-5:
- `frontend-stable:8080` — pre-W125 nginx + SPA bundle (operator builds + pins legacy image during canary prep)
- `frontend:3000` — W131 Node SSR runtime (server-prod.mjs)

5-stage progression operator-adjustable in runbook:
- Stage 0 pre-canary: 100/0 stable-only — Caddyfile apply = identity change
- Stage 1: 90/10 (24-48h soak)
- Stage 2: 75/25 (12-24h)
- Stage 3: 50/50 (12-24h)
- Stage 4: 25/75 (6-12h)
- Stage 5: 0/100 (24h soak)
- Stage 6 cleanup: delete `frontend-stable` + revert single-upstream Caddy block

Rollback path of last resort: Caddy weight flip back to `100 0` (~50 ms config hot-reload, no Pod cycling).

### Why edge-based, not service-mesh / feature-flag

- **Caddy edge canary**: leverages existing infrastructure; zero new operator dependency. Single line `lb_policy weighted_round_robin <S> <SSR>` is the weight knob.
- **k8s service mesh** (Istio / Linkerd / Argo Rollouts / Flagger): added complexity premature for a single-developer project's first canary.
- **Feature flag canary**: requires app-level branching — would break the W125-W131 architecture (server.ts has no concept of "this user gets SSR, that one gets SPA").

W125 design § Phase 6 step 5 explicitly documented "Caddy config flip to serve old SPA build" as the rollback strategy — SPA-fallback pattern matches.

### Why two Deployments (not blue/green between SSR versions)

- **Two-Deployment SPA-fallback**: gives operator a known-good rollback target. Caddy weight flip 0/100 → 100/0 is instant; reverting a Deployment image takes minutes + risks ImagePullBackOff. Stage 6 cleanup deletes `frontend-stable` only after 100% canary completion.
- **Blue/green between SSR versions**: would lose the SPA fallback safety net — if Stage 1 SSR has unexpected issues at scale, no quick path back to known-good SPA.

### Why `/sw.js` always to frontend-ssr

Service worker scope rules require single origin + single SW file. If Caddy round-robined `/sw.js` between stable + ssr, browsers would mix two service workers across navigations and could install the wrong one. The W131 SW4 explicit `/sw.js → frontend:3000` block is preserved + the new `lb_policy` block carves around it.

### Initial Caddy weights `100 0`

Caddyfile apply at Stage 0 is an **identity change** — operator can deploy the new config without traffic shift. Canary triggers via runbook command flip (edit weights → ConfigMap → Caddy reload), not by default. This decouples *infrastructure rollout* from *canary execution*, lowering operator mental load.

### Server-Timing observability

Each SSR response from the Node SSR pool emits:

```
Server-Timing: ssr;dur=<float>;desc="ssr-render"
```

`dur` is wall-clock time in `handler.fetch(request)` (tanstackStart router + matched-route render + loader chain) measured via `performance.now()` for sub-ms precision. Skipped for `/healthz` (W131 SW2 fast path stays clean) and static assets (W131 SW7 short-circuit before SSR layer).

Operators identify SSR-pool responses during canary via header presence (filter responses by `Server-Timing IS NOT NULL` in any HTTP-aware analyzer). Aggregated `dur` distribution per stage feeds advance/abort decisions.

## File inventory

### Created

- `k8s/frontend/canary/deployment-stable.yaml` — template legacy fallback Deployment + Service + PDB; operator sets `${LEGACY_SPA_IMAGE}` placeholder during canary prep
- `k8s/frontend/canary/canary-flip-strategies.md` — Caddy weight progression reference + flip commands
- `docs/CANARY_ROLLOUT_PHASE6.md` — comprehensive operator runbook (DEPLOY.md naming convention)
- `docs/plans/2026-05-07-wave132-phase6-rollout-design.md` — this design doc
- `docs/audits/AUDIT_WAVE132.md` — wave-close audit
- `memory/wave132_backlog.md` — closed status
- `memory/wave133_opening_prompt.md` — handoff

### Modified

- `services/caddy/Caddyfile` — single-upstream → `lb_policy weighted_round_robin` block + initial weights `100 0` + active probe + passive `fail_duration`
- `frontend/scripts/server-prod.mjs` — Server-Timing middleware (~30 LoC); `pipeWebResponse` extra headers arg
- `k8s/frontend/deployment.yaml` — explicit `RollingUpdate` strategy with `maxSurge: 25%`, `maxUnavailable: 0`, `progressDeadlineSeconds: 600`
- `docker-compose.full.yml` — W131 SW3 carry-over fix: port mapping `8081:8080 → 8081:3000` + healthcheck path `:8080/ → :3000/healthz`
- `CLAUDE.md` — Audit Trail W132 row + new gotchas
- `memory/MEMORY.md` — W132 row prepended (≤200 chars per index entry)
- `docs/audits/INDEX.md` — W132 entry + W129 → archive

### Verified but NOT modified

- `infrastructure/Caddyfile` (docker-compose mount) — local stack stays single-target SSR; canary is operational, not local-test
- `k8s/frontend/network-policy.yaml`, `pdb.yaml`, `hpa.yaml` — selectors match existing `frontend` Service; `frontend-stable` template carries its own canary-subfolder PDB stub
- `frontend/src/server.ts` — Server-Timing middleware lives in server-prod.mjs, not the tanstackStart entry
- `frontend.Dockerfile` — preserved (W131 SW3)

## Data flow / Rollout flow

```
client request
    │
    ▼
caddy:443 ──[canary path]──► handle / { reverse_proxy {
                                lb_policy weighted_round_robin <stable> <ssr>
                                to frontend-stable:8080 frontend:3000
                                health_uri /healthz health_interval 10s
                                fail_duration 30s unhealthy_status 5xx
                              } }
                                                  │
                              ┌───────────────────┴────────────────────┐
                              ▼                                        ▼
                  frontend-stable Service :8080            frontend Service :80 (targetPort 3000)
                              │                                        │
                              ▼                                        ▼
                  M Pods: nginx + pre-W125 SPA            N Pods: Node 24 Alpine + W131 server-prod.mjs
                              │                                        │
                              ▼                                        ▼
                  GET / → 200 SPA shell                    GET / → 307 → /login (auth-at-edge)
                  GET /healthz → 200 OK (operator-added)   GET /healthz → 200 {"status":"ok"} (W131 SW2)
                                                            GET /login → 200 + Server-Timing
                                                            GET /assets/<hashed>.js → 200 + immutable
```

## Error handling / Rollback

8 ranked failure modes documented in `docs/CANARY_ROLLOUT_PHASE6.md` § 4 with W131/W132 mitigations mapped:

1. Hydration mismatch at scale → W127 SW2-5 cookie-mirror; rollback + capture stack traces
2. Cookie SameSite=Lax breaks SSO → `SECURITY_COOKIE_SAMESITE_OVERRIDE=strict` env var (W131 SW6)
3. Service worker collision → W131 SW4 `/sw.js → frontend:3000` always (single source)
4. VITE_LHCI bypass leaks to prod → pre-deploy gate `grep -l "lhci-mock-user" dist/assets/*.js`
5. Push subscription invalidation → 24-48h soak observation
6. Caddy hot-reload transient 5xx → expected ~50-200ms window
7. Node SSR memory leak → k8s memory limit + HPA + scheduled restart
8. ws-hub reconnect storm → preStop sleep:10 + ws-hub backoff

Rollback decision tree: any abort criterion fires → Caddy weight flip back to `100 0` → 30s `fail_duration` window → all traffic returns to stable pool.

## Testing / Verification

### Code gates (every SW)
- `tsc 0`, `eslint 0 max-warnings=0`
- `vitest 988p / 12s / 0f` preserved
- `pytest backend slice 75p+/0f` preserved
- `npm audit 0`
- Cargo.lock no drift

### Build invariant (SW7 final)
- PROD `dist/client/assets/index-KalQn95O.js` 138,974 bytes BYTE-IDENTICAL to W131 baseline
- `_shell.html` 65,872 bytes BYTE-IDENTICAL

### Integration verification (SW1)
- `docker compose -f docker-compose.full.yml up -d` after `docker compose down -v && docker buildx prune -af`
- chrome-devtools-mcp visual smoke on 8 routes through real Caddy → Node SSR → backend chain
- 0 React hydration errors per route

### LHCI baseline (SW2)
- `npm run lhci:windows` 9-URL × 3-run via `lhci-windows-fallback.mjs` (W120 SW1 wrapper)
- Comparison to W124 SW4 pre-SSR baseline

### Caddy + k8s syntax (SW3, SW4)
- `caddy validate` (W131 polish A6 stripped-block method)
- `yaml.safe_load_all` on all k8s/frontend manifests

### Server-Timing (SW5)
- `node ./scripts/server-prod.mjs` + curl tests:
  - `/healthz` no Server-Timing
  - `/login` Server-Timing emitted
  - `/assets/<hashed>.js` no Server-Timing (static layer skip)

### Runbook (SW6)
- Cross-ref grep verification (all CLAUDE.md gotchas referenced exist)
- Command examples runnable against current state

## Out of scope (explicit)

- Real `kubectl apply` of canary manifests
- Caddy weight flip on live cluster
- Sentry alert thresholds wired with production-real values
- LHCI baseline for SSR pool serving real traffic
- Push subscription recovery flow under SW upgrade
- WebSocket reconnect storm test under canary load
- `nitro()` plugin re-evaluation
- Sequential `/users/me` + `/schedule` lessons SSR
- `/profile` or `/settings` SSR enablement
- vite-plugin-pwa Windows hang structural fix
- `frontend/nginx.conf` deletion (kept as Phase 6 rollback safety)
- MEMORY.md compaction

## Sources

- [`docs/plans/2026-05-01-wave125-ssr-design.md`](2026-05-01-wave125-ssr-design.md) § Phase 6 — design source
- [`docs/plans/2026-05-06-wave131-phase4-deploy-design.md`](2026-05-06-wave131-phase4-deploy-design.md) — Phase 4 prerequisites
- [`docs/audits/AUDIT_WAVE131.md`](../audits/AUDIT_WAVE131.md) §Honesty probe #1+#2 — closed by W132 SW1 (Docker stack runtime verification)
- [`docs/audits/AUDIT_WAVE132.md`](../audits/AUDIT_WAVE132.md) — execution outcome
- `services/caddy/Caddyfile` (W132 SW3) — active canary config
- `k8s/frontend/canary/canary-flip-strategies.md` (W132 SW4) — operator quick-reference
- `frontend/scripts/server-prod.mjs` (W131 SW1+SW7, W132 SW5) — Node SSR runtime
- `memory/feedback_perfectionism.md` — anticipate "безупречно?" polish probe
- `memory/feedback_planning_estimates.md` — range estimates framework
