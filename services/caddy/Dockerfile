# Multi-stage build: compile a custom Caddy binary with the
# mholt/caddy-ratelimit plugin using xcaddy, then copy it into
# the matching slim Caddy runtime image.
#
# The ratelimit plugin adds a zone-based `rate_limit` directive that can
# throttle WebSocket upgrade requests before they reach the backend.
# Standard caddy:2-alpine does NOT include this module.

ARG CADDY_VERSION=2.11.4

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM caddy:2.11.4-builder-alpine@sha256:8e89605351333ad2cc2f3bcc95275a2ccc427f88914050e86a5fde0fd77a63c4 AS builder

ARG CADDY_VERSION

# Build Caddy with the rate-limit plugin.
# Pin the plugin to a specific commit tag for supply-chain safety.
RUN xcaddy build v${CADDY_VERSION} \
    --with github.com/mholt/caddy-ratelimit@v0.1.0

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# The pinned upstream Alpine image runs as root and does not ship a named
# runtime account.  Create the account explicitly so the custom binary is
# usable by Docker Compose and by non-root Kubernetes deployments.
RUN addgroup -S caddy \
    && adduser -S -D -H -G caddy caddy \
    && chown -R caddy:caddy /data /config /etc/caddy

USER caddy

# Kubernetes supplies liveness/readiness probes for this edge proxy.
#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
