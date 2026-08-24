# gateway — build + test targets.
#
# Per ADR-022, integration tests live behind a //go:build integration tag and
# require Docker (testcontainers-go spins up real Redis for auth, revocation,
# rate-limit, and L1-cache validation). The default `make test` is unit-only,
# no container pulls.

.PHONY: test test-integration test-all build clean

test:
	go test -race -coverprofile=coverage.out ./...

test-integration:
	go test -tags integration -race -timeout 5m ./...

test-all: test test-integration

build:
	go build -o gateway ./cmd/gateway

clean:
	rm -f coverage.out gateway gateway.exe
