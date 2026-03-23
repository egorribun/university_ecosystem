# ADR-009: OpenFeature Feature Flags

## Status
Proposed (Wave 15, 2026-03-23) — **provider not yet selected**

## Context

Several features in the roadmap require gradual rollout or A/B testing capabilities:
- New scheduler algorithm (`new-scheduler-algorithm` — MOD-08)
- Experimental GraphQL subscription transport
- Per-user beta feature access

Currently, feature gates are hardcoded `if settings.enable_feature_X` boolean flags, which require a re-deploy to toggle and provide no per-user targeting.

The team evaluated the OpenFeature standard (CNCF) as a vendor-neutral abstraction layer, allowing the backing provider to be swapped without changing application code.

## Decision

**Adopt OpenFeature SDK** (`openfeature-sdk` for Python, `go-sdk` for Go services). Provider selection is **pending** — blocked on ops infrastructure decision.

### Provider Options Under Evaluation

| Provider | Hosting | Cost | Real-time push | User targeting |
|----------|---------|------|---------------|----------------|
| **flagd** | Self-hosted | Free | gRPC streaming | Via JSON targeting rules |
| **Unleash** | Self-hosted / Cloud | OSS free | WebSocket | Full segmentation |
| **LaunchDarkly** | SaaS | Paid | Streaming | Full |
| **Flipt** | Self-hosted | Free | gRPC streaming | Limited |

**Preliminary recommendation:** `flagd` — self-hosted, no SaaS dependency, native OpenFeature provider, gRPC streaming for real-time flag updates, file-backed for dev. Aligns with the project's preference for self-hosted infra.

## Deferred Until

Provider decision must be made before implementation begins. The architecture team will evaluate ops feasibility of running flagd vs. Unleash by **2026-06-01**.

## Consequences (if flagd is chosen)

**Positive:**
- Feature flags toggleable without deploy.
- Per-user and per-role targeting without code changes.
- Vendor-neutral (OpenFeature SDK) — provider can be swapped.

**Negative:**
- New infrastructure component (flagd service).
- Network dependency in request path for flag evaluation (mitigated by local caching).
- Flag configuration drift if not version-controlled.

## Implementation (planned, pending provider decision)

- `app/core/feature_flags.py` — OpenFeature client initialization
- `docker-compose.prod.yml` — flagd service
- `flags/flags.json` — flag definitions (version-controlled)
- Usage: `client.get_boolean_value("feature-name", default_value=False, evaluation_context=...)`
