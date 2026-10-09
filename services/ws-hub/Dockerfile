# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.9-alpine3.24@sha256:cdfd4fe2da6b225d8b40c6b7a105736e548e83ff56d5d8f9394446eeb5eb84e0 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/pkg/logging ./services/pkg/logging
COPY services/pkg/spiffe ./services/pkg/spiffe
COPY services/ws-hub/go.mod services/ws-hub/go.sum* ./services/ws-hub/

WORKDIR /app/services/ws-hub
# Retry to tolerate transient "unexpected EOF" from proxy.golang.org under
# bandwidth contention with parallel compose builds (Go does not retry zip
# fetches; partial downloads persist within the RUN, so retries resume).
RUN n=0; until go mod download; do \
      n=$((n + 1)); \
      if [ "$n" -ge 5 ]; then echo "go mod download failed after $n attempts" >&2; exit 1; fi; \
      echo "go mod download failed, retry $n/5 in 5s..."; \
      sleep 5; \
    done

# Copy source
COPY services/ws-hub .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build \
  -trimpath \
  -ldflags="-w -s -buildid=" \
  -o ws-hub .

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface
FROM gcr.io/distroless/static-debian12@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/ws-hub/ws-hub .

# WS-Hub runs on 8081
EXPOSE 8081

# Note: Docker HEALTHCHECK removed in favor of Kubernetes liveness/readiness probes (TD-EXP-02)
#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
USER nonroot:nonroot

CMD ["/app/ws-hub"]
