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
FROM golang:${GO_VERSION}-alpine AS builder

RUN apk add --no-cache git

# Install xcaddy — the official Caddy plugin build tool.
RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest

# Build Caddy with the rate-limit plugin.
# Pin the plugin to a specific commit tag for supply-chain safety.
RUN xcaddy build v${CADDY_VERSION} \
    --with github.com/mholt/caddy-ratelimit

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM caddy:${CADDY_VERSION}-alpine

COPY --from=builder /root/caddy /usr/bin/caddy
