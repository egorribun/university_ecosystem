# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.4-alpine3.22@sha256:cff7cf3120cd74bf0960cfe19a3efb6631161148d8e070f76976f73a13b2e3d4 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/gateway/go.mod services/gateway/go.sum* ./services/gateway/

WORKDIR /app/services/gateway
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
COPY services/gateway .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build \
  -trimpath \
  -ldflags="-w -s -buildid=" \
  -o gateway ./cmd/gateway

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface (no shell, no pkg manager)
FROM gcr.io/distroless/static-debian12:latest@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/gateway/gateway .

# Gateway runs on 8080
EXPOSE 8080

# Note: Docker HEALTHCHECK removed in favor of Kubernetes liveness/readiness probes (TD-EXP-02)
# checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes.
USER nonroot:nonroot

CMD ["/app/gateway"]
