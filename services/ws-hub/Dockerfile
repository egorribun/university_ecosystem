# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.2-alpine3.22@sha256:7ef941168f213aa115df2e61364d67682129e99dc8188b734139dea862cc7d31 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/ws-hub/go.mod services/ws-hub/go.sum* ./services/ws-hub/

WORKDIR /app/services/ws-hub
RUN go mod download

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
