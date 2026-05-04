# ws-hub — build + test targets.
#
# Per ADR-022, integration tests live behind a //go:build integration tag and
# require Docker (testcontainers-go spins up real NATS, Redis, etc).  The
# default `make test` runs unit tests only — fast, no container pulls.

.PHONY: test test-integration test-all build clean

test:
	go test -race -coverprofile=coverage.out ./...

test-integration:
	go test -tags integration -race -timeout 5m ./...

test-all: test test-integration

build:
	go build -o ws-hub ./

clean:
	rm -f coverage.out ws-hub ws-hub.exe main.exe
