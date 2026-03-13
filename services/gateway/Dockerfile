# syntax=docker/dockerfile:1.7

# Build stage
FROM golang:1.26.3-alpine3.21 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/gateway/go.mod services/gateway/go.sum* ./services/gateway/

WORKDIR /app/services/gateway
RUN go mod download

# Copy source
COPY services/gateway .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build \
  -trimpath \
  -ldflags="-w -s -buildid=" \
  -o gateway ./cmd/gateway

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface (no shell, no pkg manager)
FROM gcr.io/distroless/static-debian12:latest

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/gateway/gateway .

# Gateway runs on 8080
EXPOSE 8080

# Note: Docker HEALTHCHECK removed in favor of Kubernetes liveness/readiness probes (TD-EXP-02)
USER nonroot:nonroot

CMD ["/app/gateway"]
