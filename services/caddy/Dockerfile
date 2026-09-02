# Multi-stage build: compile a custom Caddy binary with the
# mholt/caddy-ratelimit plugin using xcaddy, then copy it into
# the matching slim Caddy runtime image.
#
# The ratelimit plugin adds a zone-based `rate_limit` directive that can
# throttle WebSocket upgrade requests before they reach the backend.
# Standard caddy:2-alpine does NOT include this module.

ARG CADDY_VERSION=2.11.4
ARG XCADDY_VERSION=v0.4.5

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM golang:1.26.6-alpine3.24@sha256:af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df AS builder

ARG CADDY_VERSION
ARG XCADDY_VERSION

# Build Caddy with the patched repository Go toolchain. The upstream Caddy
# builder for 2.11.4 still contains Go 1.26.5, so xcaddy is installed from its
# immutable module version and Caddy's vulnerable transitive modules are
# replaced with their fixed releases without adding them as Caddy plugins.
RUN apk add --no-cache \
      ca-certificates=20260611-r0 \
      git=2.54.0-r0 \
    && GOBIN=/usr/local/bin go install \
      github.com/caddyserver/xcaddy/cmd/xcaddy@${XCADDY_VERSION}
RUN xcaddy build v${CADDY_VERSION} \
    --output /usr/bin/caddy \
    --with github.com/mholt/caddy-ratelimit@v0.1.0 \
    --replace golang.org/x/net=golang.org/x/net@v0.56.0 \
    --replace golang.org/x/text=golang.org/x/text@v0.39.0 \
    --replace google.golang.org/grpc=google.golang.org/grpc@v1.83.1

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# The pinned upstream Alpine image runs as root and does not ship a named
# runtime account. Upgrade only the fixed, explicitly versioned security
# packages so repeated builds cannot silently resolve different inputs, then
# create the account used by Docker Compose and Kubernetes deployments.
RUN apk add --no-cache \
      libapk=3.0.7-r0 \
      apk-tools=3.0.7-r0 \
      libcrypto3=3.5.8-r0 \
      libssl3=3.5.8-r0 \
      c-ares=1.34.8-r0 \
      libcurl=8.20.0-r0 \
      curl=8.20.0-r0 \
    && addgroup -S caddy \
    && adduser -S -D -H -G caddy caddy \
    && chown -R caddy:caddy /data /config /etc/caddy

USER caddy

# Kubernetes supplies liveness/readiness probes for this edge proxy.
#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
