# Testing and quality guide

University Ecosystem uses one fail-closed quality contract across Python,
TypeScript, Go, Rust, browser tests, infrastructure, and supply-chain checks.
The machine-readable source of truth is
[`quality/quality-contract.json`](quality/quality-contract.json); documentation
must not duplicate its thresholds as a second policy source.

## What 100% means

- Every native metric supported by a component's coverage tool must satisfy
  the component threshold in the quality contract.
- Current patch coverage and per-component floors stay enforced until the
  separately approved Q3 migration; unsupported counters retain their current
  contract representation.
- [ADR-047](docs/adr/ADR-047-risk-based-quality-policy.md) makes mutation testing
  a nightly/manual signal after Q1. Until Q1 lands, existing mutation gates
  remain enforced. Global 100% mutation closure is no longer an MVP task;
  Q1/Q4 must land before release, and Q2/Q3 remain deferred.
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

## Repository gates

```powershell
# Hermetic developer-harness checks (--include-global-config also inspects
# optional per-developer configuration)
python verify_harness.py --repo-only
# Hook runtime regressions: corruption, concurrency, timeouts and Go discovery
python -m pytest tests/test_harness_hook_runtime.py tests/contracts/test_stop_quality_gate_contract.py -q
# Skip, orphan and anti-pattern inventory
uv run python scripts/quality/check_orphans_and_anti_patterns.py
# Relative Markdown links and heading anchors
uv run pytest tests/test_markdown_links.py -q
```

The verifier checks repository configuration, hook JSON protocol and behavior.
State-writing tests use temporary state and targets; mutating CLI tests use
copied hooks, and dispatch tests mock tool processes. The verifier does not
format working files or reset `.agents/hooks/.gate_state.json`.
Real toolchain checks remain in `scripts/fast_preflight.py`, pre-commit and CI;
a green verifier is not coverage, product acceptance or release certification.

The existing `.agents/hooks.json` uses the Antigravity protocol and assumes the
repository root as its working directory. Explicit invocation is available with
`python .agents/hooks/runner.py pre-tool`, `post-tool` or `stop`, receiving JSON
on stdin. It is not automatically discovered by Codex. Native Codex hooks need
their own registration and protocol adapter; see the
[official hook documentation](https://developers.openai.com/codex/hooks/).
Profiles in `.agents/subagents.json` are role guidance, not processes: root
assigns disjoint files in `egorribun`, caps concurrency at three, and controls
heavy workloads and the 30-minute checkpoint budget.

## Browser tests

```powershell
# Mocked-API Playwright matrix (Chromium, Firefox, WebKit, mobile WebKit)
npm run test:e2e --prefix frontend

# Live acceptance lane: real backend, database, seeded roles and Mailpit
$liveStateParent = Join-Path (python -c "import tempfile; print(tempfile.gettempdir())") 'ue-live-acceptance'
$liveStateDir = Join-Path $liveStateParent ('run-' + [guid]::NewGuid().ToString('N'))
python scripts/live_stand.py up --in-place --state-dir $liveStateDir --ref HEAD --stack core
python scripts/live_stand.py seed --in-place --state-dir $liveStateDir --demo
python scripts/live_stand.py e2e --in-place --state-dir $liveStateDir --mode full
python scripts/live_stand.py stop --in-place --state-dir $liveStateDir
```

The active MVP plan requires one checkout: use `--in-place` on a clean, frozen
`egorribun` SHA and keep its generated configuration in an owned temporary run
directory. The CLI assigns a separate Compose project and checks resource
ownership; `stop` preserves demo data, while explicit `teardown` deletes only
the validated run resources. Product acceptance uses Core; the frozen-release
full smoke explicitly uses `--stack full`. Coordinate any source edits until
the live run ends. Infrastructure-backed checks run only when their
services are available; a missing optional service is reported as an explicit
environment skip, never as a pass.

Supply the same `--state-dir` with every `--in-place` command. The directory
must be a direct `run-*` child under Python's temporary `ue-live-acceptance`
root. The `e2e` wrapper validates owned endpoints and supplies ephemeral
credentials; use it for acceptance rather than invoking the npm script without
the stand's environment. `status` reads existing state without creating a run.

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
