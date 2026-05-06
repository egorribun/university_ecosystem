# Canary weight-flip quick reference (Wave 132 SW4)

> Operator-facing reference for advancing Caddy `lb_policy weighted_round_robin`
> weights during Phase 6 SSR rollout. Full procedure in
> [`docs/CANARY_ROLLOUT_PHASE6.md`](../../../docs/CANARY_ROLLOUT_PHASE6.md).
> Caddy config at [`services/caddy/Caddyfile`](../../../services/caddy/Caddyfile).

## Stage progression

The active line in `services/caddy/Caddyfile` is:

```caddy
lb_policy weighted_round_robin <stable> <ssr>
```

Weight order matches upstream order: `to frontend-stable:8080 frontend:3000`.
Weights are positive integers; weight `0` excludes that upstream entirely.

| Stage | `<stable>` | `<ssr>` | Soak | Promote when | Abort if |
|------:|-----------:|--------:|------|--------------|----------|
| 0 | 100 | 0 | n/a | Caddyfile applied as identity change; baseline metrics captured | n/a |
| 1 | 90 | 10 | 24-48h | error rate < 0.5% on SSR pool; LCP p75 < 4s; no WS disconnect spike | error ≥ 1%; LCP p75 ≥ 6s; 5xx baseline +50% |
| 2 | 75 | 25 | 12-24h | Stage 1 metrics held under 2.5× SSR load | same |
| 3 | 50 | 50 | 12-24h | Push subscription continuity verified; Stage 2 metrics held | push subscriptions dropping; metrics regress |
| 4 | 25 | 75 | 6-12h | Stage 3 metrics held | same |
| 5 | 0 | 100 | 24h | Sentry stable; LHCI baseline at SSR levels | same |
| 6 | n/a | n/a | n/a | Delete `frontend-stable` + revert Caddy single-upstream block | n/a |

Thresholds are placeholders — operator captures real Stage 0 baseline values
and adjusts before Stage 1. The runbook documents how.

## Flip command

The Caddy config lives in a ConfigMap loaded via `--mount=type=secret`. To
apply a new weight set:

```bash
# 1. Edit services/caddy/Caddyfile lb_policy line:
#    lb_policy weighted_round_robin 90 10   ← Stage 1
#    lb_policy weighted_round_robin 75 25   ← Stage 2
#    ... etc.

# 2. Update ConfigMap from file:
kubectl -n university-ecosystem create configmap caddy-config \
  --from-file=Caddyfile=services/caddy/Caddyfile \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Trigger Caddy hot-reload (no restart needed):
kubectl -n university-ecosystem rollout restart deployment caddy

# Hot-reload completes in ~50ms. In-flight requests complete on the old
# config; new requests honor the new weights immediately.
```

**Cluster-specific**: if your cluster uses Helm / Argo CD / Flux for Caddy
config, adjust the apply pattern accordingly. The principle stays: edit the
weight line, push through your config-management chain, observe the
hot-reload event in Caddy logs.

## Instant rollback (any stage)

```bash
# Edit services/caddy/Caddyfile lb_policy line back to:
#   lb_policy weighted_round_robin 100 0

# Apply via the same ConfigMap update + rollout restart sequence.
# Recovery time: ~50ms config reload + Caddy fail_duration 30s expiry.
# In-flight SSR requests complete; new requests serve from stable pool.
```

After rollback, capture the failure mode from Sentry / Grafana / logs +
fix in staging before re-attempting from Stage 1. Do **NOT** resume mid-
stage — always restart from Stage 1 to re-establish baseline confidence.

## Per-stage verification

```bash
# Caddy access log: confirm weight distribution matches stage
kubectl -n university-ecosystem logs -l app=caddy --tail=200 \
  | grep '"upstream":' | sort | uniq -c

# Expected at Stage 1 (90/10):
#   ~90% requests:  upstream:"frontend-stable:8080"
#   ~10% requests:  upstream:"frontend:3000"

# Server-Timing header on SSR pool responses:
curl -I https://your-domain.tld/dashboard | grep -i server-timing
# Server-Timing: ssr;dur=145.32;desc="ssr-render"

# SSR pool Pod count (for HPA observation):
kubectl -n university-ecosystem get pods -l app.kubernetes.io/name=frontend
kubectl -n university-ecosystem get pods -l app.kubernetes.io/name=frontend-stable
```

## Stage 6 cleanup (post-100% canary)

```bash
# 1. Verify Stage 5 (0/100) ran cleanly for at least 24h
# 2. Delete the canary fallback pool:
kubectl -n university-ecosystem delete -f k8s/frontend/canary/deployment-stable.yaml

# 3. Revert services/caddy/Caddyfile default handle to single-upstream form
#    (commented at the bottom of the file as the post-Phase-6-cleanup form)

# 4. Apply + reload Caddy:
kubectl -n university-ecosystem create configmap caddy-config \
  --from-file=Caddyfile=services/caddy/Caddyfile \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n university-ecosystem rollout restart deployment caddy

# 5. Re-baseline LHCI gates at the new SSR levels per the W124 SW4 ratchet
#    methodology — see frontend/scripts/run-lhci.mjs for current thresholds.
#    Expected post-rollout: Perf gate likely error@0.70+ (was @0.40 pre-SSR);
#    LCP gate likely error@2500ms (was @4000ms).
```

## See also

- [`services/caddy/Caddyfile`](../../../services/caddy/Caddyfile) — the active config
- [`docs/CANARY_ROLLOUT_PHASE6.md`](../../../docs/CANARY_ROLLOUT_PHASE6.md) — full operator runbook
- [`docs/plans/2026-05-01-wave125-ssr-design.md`](../../../docs/plans/2026-05-01-wave125-ssr-design.md) § Phase 6 — design source
- [`docs/audits/AUDIT_WAVE132.md`](../../../docs/audits/AUDIT_WAVE132.md) — wave-close audit
