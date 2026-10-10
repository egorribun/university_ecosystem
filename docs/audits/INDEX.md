# Audit trail

This index holds the retained platform findings and historical-evidence policy.
Historical classifications describe their recorded source revision. Current
release claims require fresh evidence under the master plan.

## Current quality-closure roadmap

- [Active MVP closure status](../superpowers/plans/STATUS.md) — the current
  operational checkpoint; every release claim still requires fresh exact-SHA
  evidence.
- [MVP master plan](../superpowers/plans/MVP_MASTER_PLAN.md) and
  [ADR-047](../adr/ADR-047-risk-based-quality-policy.md) — since 2026-10-08 the
  `v1.0.0` definition of done is product acceptance; mutation score and release
  certification items moved to `v1.1`. Existing six-image publication is retained;
  Q1/Q4 are mandatory, and current coverage floors stay enforced until Q3.
- [Findings ledger](#findings-ledger) — all 63 platform finding IDs, retained
  rationale and current source references. Current-RC revalidation remains open.
- [Codebase consolidation decisions](../adr/ADR-046-codebase-consolidation-audit.md)
  — outcome of the 2026-10 dead-code, duplication and contract-drift audit:
  what was fixed, retired and deliberately kept, with the evidence rules used.

## Findings ledger

This ledger retains all 63 IDs and aliases from the historical platform review. The
historical 60 CLOSED / 2 DECLINED / 1 OPEN counts are only the report’s
2026-10-03 ledger; they are not a current-RC certification. Revalidate all
63 classifications against the final RC SHA and record current evidence/run
and owner. Until then the current status is pending revalidation. BE-02
deployed catalog evidence and MIG-PASS-01 remain v1.1 obligations; this does
not close them. A row marked historically closed is not a current pass.

| ID / alias | Historical disposition | Retained requirement, rationale, or evidence |
| --- | --- | --- |
| BE-01 | CLOSED | Keep offline Alembic environment discovery independent of runtime-only secrets/config. [Migration](../../alembic/versions/148642dd1207_fix_missing_tables.py) |
| BE-02 | OPEN | Deployed PostgreSQL catalog preflight for DDL phases 1/3/4; source inventory is not deployment proof. v1.1. [ADR-036](../adr/ADR-036-sqlalchemy-dual-default-migration-policy.md), [policy](../../quality/model-default-policy.json), [preflight](../../scripts/be02_catalog_preflight.py) |
| BE-03 | CLOSED | User.chats must remain explicit back_populates with lazy=noload. [User model](../../app/models/users.py) |
| BE-04 | CLOSED | One canonical Dishka route/session owner; current inventory and drift guard remain authoritative. [ADR-033](../adr/ADR-033-request-scoped-database-session-ownership.md), [inventory](../../quality/route-dependency-inventory.json) |
| BE-05 | CLOSED | Stdlib logs must pass through structured PII-redacting formatter. [Logging](../../app/core/logging.py) |
| BE-06 | CLOSED | Recursive nested PII redaction with cycle protection. [Logging](../../app/core/logging.py) |
| BE-07 | CLOSED | NATS disconnect must be observable and delivery failure must not silently disappear. [NATS broker](../../app/core/nats_broker.py) |
| BE-08 | CLOSED label; DEFERRED | Polling/LISTEN-NOTIFY is sole supported outbox transport; CDC remains fail-closed until every integration/replay/lifecycle gate is accepted. [ADR-037](../adr/ADR-037-cdc-outbox-transport-ownership.md) |
| BE-09 | CLOSED | Event-handler tasks require structured ownership and cancellation cleanup. [Event handlers](../../app/core/events.py) |
| BE-10 | CLOSED | Local revocation store accepts the safe default URL while rejecting invalid sentinels. [Revocation](../../app/auth/revocation.py), [cache settings](../../app/core/config/cache.py) |
| BE-11 | CLOSED | Broad exception handlers retain valid justification tags. [Backend observability](../../app/core/observability.py), [reset MFA](../../app/management/reset_mfa.py) |
| BE-12 | CLOSED | Schema split preserves import compatibility, byte-stable OpenAPI, and Pact path coverage. [Schema shim](../../app/schemas/schemas.py), [contracts](../../.github/workflows/contract-tests.yml) |
| FE-01 | CLOSED | Production SSR wrapper keeps traversal and malformed-URI defenses. [SSR wrapper](../../frontend/scripts/server-prod.mjs) |
| FE-02 | CLOSED | Router and application must share QueryClient defaults. [Router](../../frontend/src/router.ts), [QueryClient](../../frontend/src/app/queryClient.ts) |
| FE-03 | CLOSED | Redirect parsing rejects backslash/open-redirect variants and preserves query/hash safely. [Redirect helper](../../frontend/src/utils/redirect.ts) |
| FE-04 | CLOSED historical; recheck | The cited ClockWidget was deleted in commit 588fd8b; historical closure does not establish a replacement. Re-evaluate the current dashboard date/hydration path before classification. [Current dashboard area](../../frontend/src/features/dashboard/) |
| FE-05 | CLOSED | Missing wasm-pack may use checked-in artifacts only after validation; a real build failure stays fatal. [WASM build](../../frontend/scripts/build-wasm.mjs) |
| FE-06 | CLOSED | Button consumers use leadingIcon; startIcon remains only as an intentional compatibility alias. [Button](../../frontend/src/components/ui/Button.tsx) |
| FE-07 | CLOSED | useAuthStore remains exported from the canonical store barrel. [Store index](../../frontend/src/stores/index.ts) |
| FE-08 | CLOSED | Remove the duplicate utility without deleting valid custom Tailwind classes. [Settings layout](../../frontend/src/components/settings/ui/Layout.tsx) |
| FE-09 | CLOSED | Test MockButton filters non-DOM component props before spreading onto button. [Sessions closure test](../../frontend/src/pages/settings/sections/__tests__/SessionsSection.closure.test.tsx) |
| GO-01 / FP-FP-01 | CLOSED | Reject absolute/traversal object keys before normalization in gRPC and workflow paths. [File processor validation](../../services/file-processor/internal/service/server.go), [workflow](../../services/file-processor/internal/workflow/workflow.go) |
| GO-02 / GW-AUTH-01 | CLOSED | JWKS retains both rotation keys and selects by kid; preserve ADR-013 dual-key window. [Gateway auth](../../services/gateway/middleware/auth.go), [ADR-013](../adr/ADR-013-secret-rotation.md) |
| GO-03 / GW-RL-01 | CLOSED | Readiness/liveness probes remain available during Redis limiter failure. [Gateway rate limiter](../../services/gateway/middleware/ratelimit.go) |
| GO-04 / WSH-CFG-01 | CLOSED | Default allowed origins include localhost through Caddy port 80. [WS-Hub config](../../services/ws-hub/pkg/config/config.go) |
| GO-05 / CLI-REDIS-01 | CLOSED | Admin cache clearing uses cursor SCAN, never blocking KEYS. [uni-cli](../../services/cmd/uni-cli/main.go) |
| GO-06 / DOC-AGENTS-01 | CLOSED | Services documentation assigns NATS key/cache subscriptions to ws-hub, not gateway. [Services guide](../../services/AGENTS.md) |
| GO-07 / ENV-TOOL-01 | CLOSED | Preserve the pinned/containerized lint and race-test path for hosts without Go lint/CGO tools. [Services guide](../../services/AGENTS.md) |
| RUST-P1-01 | CLOSED | Non-WASM raw-pointer entry point validates bounds before dereferencing. [WASM sanitizer](../../frontend/wasm-sanitizer/src/lib.rs) |
| RUST-P1-02 | CLOSED historical; recheck current contract | WASM sanitizer handles null bytes and BOM. The former PyO3 parity peer was retired; do not claim parity with deleted code. [WASM sanitizer](../../frontend/wasm-sanitizer/src/lib.rs), [ADR-044](../adr/ADR-044-retire-unused-native-sanitizer.md) |
| RUST-P2-01 | CLOSED | Release Python GIL around Rayon conflict work. [Native extension](../../native/rust_ext/src/lib.rs) |
| RUST-P2-02 | CLOSED | Bound PBKDF2 iteration and key size inputs. [Rust crypto](../../frontend/rust-crypto/src/lib.rs) |
| RUST-P2-03 | CLOSED | Secret key material remains zeroized on all relevant Rust crypto paths. [Rust crypto](../../frontend/rust-crypto/src/lib.rs) |
| RUST-P2-04 | CLOSED by retirement | pyo3-sanitizer is retired; current cargo-deny inventory covers only remaining production crates. [ADR-044](../adr/ADR-044-retire-unused-native-sanitizer.md) |
| RUST-P2-05 | CLOSED by retirement | No fuzz target is expected for deleted pyo3-sanitizer; keep remaining production fuzz coverage. [ADR-044](../adr/ADR-044-retire-unused-native-sanitizer.md) |
| RUST-P3-01 | DECLINED | Keep per-crate manifests/locks and CI evidence boundaries absent demonstrated consolidation value; rust-crypto wasm_js feature resolution/cache effects require evidence before reconsideration. [native Rust manifest](../../native/rust_ext/Cargo.toml), [WASM sanitizer manifest](../../frontend/wasm-sanitizer/Cargo.toml), [Rust crypto manifest](../../frontend/rust-crypto/Cargo.toml) |
| RUST-P3-02 | CLOSED | Fuzz target belongs under the production Rust crate that owns it, not as an orphan at repository root. [Rust crypto fuzz](../../frontend/rust-crypto/fuzz/) |
| RUST-P3-03 | CLOSED historical; final SHA proof pending | Keep direct Base64 export and prove source/artifact parity on canonical builder against exact final SHA; do not reimplement export. [Rust crypto](../../frontend/rust-crypto/src/lib.rs), [crypto worker](../../frontend/src/workers/crypto.worker.ts), [master plan](../superpowers/plans/MVP_MASTER_PLAN.md) |
| RUST-P3-04 | CLOSED | Remove unused dependency features; retain the zeroizing key-ring behavior. [Native Rust manifest](../../native/rust_ext/Cargo.toml) |
| INFRA-01 | CLOSED | Standalone K8s secret names and backend environment bindings remain aligned. [ExternalSecret](../../k8s/backend/external-secret.yaml), [deployment](../../k8s/backend/deployment.yaml) |
| INFRA-02 | CLOSED by decision | Helm is sole staging/production application producer; raw K8s is supporting/development only, with no duplicate Go workload set. [ADR-034](../adr/ADR-034-helm-canonical-application-deployment.md), [K8s guide](../../k8s/README.md) |
| INFRA-03 | CLOSED | Raw K8s apply goes through allowlisted envsubst wrapper; IMAGE_TAG is immutable SHA or semantic version. [Root standards](../../AGENTS.md), [apply wrapper](../../scripts/apply_raw_k8s.sh) |
| INFRA-04 | CLOSED | Frontend HPA remains parameterized and chart-owned. [Helm values](../../charts/university-ecosystem/values.yaml), [HPA template](../../charts/university-ecosystem/templates/hpa.yaml) |
| INFRA-05 | CLOSED | Frontend SSR memory request/limit stays within reviewed workload sizing. [Helm values](../../charts/university-ecosystem/values.yaml) |
| INFRA-06 | CLOSED | Reusable backend workflow passes validated inputs via environment, not interpolated shell source. [Workflow](../../.github/workflows/reusable-backend-tests.yml) |
| INFRA-07 | CLOSED | Backend Docker healthcheck uses readiness endpoint. [Backend Dockerfile](../../backend.Dockerfile), [health routes](../../app/api/health.py) |
| INFRA-08 | CLOSED | File processor Compose service keeps its expected healthcheck. [Go Compose](../../docker-compose.go.yml) |
| INFRA-09 | CLOSED | Observability Compose dependency resolves to an existing Tempo health helper/service. [Observability Compose](../../docker-compose.observability.yml) |
| INFRA-10 | CLOSED | Gateway chart retains autoscaling configuration. [Helm values](../../charts/university-ecosystem/values.yaml) |
| INFRA-11 | CLOSED | Standalone ingress issuer stays configurable rather than hard-coded. [Ingress](../../k8s/ingress.yaml) |
| INFRA-12 | DECLINED | Weekly cleanup fails closed on missing required DB secret: on main this signals retention silently stopped; a warning/skip hides the operational failure. [Workflow](../../.github/workflows/weekly-cleanup.yml), [contract](../../tests/test_workflow_fail_closed_contracts.py) |
| SEC-01 | CLOSED | GraphQL trusts identity only after internal gateway HMAC verification. [GraphQL schema](../../app/graphql/schema.py), [ADR-013](../adr/ADR-013-secret-rotation.md) |
| SEC-02 | CLOSED; duplicate issue family | Preserve dual-key JWKS handling under the separate SEC-02 ID as well as GO-02. [Gateway auth](../../services/gateway/middleware/auth.go), [ADR-013](../adr/ADR-013-secret-rotation.md) |
| SEC-03 | CLOSED in historical source review | Do not include the old key value. User confirmed ephemeral CI/demo use only, not persistent DB/deployments; this alone does not justify production rotation. Before any retained-signature migration require protected consistent backup and read-only inventory. Preserve both DataAccessLog legacy payload verifiers (JSON-array and pipe-delimited, with differing signed fields) and inventory hash-linked versus nullable StoredEvent rows; migrate atomically/fail closed, never imply old HMAC authenticated unsigned fields. [Security settings](../../app/core/config/security.py), [master plan](../superpowers/plans/MVP_MASTER_PLAN.md) |
| SEC-04 | CLOSED | Go structured logs retain shared PII redaction. [Go logging package](../../services/pkg/logging/) |
| SEC-05 | CLOSED | Quality floor validation remains fail-closed; no zero-floor bypass. [Quality contract](../../quality/quality-contract.json), [validator](../../scripts/quality/validate_quality_contract.py) |
| SEC-06 | CLOSED | Gitleaks allowlists refer to existing lock files; PR branch filter semantics are base-branch based. [.gitleaks.toml](../../.gitleaks.toml), [workflow](../../.github/workflows/gitleaks.yml) |
| SEC-07 | CLOSED historical; recheck baseline | Use detect-secrets is_secret triage, not is_verified; revalidate current baseline entries/count, never repeat stale 326/321 as current. [Baseline](../../.secrets.baseline), [triage validator](../../scripts/verify_secrets_baseline.py) |
| SEC-08 | CLOSED | Bandit target and Windows encoding behavior remain compatible with pre-commit. [pre-commit](../../.pre-commit-config.yaml), [project config](../../pyproject.toml) |
| SEC-09 | CLOSED | Bound external production dependencies only; keep dev tooling and workspace packages outside this finding’s scope. Current inventory is described in [ADR-035](../adr/ADR-035-python-dependency-compatibility-policy.md), not by the old 19 count. |
| SEC-10 | CLOSED; duplicate issue family | Keep SCAN instead of KEYS under the separate SEC-10 ID as well as GO-05. [uni-cli](../../services/cmd/uni-cli/main.go) |
| SEC-11 | CLOSED; duplicate issue family | Keep readiness endpoint in Docker healthcheck under separate SEC-11 ID as well as INFRA-07. [Backend Dockerfile](../../backend.Dockerfile) |
| SEC-12 | CLOSED | Mypy hook remains aligned with the supported backend CI scope. [pre-commit](../../.pre-commit-config.yaml), [quality guide](../../TESTING.md) |

### Transfer notes

- The historical ID aliases above are retained for traceability. Do not collapse SEC-02/GO-02, SEC-10/GO-05, or SEC-11/INFRA-07 into fewer IDs.
- Remove stale scorecards, tool/test counts, historical command transcripts, and pre-retirement crate claims from the current index. Preserve them in Git history only.
- The linked decisions and code are evidence sources to revisit, not proof that the finding passes at the final RC SHA.

## Legacy archive cleanup and recovery

The former directories `archive/` and `../superpowers/plans/archive/` contained
112 audit reports and 8 plan snapshots; both are already absent from the current
working tree. Applicable requirements were reconciled against the master plan,
ADRs, tests, and current workflow contracts. The repository history remains the
historical source. The external rescue bundle was verified at rescue SHA
`d0aad7c296facd79b3d41b037bc4160f5b3132be`; `git bundle verify` confirmed its
complete history, two restored sample files matched their inventory blobs, and
the inventory matches all 120 archive paths, blob IDs, and sizes. It is stored
next to the repository as
`../university_ecosystem-rescue-2026-09-30-d0aad7c.bundle`; its SHA-256 is
`7cdaed352df12a0f735f86399dd2937be9c832e60d2f1f0ff66fbbb9bc823b11`.
The 120-file path/blob/size/disposition/transfer inventory is stored next to
the repository as `../university_ecosystem-archive-inventory-d0aad7c.csv`;
after adding a newly found credential reference its SHA-256 is
`20bb5457d104ed2590c33c4940c2f0334f2ba526fb1bff208111f5a99c4cc514`. The
inventory excludes secret values. Archived reports contain credential-shaped
strings. The user confirmed that the Chromatic project token was reset and the
Actions secret updated; secret metadata was checked without reading its value.
The user also confirmed that the seeded-admin password and the historical HMAC
signing-key default were used only in ephemeral CI/demo environments, not in
persistent databases or deployments; no persistent-secret rotation is indicated.
The `DataAccessLog` writer/verifier format mismatch remains relevant to any future
migration of retained signed records, which requires a protected backup and
read-only inventory first. Keep the bundle private and quarantined because it
contains full Git history and credential-shaped strings. Do not copy, distribute,
or restore it for routine work; do not restore removed archive paths or create
another bundle.
No recovery is currently needed. The following commands document an isolated
restore procedure only for a concrete, authorized recovery task. Do not run them
as part of routine archive maintenance:

```powershell
$bundle = Join-Path (Split-Path -Parent (Get-Location).Path) 'university_ecosystem-rescue-2026-09-30-d0aad7c.bundle'
$rescue = Join-Path $env:TEMP 'university-ecosystem-rescue'
git bundle verify $bundle
git clone --no-checkout $bundle $rescue
git -C $rescue checkout d0aad7c296facd79b3d41b037bc4160f5b3132be -- docs/audits/archive docs/superpowers/plans/archive
```

Validate documentation links with `scripts/docs/check_markdown_links.py`.
Keep `--include-archives` as a diagnostic mode for verifying restored snapshots;
do not invent replacement links for files that are not present. A historical
link-check result does not establish the current documentation state.

## Current working references

- [MVP master plan](../superpowers/plans/MVP_MASTER_PLAN.md) — approved scope,
  decisions, sequence, and acceptance criteria.
- [Active closure status](../superpowers/plans/STATUS.md) — current state and
  next actions.
- [Scoped platform review template](../superpowers/plans/AUDIT_PROMPT.md) —
  reusable input for an explicitly assigned review.
- [Machine-enforced quality contract](../../quality/quality-contract.json) —
  mandatory quality gates.

## Historical reports

Current requirements and useful procedures from legacy reports have been
transferred to the master plan, ADRs, and executable contracts. Superseded copies
were removed from the working tree without rewriting Git history. Keep the rescue
bundle and its inventory outside the repository rather than maintaining duplicated
narratives here.

## Maintenance rules

- Record durable architecture choices as ADRs under [`../adr/`](../adr/).
- Record current quality policy in [`../../quality/`](../../quality/) and the
  [testing guide](../../TESTING.md), not in historical audits.
- Do not append prompts, session transcripts, temporary plans, or live status
  notes to audit reports.
- Keep links relative. Do not create new session archives or rotate reports into
  legacy archive directories; indexes should list only current working inputs
  and durable evidence.
