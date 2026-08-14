# Phase 6 — SSR canary rollout runbook (Wave 132)

> Operational runbook for the W125–W131 SSR migration arc's canary rollout phase. Authored Wave 132 SW6 in author-only mode (no live cluster access on dev workstation); cluster operator follows this procedure during the actual rollout. Cross-references the canary infrastructure shipped in W132 SW3-SW5.

> **Archived procedure (2026-08-13):** the checked-in Caddy baseline now routes
> only to the deployed `frontend` service. The `frontend-stable` service and its
> weighted route are not part of the current Compose or Helm topology. Do not
> run the commands below against the default Caddyfile. A future canary must
> first provision both upstreams and prepare a temporary, reviewed Caddy
> configuration derived from the then-current baseline.

## At a glance

This document preserves the project's first canary rollout procedure. The migration target was the SPA → Node SSR transition shipped over W125-W131. Phase 4 (W131) prepared the deploy infrastructure — Node 24 Alpine runtime, Caddy multi-service routing, cookie SameSite=Lax. Phase 6 (W132) authored the historical canary infrastructure — Caddy `lb_policy weighted_round_robin`, k8s rolling-update strategy, `frontend-stable` Deployment template, Server-Timing observability — and wrote this runbook. It is retained as design history, not as a runnable current-state procedure.

The expected user-facing outcome: authenticated route LCP drops from ~12 s (SPA) to ~2-4 s (SSR) on mobile devtools throttling, per W125 design § Phase 6 step 1.

The rollback path of last resort is **Caddy weight flip back to `100 0` + 30 s wait for `fail_duration` to expire**. Investigate after; do not resume mid-stage.

---

## Architecture map

```
client request
    │
    ▼
caddy:443 ──► handle / { reverse_proxy {
                  to frontend-stable:8080 frontend:3000      ← upstream pool
                  lb_policy weighted_round_robin <S> <SSR>   ← weight knob
                  health_uri /healthz health_interval 10s    ← active probe
                  fail_duration 30s unhealthy_status 5xx     ← passive probe
              } }
                            │
            ┌───────────────┴────────────────────┐
            ▼                                    ▼
   frontend-stable Service :8080        frontend Service :80 (targetPort 3000)
   selector: app.k8s.io/name            selector: app.k8s.io/name
            =frontend-stable                     =frontend
            │                                    │
            ▼                                    ▼
   M Pods: nginx + pre-W125 SPA         N Pods: Node 24 Alpine + W131 server-prod.mjs
   image: ${LEGACY_SPA_IMAGE}           image: registry.example.com/frontend:${IMAGE_TAG}
   (operator builds during prep)        (W131 SW3 frontend.Dockerfile)
            │                                    │
            ▼                                    ▼
   GET / → 200 SPA shell HTML           GET / → 307 → /login (auth-at-edge)
   GET /healthz → 200 OK (operator      GET /healthz → 200 {"status":"ok"} (W131 SW2 fast path)
     adds /healthz endpoint to nginx     GET /login → 200 + Server-Timing: ssr;dur=…
     config; see "Pre-canary" step 4)    GET /assets/<hashed>.js → 200 + immutable cache
```

Key files in this canary system:
- Historical canary Caddy configuration — removed after the rollout; any future
  weighted configuration must be created as a temporary overlay from the
  current [`services/caddy/Caddyfile`](../services/caddy/Caddyfile)
- [`k8s/frontend/deployment.yaml`](../k8s/frontend/deployment.yaml) — Node SSR Deployment (W131 SW3) + Service `frontend`; W132 SW4 added explicit RollingUpdate strategy
- [`k8s/frontend/canary/deployment-stable.yaml`](../k8s/frontend/canary/deployment-stable.yaml) — template legacy fallback Deployment + Service + PDB
- [`k8s/frontend/canary/canary-flip-strategies.md`](../k8s/frontend/canary/canary-flip-strategies.md) — quick-reference flip commands
- [`frontend/scripts/server-prod.mjs`](../frontend/scripts/server-prod.mjs) — Node SSR runtime + W132 SW5 Server-Timing emission

---

## 1. Prerequisites

Before initiating Stage 0 (pre-canary identity apply), confirm operator access to:

- **k8s cluster** with `kubectl` configured for the production namespace (`university-ecosystem`).
- **Container registry** with push permissions for both `registry.example.com/frontend` (W131 image) and `registry.example.com/frontend-stable` (legacy fallback image — operator builds in step 4 below).
- **Caddy ConfigMap** management — either direct `kubectl create configmap … --dry-run=client | kubectl apply -f -` or via your Helm/Argo CD/Flux chart (adjust commands accordingly).
- **Sentry** project access — read alerts; baseline error rates (Stage 0 step 8 captures these).
- **Grafana** / **Prometheus** access — Caddy access log dashboard, Pod metrics, ws-hub reconnect rate, webpush subscription count.
- **W131 §Honesty probe #10 emergency rollback knob** — ability to set `SECURITY_COOKIE_SAMESITE_OVERRIDE=strict` env var on the backend Deployment + restart pods (used only if SSO callbacks break under SameSite=Lax — see § Failure modes below).

If any of these are missing, **STOP** and acquire access before proceeding. Canary rollouts under partial visibility are dangerous.

---

## 2. Pre-canary checklist (one-time, ~2-4h)

### Step 1 — Verify W131 baseline is deployed

```bash
kubectl -n university-ecosystem get deployment frontend -o jsonpath='{.spec.template.spec.containers[0].image}'
# Expect: registry.example.com/frontend:<W131-or-later-tag>
kubectl -n university-ecosystem rollout status deployment frontend
# Expect: deployment "frontend" successfully rolled out
kubectl -n university-ecosystem get pods -l app.kubernetes.io/name=frontend
# Expect: all pods Running + READY 1/1
```

If the W131 build is not yet deployed, deploy it via your normal CI/CD path **before** starting the canary. The canary procedure assumes the SSR pool is already running production traffic at 100%.

### Step 2 — Capture pre-canary LHCI baseline

Run LHCI 9-URL × 3-run sweep on the current production state (before any canary changes):

```bash
cd frontend
LHCI_TARGET_URL=https://your-domain.tld npm run lhci -- --collect.numberOfRuns=3
```

Save the report to a tracked location (e.g. `docs/audits/AUDIT_WAVE132_PRECANARY_LHCI.md`). After Stage 5 completes, this becomes the post-canary comparison baseline. Median Perf, CLS, LCP per URL are the numbers that matter for the LHCI gate ratchet at Stage 6 cleanup.

### Step 3 — Apply W132 SW4 deployment.yaml change (rolling-update strategy)

```bash
kubectl -n university-ecosystem apply -f k8s/frontend/deployment.yaml
kubectl -n university-ecosystem rollout status deployment frontend
```

The W132 SW4 change adds explicit `strategy.rollingUpdate.maxUnavailable: 0` — Pod cycling during canary stages won't drop SSR-pool capacity below current replica count. No traffic shift; this is a strategy-only change.

### Step 4 — Build the legacy SPA fallback image

The `frontend-stable` pool needs an image that reproduces the pre-W125 SPA behavior. Build from a known-stable commit (e.g. tag `pre-w125-spa` if you keep one, or commit `b2f6960aa` = W123 SW3 known-good per W125 design § hand-off notes):

```bash
git checkout -b canary-stable-build pre-w125-spa  # or specific commit
```

Add a `/healthz` endpoint to the legacy nginx config — Caddy's active health probe (W132 SW3 `health_uri /healthz`) will mark the pool unhealthy without it:

```nginx
# In frontend/nginx.conf (or wherever the legacy nginx config lives), add:
server {
    listen 8080;
    # ... existing SPA serving config ...
    location = /healthz {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
```

Build + push:

```bash
docker build -t registry.example.com/frontend-stable:pre-w125-spa -f frontend.Dockerfile.legacy .
docker push registry.example.com/frontend-stable:pre-w125-spa

# Return to current branch:
git checkout egorribun  # or your main branch
```

### Step 5 — Apply frontend-stable Deployment template

Set the image reference in the canary template + apply:

```bash
# Replace the placeholder in the manifest:
sed -i 's|${LEGACY_SPA_IMAGE}|registry.example.com/frontend-stable:pre-w125-spa|' \
  k8s/frontend/canary/deployment-stable.yaml

kubectl -n university-ecosystem apply -f k8s/frontend/canary/deployment-stable.yaml
kubectl -n university-ecosystem rollout status deployment frontend-stable

# Verify both pools healthy:
kubectl -n university-ecosystem get pods -l app.kubernetes.io/name=frontend
kubectl -n university-ecosystem get pods -l app.kubernetes.io/name=frontend-stable

# Verify Service endpoints:
kubectl -n university-ecosystem get endpoints frontend frontend-stable
# Both should show non-empty ENDPOINTS columns matching pod IPs.

# Smoke-test legacy /healthz endpoint:
kubectl -n university-ecosystem run -it --rm curl-test --image=curlimages/curl --restart=Never -- \
  curl -sI http://frontend-stable:8080/healthz
# Expect: HTTP/1.1 200 OK
```

If `/healthz` returns 404 from frontend-stable, your nginx config didn't include the endpoint — revert step 4 and rebuild with the `location = /healthz` block.

### Step 6 — Apply the W132 SW3 Caddy config (Stage 0 = identity change)

```bash
# Historical example only: apply the reviewed temporary canary Caddyfile:
kubectl -n university-ecosystem create configmap caddy-config \
  --from-file=Caddyfile=/secure/operator-workdir/Caddyfile.canary \
  --dry-run=client -o yaml | kubectl apply -f -

# Trigger Caddy hot-reload:
kubectl -n university-ecosystem rollout restart deployment caddy
kubectl -n university-ecosystem rollout status deployment caddy

# Verify Caddy logs show new config loaded:
kubectl -n university-ecosystem logs -l app=caddy --tail=20 | grep -i "reload\|reverse_proxy"
```

The temporary canary Caddyfile weights are `lb_policy weighted_round_robin 100 0` — stable serves all traffic; SSR pool gets zero. This is **Stage 0 identity change**: applied config differs from pre-W132 only in routing-config syntax, not in observed traffic distribution. Verify via:

```bash
# Run for ~5 min, then sample the access log:
kubectl -n university-ecosystem logs -l app=caddy --tail=500 \
  | grep -E '"upstream":' | grep -oE '"[^"]+:[0-9]+"' | sort | uniq -c

# Expect: ~100% requests to "frontend-stable:8080"
# Expect: 0 requests to "frontend:3000" (excepting health probes)
```

If you see any traffic landing on `frontend:3000`, **STOP** and investigate — Stage 0 is supposed to be SSR-traffic-zero. Common cause: the W131 SW4 explicit `/sw.js → frontend:3000` block bypasses the lb_policy block (intentional — service worker scope rules) — that's expected and fine. Anything else needs investigation.

### Step 7 — Smoke-test the canary infrastructure

Hit production from your dev machine + verify the headers:

```bash
# /healthz — should return W131 SW2 fast path; either pool answers
curl -sI https://your-domain.tld/healthz | head -5

# /login — should be served by stable pool at Stage 0 (no Server-Timing)
curl -sI https://your-domain.tld/login | grep -iE "server|server-timing"
# Expect: server: header from nginx (no Server-Timing — stable pool)

# /sw.js — always served by frontend-ssr per W131 SW4 explicit block
curl -sI https://your-domain.tld/sw.js | grep -iE "service-worker-allowed|server-timing"
# Expect: service-worker-allowed: /  +  Server-Timing emitted (SSR pool)
```

The `/sw.js` Server-Timing presence at Stage 0 confirms the SSR pool is healthy + reachable; this is the single endpoint guaranteed to hit `frontend:3000` regardless of canary weights.

### Step 8 — Capture Stage 0 baseline metrics

Wait **24 hours** under Stage 0 (stable-only) traffic, then capture:

| Metric | Source | Stage 0 value (fill in) |
|--------|--------|-------------------------|
| Sentry error rate (frontend transactions, 24h median) | Sentry → Performance | _____% |
| LCP p75 on /dashboard, /events, /news | LHCI baseline (step 2) or RUM | _____ ms |
| Caddy 5xx rate (24h) | Grafana / access log | _____% |
| webpush subscription_active count | Backend metrics endpoint | ______ |
| ws-hub reconnect rate (events/min) | Prometheus | ____/min |

**These numbers become the abort thresholds for stages 1-5**. The runbook's threshold table below uses placeholder values (e.g. "error rate < 0.5%") — operator must replace placeholders with concrete numbers derived from this Stage 0 baseline before advancing.

If any baseline metric is already alarming (e.g. error rate > 1%), **STOP** and resolve the underlying issue before starting the canary. Canary stages amplify pre-existing issues; do not muddle the signal by starting from a degraded baseline.

---

## 3. Canary stages 1-5

For each stage:
1. Apply the new weight values via the [flip command](../k8s/frontend/canary/canary-flip-strategies.md#flip-command)
2. Verify via Caddy access log that distribution matches new weights (within ±5% tolerance over a 1h sample)
3. Begin soak observation (per-stage duration in the table)
4. Capture per-stage metrics throughout soak
5. Decide at end of soak: **advance** to next stage, or **abort** to Stage 0

Per-stage advance/abort criteria:

| Stage | Stable | SSR | Soak | Promote when (vs. Stage 0 baseline) | Abort if |
|------:|-------:|----:|------|-------------------------------------|----------|
| 1 | 90 | 10 | 24-48h | Sentry error rate increase < 0.5pp; LCP p75 SSR pool ≤ 4s; no WS disconnect spike | Error rate ≥ +1pp; LCP p75 ≥ 6s; 5xx rate +50% over baseline |
| 2 | 75 | 25 | 12-24h | Stage 1 metrics held under 2.5× SSR load | same |
| 3 | 50 | 50 | 12-24h | Push subscription delta < 5%; Stage 2 metrics held | push subscription drop ≥ 5% pre-canary count |
| 4 | 25 | 75 | 6-12h | Stage 3 metrics held | same |
| 5 | 0 | 100 | 24h | Sentry stable; LHCI numbers in range of expected SSR LCP gain | same |

> **Note**: thresholds above are **placeholders**. Replace with concrete numbers derived from your Stage 0 baseline before advancing. The W125 design Phase 6 § "Risks" inventory anticipated this — see also `feedback_perfectionism.md` "be specific, don't paper over with future-wave labels".

### Stage advance command pattern

The single line that changes per advance is in the temporary operator-managed canary Caddyfile:

```caddy
lb_policy weighted_round_robin <stable> <ssr>
```

Edit + apply as documented in [`k8s/frontend/canary/canary-flip-strategies.md`](../k8s/frontend/canary/canary-flip-strategies.md#flip-command). After hot-reload, sample the access log for ~10 minutes to confirm distribution matches:

```bash
# After flip to Stage 1 (90/10):
kubectl -n university-ecosystem logs -l app=caddy --tail=2000 \
  | grep -E '"upstream":' | grep -oE '"[^"]+:[0-9]+"' \
  | sort | uniq -c | sort -rn

# Expected (within ±5% tolerance):
#   ~90% "frontend-stable:8080"
#   ~10% "frontend:3000"
```

`Server-Timing` headers from the SSR pool are tagged via W132 SW5 — operator can also filter by header presence to identify SSR-pool responses in any HTTP-aware log analyzer.

### Stage soak monitoring queries

During each stage's soak, watch:

```bash
# Sentry frontend errors per upstream (filter by Server-Timing header presence)
# Sentry UI: Performance → Filter "tag:Server-Timing IS NULL" vs "IS NOT NULL"

# Caddy 5xx rate per upstream (Caddy access log)
kubectl -n university-ecosystem logs -l app=caddy --since=1h \
  | jq -r 'select(.status >= 500) | .upstream' \
  | sort | uniq -c | sort -rn

# SSR pool latency distribution from Server-Timing
# (Caddy access log captures Server-Timing if you add it to the log format;
# alternative: instrument client-side RUM to capture Server-Timing.dur)

# webpush subscription continuity (backend metric)
kubectl -n university-ecosystem exec -it backend-<pod-id> -- \
  curl -sf http://127.0.0.1:8000/metrics | grep webpush_subscription_active

# ws-hub reconnect rate (Prometheus)
# Query: rate(ws_hub_reconnects_total[5m])
```

If any abort criterion fires during soak, immediately execute the rollback procedure below.

---

## 4. Rollback procedure (any stage)

The W125 design § Phase 6 step 5 documented this as the "Caddy config flip to serve old SPA build" rollback. Execution time: **~50 ms config reload + 30 s `fail_duration` window** before the stable pool fully reabsorbs traffic.

```bash
# Edit /secure/operator-workdir/Caddyfile.canary:
#   Change `lb_policy weighted_round_robin X Y` back to `lb_policy weighted_round_robin 100 0`

kubectl -n university-ecosystem create configmap caddy-config \
  --from-file=Caddyfile=/secure/operator-workdir/Caddyfile.canary \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n university-ecosystem rollout restart deployment caddy
kubectl -n university-ecosystem rollout status deployment caddy

# Verify the access log shows traffic returning to stable pool:
kubectl -n university-ecosystem logs -l app=caddy --since=2m \
  | grep -E '"upstream":' | grep -oE '"[^"]+:[0-9]+"' | sort | uniq -c
# Expect: ~100% "frontend-stable:8080" (excepting health probes + /sw.js)
```

After rollback, **DO NOT** resume canary mid-stage. Always:
1. Capture failure mode from Sentry / Grafana / logs
2. File a follow-up issue with root cause + reproduction steps
3. Fix in staging environment
4. Re-attempt from **Stage 1** (re-establish baseline confidence; never trust the Stage N+1 advance from a state that triggered abort)

### Failure mode catalog (W132 SW6 Phase 6 anticipated)

| # | Symptom | Probable cause | Mitigation |
|---|---------|----------------|------------|
| 1 | Sentry React error spike `Text content does not match server-rendered HTML` | Hydration mismatch at scale (theme, lang, browser-only state visible only under load) | Rollback to 100/0; capture stack traces from first 100 errors; fix in staging via W127 SW2-5 cookie-mirror or `suppressHydrationWarning` audit |
| 2 | Users redirected to /login after SSO callback | Cookie SameSite=Lax (W131 SW6) blocks access_token_v2 cookie on the cross-site SSO callback | Set `SECURITY_COOKIE_SAMESITE_OVERRIDE=strict` env var on backend Deployment + `kubectl rollout restart deployment backend`; rollback canary; re-investigate SSO flow under Lax |
| 3 | Blank page / duplicate fetches; SW console `redundant` state | Service worker collision (old SW from cached SPA shell + new SW from SSR build) | W131 SW4 `/sw.js → frontend:3000` always (single source) — verify via curl on `/sw.js` during prep step 7. If users hit this, instruct hard reload (Ctrl+Shift+R); browser will fetch the correct SW |
| 4 | All users see authenticated content as `lhci-mock-user` (SECURITY INCIDENT) | VITE_LHCI build flag leaked to prod build (auth bypass tree-shake invariant violated) | **PRE-DEPLOY GATE**: `grep -l "lhci-mock-user" dist/assets/*.js` MUST return empty for prod build before push. CI build-time check enforced via npm script. Failure = block deploy. |
| 5 | Users stop receiving push notifications | Service worker upgrade invalidates webpush subscription | Stage 1 24-48h soak observes push delivery rate. No code mitigation (browser-controlled). User-facing recovery: app shows "re-subscribe" prompt. Expected ~5% subscription drop is acceptable; > 10% triggers rollback per Stage 3 abort |
| 6 | Caddy reload causes brief 5xx spike (~50-200ms) | In-flight requests during config hot-reload | Caddy reload is graceful (in-flight on old config). Schedule weight flips during low-traffic windows; document expected window in operations log |
| 7 | OOMKill on Node SSR Pods | Memory leak in long-running Node SSR worker | k8s memory limit 512Mi (W131 SW5) + HPA + scheduled rollout restart cron post-100%. Server-Timing data correlates render duration to memory growth |
| 8 | ws-hub reconnect rate spike during stage transitions | WebSocket clients reconnect when their pod is replaced | preStop sleep:10 (W131 SW5) + ws-hub backoff + tightened rollingUpdate `maxUnavailable: 0` (W132 SW4). Spike is expected at stage transitions; magnitude should match prior preStop-driven cycling |

Each failure mode above maps to either a W131/W132 mitigation already shipped or an operator action documented in this runbook. None require new code work to address during canary.

---

## 5. Stage 6 — post-100% cleanup

After Stage 5 (0/100) ran cleanly for at least 24 h:

### Step 1 — Delete the canary fallback pool

```bash
kubectl -n university-ecosystem delete -f k8s/frontend/canary/deployment-stable.yaml
# Removes: Deployment + Service + PodDisruptionBudget for frontend-stable

# Verify:
kubectl -n university-ecosystem get all -l wave=w132-canary
# Expect: No resources found
```

### Step 2 — Revert Caddy to single-upstream block

Edit the temporary operator-managed canary Caddyfile. Replace its `lb_policy weighted_round_robin` block in the `default` handle with the current single-upstream form from `services/caddy/Caddyfile`. Then apply:

```bash
kubectl -n university-ecosystem create configmap caddy-config \
  --from-file=Caddyfile=/secure/operator-workdir/Caddyfile.canary \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n university-ecosystem rollout restart deployment caddy
```

### Step 3 — Re-baseline LHCI gates

The W124 SW4 ratchet methodology — `floor = min(measured medians) − 0.05 safety margin` — applies. Run a fresh 9-URL × 3-run sweep on the post-cleanup state:

```bash
cd frontend
LHCI_TARGET_URL=https://your-domain.tld npm run lhci -- --collect.numberOfRuns=3
```

Update `frontend/scripts/run-lhci.mjs` thresholds:
- **Perf**: pre-W125 was `error@0.40`; post-Phase-6 likely `error@0.70+` based on expected LCP gains
- **LCP**: pre-W125 was `error@4000ms`; post-Phase-6 likely `error@2500ms`
- **CLS**: stays `error@0.10` (W120 SW2 ratchet preserved)

Document the new thresholds + the measurements they came from in a follow-up audit (e.g. `docs/audits/AUDIT_WAVE133_LHCI_RATCHET.md`).

### Step 4 — Update CLAUDE.md + memory

- Append a Wave 132/133 row to `## Audit Trail` covering the canary execution
- Add a gotcha: "Phase 6 canary completed; `frontend-stable` Deployment + Caddy `lb_policy` block deleted at Stage 6; future SSR-bound canaries author fresh"
- Append to `memory/MEMORY.md` Active backlog with measured LCP delta + Phase 6 outcomes
- File `memory/wave132_post_canary_outcomes.md` with the actual error rates, LCP numbers, push subscription drop %, etc. (cross-references to Stage 0 baseline + final Stage 5 numbers)

### Step 5 — Consider deleting `frontend/nginx.conf`

W131 §Honesty probe #9 noted nginx.conf is no longer referenced after the W131 SW3 Dockerfile move to Node. It was preserved as Phase 6 rollback safety. Post-Phase-6, it's truly dead — consider deleting in a follow-up housekeeping wave (W134+).

---

## 6. Known limitations + carry-forward deferrals

This section captures honest gaps in the W132 SW6 author phase that the operator may need to address during real rollout.

1. **Threshold values are placeholders**. The "error rate < 0.5%" / "LCP p75 < 4s" numbers in the stage table are conservative defaults; operator captures real Stage 0 baseline + adjusts. The runbook framework is correct; the numbers are templates.
2. **Caddy weight-flip command pattern assumes ConfigMap loading**. If your cluster uses Helm / Argo CD / Flux for Caddy config, adjust the apply pattern accordingly. The principle stays the same: edit weight line + push through your config-management chain + observe Caddy hot-reload event.
3. **`SECURITY_COOKIE_SAMESITE_OVERRIDE=strict` rollback knob NOT exercised in production**. W131 SW6 unit-tested it (8 tests in `tests/test_wave131_cookie_migration.py`), but actual prod rollback procedure (set env var → restart pods → verify Set-Cookie attribute changes) is undocumented for your specific cluster. Add to your team's runbook.
4. **VITE_LHCI bypass tree-shake invariant** is critical pre-deploy gate (failure mode #4 above). Existing CI build-time check is enforced — verify it runs on every prod image build before push.
5. **Caddy access log Server-Timing capture** assumes your Caddy log format includes the `Server-Timing` response header. If not, add it via Caddy's `log_format` directive (`{>Server-Timing}` placeholder) or instrument client-side RUM to capture it.
6. **Webpush subscription drop measurement** assumes you have a `webpush_subscription_active` Prometheus metric on the backend. If not, query backend DB directly:
   ```sql
   SELECT COUNT(*) FROM webpush_subscriptions WHERE active = true;
   ```
7. **`frontend-stable` legacy nginx image** must be built fresh (step 4 above). The runbook documents the procedure but the actual image doesn't exist in any registry until operator builds it.
8. **W131 §Honesty probe #5 Docker cache pollution** can re-surface during step 4's local Docker build (`docker build`). Mitigate via `docker buildx prune -af` before building if cache pressure is high.

---

## 7. Cross-references

- [`docs/plans/2026-05-01-wave125-ssr-design.md`](plans/2026-05-01-wave125-ssr-design.md) § Phase 6 — design source for this runbook
- [`docs/plans/2026-05-06-wave131-phase4-deploy-design.md`](plans/2026-05-06-wave131-phase4-deploy-design.md) — Phase 4 prerequisites
- [`docs/audits/AUDIT_WAVE131.md`](audits/AUDIT_WAVE131.md) — W131 §Honesty probe #1+#2 (Docker stack verification deferred → addressed by W132 SW1)
- [`docs/audits/AUDIT_WAVE132.md`](audits/AUDIT_WAVE132.md) — W132 wave-close audit (this wave's work)
- [`services/caddy/Caddyfile`](../services/caddy/Caddyfile) — current single-upstream baseline; the historical canary variant has been retired
- [`k8s/frontend/canary/canary-flip-strategies.md`](../k8s/frontend/canary/canary-flip-strategies.md) — quick-reference flip commands (W132 SW4)
- [`k8s/frontend/canary/deployment-stable.yaml`](../k8s/frontend/canary/deployment-stable.yaml) — legacy SPA fallback Deployment template (W132 SW4)
- [`frontend/scripts/server-prod.mjs`](../frontend/scripts/server-prod.mjs) — Node SSR runtime + Server-Timing observability (W131 SW1+SW7, W132 SW5)
- [`CLAUDE.md`](../CLAUDE.md) `## Audit Trail` Wave 131 + Wave 132 rows — context summary

---

## 8. Lessons learned (post-Phase-6 fill)

> Operator: append your observations from each stage here after Stage 6 cleanup. Future SSR-bound canary projects will reference this section for what worked + what surprised.

- Stage 0 baseline metrics: ___
- Stage 1 (90/10) observations: ___
- Stage 2 (75/25) observations: ___
- Stage 3 (50/50) observations: ___
- Stage 4 (25/75) observations: ___
- Stage 5 (0/100) observations: ___
- Final LCP p75 delta vs pre-W125 baseline: ___
- Push subscription drop magnitude: ___
- Surprises / gotchas not anticipated by the W125-W131 design: ___
- Recommended W125 design § Phase 6 amendments: ___
