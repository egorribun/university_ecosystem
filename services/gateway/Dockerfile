# syntax=docker/dockerfile:1.7

# Build stage
# MOD-02 (audit 2026-03-06): 1.25.5 → 1.26.3 (Go 1.26 LTS; alpine3.22 for CVE coverage)
FROM golang:1.26-alpine AS builder

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
FROM alpine:latest

RUN apk add --no-cache ca-certificates tzdata \
  && addgroup -S app && adduser -S app -G app

WORKDIR /app

COPY --from=builder --chown=app:app /app/services/gateway/gateway .

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["./gateway"]
