# Docker Startup Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `./start-docker.ps1 -Build` converge an existing local installation to a healthy full stack without deleting persistent volumes, while removing the Docker configuration defects discovered during the audit.

**Architecture:** Reconcile durable JetStream resources in place, keep one transactional outbox processor per Compose stack, and make startup contracts executable through focused tests. The PowerShell entrypoint remains the canonical full-stack launcher; Compose wrappers and examples must resolve the same environment contract. Images continue to run as non-root users, with writable home/runtime paths explicitly provisioned.

**Tech Stack:** PowerShell 7, Docker Engine/Compose, Python 3.14, FastAPI, nats-py JetStream, SQLAlchemy/Alembic, pytest, YAML, Helm, Go service images.

---

### Task 1: Lock the reproduced backend failures into regression tests

**Files:**
- Modify: `tests/test_wave140_nats_files_process_stream.py`
- Modify: `tests/test_lifespan.py`

**Step 1: Write failing JetStream drift tests**

Add a test where `add_stream()` raises NATS error 10058 for an existing stream with stale configuration. Assert that the desired `StreamConfig` is sent to `update_stream()` and provisioning continues. Add a companion test proving unrelated NATS errors remain fatal and the partial connection is cleaned up.

**Step 2: Run the tests and confirm RED**

Run: `docker run --rm --env-file .env.docker -v ${PWD}:/workspace -w /workspace university_ecosystem-backend pytest -q tests/test_wave140_nats_files_process_stream.py`

Expected: failure because `connect()` only invokes `add_stream()` and retains partial state.

**Step 3: Write a failing migration-context test**

Model `AsyncConnection.run_sync()` as executing a callback and require `MigrationContext.get_current_revision()` to execute inside that callback.

**Step 4: Run the lifespan slice and confirm RED**

Run: `docker run --rm --env-file .env.docker -v ${PWD}:/workspace -w /workspace university_ecosystem-backend pytest -q tests/test_lifespan.py`

Expected: failure because the current revision is read after leaving SQLAlchemy's greenlet bridge.

### Task 2: Make backend startup self-healing and deterministic

**Files:**
- Modify: `app/core/nats_broker.py`
- Modify: `app/core/lifespan.py`

**Step 1: Reconcile stream configuration**

Attempt JetStream creation first. On the specific server error `err_code=10058`, update that stream with the desired durable configuration; re-raise all other errors. If any provisioning step fails, close and clear the partial NATS connection before re-raising.

**Step 2: Keep migration I/O inside `run_sync()`**

Return `MigrationContext.configure(sync_conn).get_current_revision()` directly from the callback.

**Step 3: Run focused tests and lint**

Run the two pytest slices above and `python -m ruff check app/core/nats_broker.py app/core/lifespan.py tests/test_wave140_nats_files_process_stream.py tests/test_lifespan.py` in the backend image.

### Task 3: Repair the PowerShell launcher and environment contract

**Files:**
- Create: `tests/test_docker_startup_contracts.py`
- Modify: `start-docker.ps1`
- Modify: `.env.docker.example`
- Modify: `scripts/dc.ps1`
- Modify: `scripts/dc.sh`

**Step 1: Add failing launcher contract tests**

Assert cryptographic RNG use, initialized numeric JWT `iat`/`exp`/`jti`, validation and regeneration of stale Temporal tokens, consistent RS256 example variables, and explicit `.env.docker` use in both Compose wrappers.

**Step 2: Confirm RED**

Run: `docker run --rm -v ${PWD}:/workspace -w /workspace university_ecosystem-backend pytest -q tests/test_docker_startup_contracts.py`

**Step 3: Implement secure and idempotent launcher behavior**

Use `RandomNumberGenerator.GetBytes()` for generated secrets. Mint a signed Temporal JWT only after initializing Unix timestamps and a GUID JTI; decode an existing token and regenerate it when malformed, expired, wrong-audience, or near expiry. Keep all output UTF-8 without BOM.

**Step 4: Align examples and wrappers**

Document every variable required by `docker-compose.full.yml`, use RS256 and the private-key path, and make both wrappers pass `--env-file .env.docker` with an actionable missing-file error.

### Task 4: Remove competing outbox/CDC paths and add meaningful worker health

**Files:**
- Modify: `app/core/config/notifications.py`
- Modify: `app/core/lifespan.py`
- Modify: `app/workers/outbox.py`
- Modify: `tests/test_lifespan.py`
- Modify: `tests/test_outbox_closure.py`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.full.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `charts/university-ecosystem/values.yaml`
- Modify: `charts/university-ecosystem/templates/backend-deployment.yaml`
- Create: `charts/university-ecosystem/templates/outbox-worker-deployment.yaml`
- Modify: `charts/university-ecosystem/templates/keda-scaledobjects.yaml`

**Step 1: Add failing topology tests**

Require one standalone `python -m app.workers.outbox` service, no unsupported Debezium NATS sink, no direct `app.workers.cdc_outbox` command, and an explicit switch disabling the embedded outbox worker when the standalone worker is deployed.

**Step 2: Implement one processor topology**

Add `EMBEDDED_OUTBOX_WORKER_ENABLED` (default true for direct application runs). Disable it in Compose/Helm backend deployments and run one standalone reactive LISTEN/NOTIFY outbox worker. Retire the broken Compose CDC/Debezium services while preserving their persistent data volumes untouched.

**Step 3: Add standalone liveness**

Have the standalone worker maintain `/tmp/worker.pid` and an event-loop heartbeat. Health checks validate both process existence and recent heartbeat rather than executing an unconditional success command.

**Step 4: Repair Helm target consistency**

Render an outbox worker Deployment before referencing it from KEDA. Scale the database-backed worker conservatively and remove the invalid NATS consumer assumption from the default chart.

### Task 5: Polish image/build contracts found in the Docker audit

**Files:**
- Modify: `backend.Dockerfile`
- Modify: `Dockerfile.test`
- Modify: `services/caddy/Dockerfile`
- Modify: `.dockerignore`
- Modify: `Dockerfile.test.dockerignore`
- Modify: `tests/test_docker_startup_contracts.py`

**Step 1: Add failing static contracts**

Require a writable `/home/app`, a version-pinned Caddy rate-limit plugin, and explicit exclusion of frontend build/coverage/test artifacts from Docker contexts.

**Step 2: Implement the image fixes**

Create the non-root home directory in runtime and test images, pin `github.com/mholt/caddy-ratelimit@v0.1.0`, and exclude the measured local artifacts from both relevant contexts.

**Step 3: Run image linters/checks**

Run Hadolint for every Dockerfile and `docker build --check` for every build definition.

### Task 6: Validate every Compose mode and the live full stack

**Files:**
- Modify as needed only when a new reproduced defect is proven.

**Step 1: Validate rendered configuration**

Run `docker compose config --quiet` for full, base, base+prod, test, sandbox, base+observability, and the CI multi-file load-test composition with representative non-secret test values.

**Step 2: Run focused and full quality gates**

Run targeted pytest slices, backend Ruff, relevant Go tests, PowerShell parser checks, Helm lint/template, and the full backend suite appropriate to changed Python code.

**Step 3: Rebuild and execute the exact user command**

Run `./start-docker.ps1 -Build` against the existing volumes. Verify exit code 0, all required containers healthy/running, no restart loops, and HTTP health endpoints through Caddy, frontend, gateway, backend, ws-hub, worker, NATS, MinIO, and Temporal.

**Step 4: Verify durable resource convergence**

Query JetStream and confirm all five streams have the desired subjects, file storage, limits retention, and seven-day max age. Confirm database migrations report the current Alembic head and outbox worker logs show a stable reactive listener.

### Task 7: Review, publish, and verify remote state

**Files:**
- Review all changed files.

**Step 1: Perform a clean self-review**

Run `git diff --check`, inspect the complete diff, verify no generated secrets or unrelated user changes are included, and rerun any gate affected by review edits.

**Step 2: Commit without bypasses**

Stage the intended files and commit with `fix(docker): make full-stack startup self-healing`. Do not add a `Co-Authored-By` trailer and do not associate testing work with a wave.

**Step 3: Push and verify**

Push `egorribun`, verify `origin/egorribun` equals local HEAD, and inspect the resulting GitHub checks. Resolve any in-scope CI failure before declaring completion.
