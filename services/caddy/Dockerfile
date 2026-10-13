# Multi-stage build: compile a custom Caddy binary with the
# mholt/caddy-ratelimit plugin using xcaddy, then copy it into
# the matching slim Caddy runtime image.
#
# The ratelimit plugin adds a zone-based `rate_limit` directive that can
# throttle WebSocket upgrade requests before they reach the backend.
# Standard caddy:2-alpine does NOT include this module.

ARG CADDY_VERSION=2.11.7
ARG XCADDY_VERSION=v0.4.7

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM golang:1.26.9-alpine3.24@sha256:cdfd4fe2da6b225d8b40c6b7a105736e548e83ff56d5d8f9394446eeb5eb84e0 AS builder

ARG CADDY_VERSION
ARG XCADDY_VERSION

# Build Caddy with the repository Go toolchain. xcaddy is installed from
# its immutable module version, and explicit replacements retain the selected
# dependency versions without adding those modules as Caddy plugins.
RUN apk add --no-cache \
      ca-certificates=20260909-r0 \
      git=2.54.0-r0 \
    && GOBIN=/usr/local/bin go install \
      github.com/caddyserver/xcaddy/cmd/xcaddy@${XCADDY_VERSION}
RUN xcaddy build v${CADDY_VERSION} \
    --output /usr/bin/caddy \
    --with github.com/mholt/caddy-ratelimit@v0.1.0 \
    --replace golang.org/x/net=golang.org/x/net@v0.60.0 \
    --replace golang.org/x/text=golang.org/x/text@v0.42.0 \
    --replace google.golang.org/grpc=google.golang.org/grpc@v1.83.2

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# The pinned upstream Alpine image runs as root and does not ship a named
# runtime account. Upgrade only the fixed, explicitly versioned security
# packages so repeated builds cannot silently resolve different inputs, then
# create the account used by Docker Compose and Kubernetes deployments.
RUN apk update \
    && apk add --no-cache \
      libapk=3.0.8-r0 \
      apk-tools=3.0.8-r0 \
      libcrypto3=3.5.9-r0 \
      libssl3=3.5.9-r0 \
      c-ares=1.34.8-r0 \
      libcurl=8.22.0-r0 \
      curl=8.22.0-r0 \
    && addgroup -S caddy \
    && adduser -S -D -H -G caddy caddy \
    && chown -R caddy:caddy /data /config /etc/caddy

USER caddy

# Kubernetes supplies liveness/readiness probes for this edge proxy.
#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
