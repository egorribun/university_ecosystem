# Multi-stage build: compile the locked Caddy edge binary (upstream Caddy v2.11.7
# plus the mholt/caddy-ratelimit plugin) and copy it into the matching slim
# Caddy runtime image.
#
# The ratelimit plugin adds a zone-based `rate_limit` directive that can
# throttle WebSocket upgrade requests before they reach the backend.
# Standard caddy:2-alpine does NOT include this module.
#
# AUD-482: the complete Go module graph is committed in go.mod and go.sum, and
# the build runs with -mod=readonly. A missing or drifted dependency fails the
# build instead of resolving a new graph inside the image. The build context is
# this directory, so the module files must stay beside this Dockerfile.

ARG CADDY_VERSION=2.11.7

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM golang:1.26.10-alpine3.24@sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca AS builder

ARG CADDY_VERSION

# git serves the go command's direct VCS fallback for any module the proxy does
# not serve; the locked graph itself is fetched through the module proxy.
RUN apk add --no-cache \
      ca-certificates=20260909-r0 \
      git=2.54.0-r0

WORKDIR /src
COPY go.mod go.sum main.go ./
# The committed Caddy requirement must name the version this image is built for.
RUN grep -Fq "github.com/caddyserver/caddy/v2 v${CADDY_VERSION}" go.mod \
    && GOTOOLCHAIN=local CGO_ENABLED=0 go build \
      -mod=readonly -trimpath -buildvcs=false \
      -tags nobadger,nomysql,nopgx -ldflags "-w -s" \
      -o /usr/bin/caddy .

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
      brotli-libs=1.2.1-r0 \
      libcurl=8.23.0-r0 \
      curl=8.23.0-r0 \
    && addgroup -S caddy \
    && adduser -S -D -H -G caddy caddy \
    && chown -R caddy:caddy /data /config /etc/caddy

USER 100:101

# Kubernetes supplies liveness/readiness probes for this edge proxy.
#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
