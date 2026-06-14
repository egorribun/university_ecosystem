# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.4-alpine3.22@sha256:cff7cf3120cd74bf0960cfe19a3efb6631161148d8e070f76976f73a13b2e3d4 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
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
FROM gcr.io/distroless/static-debian12:latest@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/ws-hub/ws-hub .

# WS-Hub runs on 8081
EXPOSE 8081

# Note: Docker HEALTHCHECK removed in favor of Kubernetes liveness/readiness probes (TD-EXP-02)
USER nonroot:nonroot

CMD ["/app/ws-hub"]
