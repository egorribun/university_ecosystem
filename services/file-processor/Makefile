# file-processor — build + test targets.
#
# Per ADR-022, integration tests live behind a //go:build integration tag and
# require Docker (testcontainers-go spins up real MinIO and NATS).  The
# default `make test` runs unit tests only — fast, no container pulls.

.PHONY: test test-integration test-all build clean

test:
	go test -race -coverprofile=coverage.out ./...

test-integration:
	go test -tags integration -race -timeout 5m ./...

test-all: test test-integration

build:
	go build -o file-processor ./cmd/file-processor

clean:
	rm -f coverage.out file-processor file-processor.exe main.exe
