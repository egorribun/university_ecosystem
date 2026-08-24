# Testing and quality guide

University Ecosystem uses one fail-closed quality contract across Python,
TypeScript, Go, Rust, browser tests, infrastructure, and supply-chain checks.
The machine-readable source of truth is
[`quality/quality-contract.json`](quality/quality-contract.json); documentation
must not duplicate its thresholds as a second policy source.

## What 100% means

- Every native metric supported by a component's coverage tool must satisfy
  the component threshold in the quality contract.
- Changed executable lines must have 100% differential coverage.
- The viable mutation score must be 100%: no surviving, timed-out, or untested
  viable mutants.
- Tier 0 code must remain fully covered for every metric its source report can
  represent.
- Unsupported counters are reported as unsupported, never converted to a
  fabricated pass. YAML, Docker, shell, schemas, and generated artifacts are
  verified through lint, render, contract, policy, and smoke tests.

## Install reproducibly

```powershell
uv sync --frozen
npm ci --prefix frontend
go work sync
```

Use the Python, Node, Go, and Rust versions pinned by the repository and CI.
Do not update lockfiles as a side effect of running tests.

## Fast feedback

```powershell
uv run pytest -q <focused-test-files>
uv run ruff check <changed-python-files>
npm run typecheck --prefix frontend
npm run test --prefix frontend -- <focused-test-files>
```

Focused commands are development feedback only. A completion claim requires
the full relevant suites and policy gates.

## Canonical coverage commands

### Python backend

```powershell
New-Item -ItemType Directory -Force artifacts/coverage/python | Out-Null
uv run pytest tests -n 4 --dist loadfile --cov=app --cov-branch `
  --cov-report=xml:coverage.xml `
  --cov-report=json:artifacts/coverage/python/coverage.json `
  --cov-report=term:skip-covered
```

The command inherits the fail-closed threshold from `pyproject.toml`; do not
override it on the command line.

### Frontend

CI runs four Vitest shards on separate runners and merges their Istanbul
reports. For a local correctness run:

```powershell
npm run test:ci --prefix frontend
```

For exact CI parity, run `--shard=1/4` through `--shard=4/4` into separate
coverage directories and merge them with
`frontend/scripts/merge-vitest-coverage.mjs`. Never merge incomplete shards.

### Go services

Run each independent module from its own directory:

```powershell
Push-Location services/gateway
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location

Push-Location services/ws-hub
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location

Push-Location services/file-processor
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location

Push-Location services/cmd/uni-cli
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location

Push-Location services/pkg/spiffe
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location

Push-Location services/pkg/spicedb
go test -count=1 -race -covermode=atomic -coverprofile=coverage.out ./...
Pop-Location
```

The quality manifest reports the three deployable services independently and
merges `uni-cli`, SPIFFE, and SpiceDB evidence into the `go-shared` component
with `scripts/quality/merge_go_coverprofiles.py`. Generated protobuf bindings
are build-checked but excluded from authored-source coverage.

### Rust and WASM

Run `cargo test` and `cargo clippy --all-targets --all-features -- -D warnings`
for every workspace or crate. The exact `cargo llvm-cov` line, function, and
nightly branch commands are pinned in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml); use that workflow as the
cross-platform report contract.

## Normalize and validate evidence

Raw coverage output is not the final gate. CI normalizes all reports into
`artifacts/coverage/quality-manifest.json`, verifies report freshness and the
commit SHA, and then runs:

```powershell
uv run python scripts/quality/validate_quality_contract.py `
  --manifest artifacts/coverage/quality-manifest.json
```

Coverage reports, test XML, browser traces, and benchmark output are generated
artifacts. Do not commit them unless a fixture test explicitly owns the file.

## Reliability rules

- Synchronize on observable events or state; do not use arbitrary sleeps as a
  correctness assertion.
- Do not make a flaky test pass by raising a timeout, adding retries, or
  weakening an assertion without proving the root cause.
- Use deterministic clocks, random seeds, ports, and disposable external
  services.
- A skipped test is acceptable only when its explicit, expiring policy entry
  or environment contract makes the skip intentional.
- Preserve the first failure and diagnostics; reruns are supporting evidence,
  not a replacement for the original result.

See the [flaky-test audit runbook](docs/testing/flaky-test-audit-runbook.md),
[performance baseline policy](docs/testing/performance-regression-baseline.md),
and [quality dashboard](docs/testing/dashboard.md) for operational evidence.
