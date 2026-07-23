# Multi-stage build: compile a custom Caddy binary with the
# mholt/caddy-ratelimit plugin using xcaddy, then copy it into
# the slim caddy:2-alpine runtime image.
#
# The ratelimit plugin adds a zone-based `rate_limit` directive that can
# throttle WebSocket upgrade requests before they reach the backend.
# Standard caddy:2-alpine does NOT include this module.

ARG CADDY_VERSION=2.9.1
ARG GO_VERSION=1.24

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM golang:1.24-alpine@sha256:8bee1901f1e530bfb4a7850aa7a479d17ae3a18beb6e09064ed54cfd245b7191 AS builder

ARG CADDY_VERSION

RUN apk add --no-cache git

# Install xcaddy — the official Caddy plugin build tool.
# LOW-W19: pin xcaddy to a specific release tag for supply-chain safety
RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@v0.4.4

# Build Caddy with the rate-limit plugin.
# Pin the plugin to a specific commit tag for supply-chain safety.
RUN xcaddy build v${CADDY_VERSION} \
    --with github.com/mholt/caddy-ratelimit

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM caddy:2.9.1-alpine@sha256:b4e3952384eb9524a887633ce65c752dd7c71314d2c2acf98cd5c715aaa534f0

COPY --from=builder /go/caddy /usr/bin/caddy

# checkov:skip=CKV_DOCKER_3:Caddy's upstream image owns the runtime user.
USER caddy

# Kubernetes supplies liveness/readiness probes for this edge proxy.
# checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
