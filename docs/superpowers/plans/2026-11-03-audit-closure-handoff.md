# Audit closure handoff (2026-11-03)

Temporary work plan for the agent that continues AUDIT-2026-10 closure while the
owner is away. Delete this file and
[2026-11-03-audit63-lanes.md](2026-11-03-audit63-lanes.md) when the work is done.
It records no new audit acceptance: the accepted lower bound stays as stated in
[docs/audits/INDEX.md](../../audits/INDEX.md) until hosted evidence is reconciled.

## Start here

1. Read [AGENTS.md](../../../AGENTS.md) in full. Work only on branch `egorribun`
   (PR #1343 against `main`). `git fetch` first: other agents may have pushed.
2. The branch tip contains one **unfinished** commit,
   `wip(security): checkpoint ue_app privileges, WebSocket tenant scope and NATS send diagnostics`.
   Its hooks passed, but tests in it still fail. Finish it with new commits on
   top; never amend or force-push.
3. Then work through the lanes in
   [2026-11-03-audit63-lanes.md](2026-11-03-audit63-lanes.md).

## State at handoff

- All commits before the WIP were made with normal hooks and were verified
  locally. CI on `5166149b9`: 19 workflows green, including Dependency Review,
  Nilaway, CodeQL, Gitleaks and Zizmor. CI Matrix and Owned Live Acceptance had
  not finished; check the latest SHA.
- Owned Live Acceptance, step "Run owned NATS outage acceptance", fails with
  `outcome=failed stage=send` since `b8c94de9c`; last pass was on `e6bbbb5b4`.
  The runs in between failed earlier, so no commit is identified yet.
- Inventories: detect-secrets baseline 242, disposition policy 361, Gitleaks 27.

## Step 1: finish the WIP commit

- **ue_app least privilege** (`infrastructure/postgres-roles/bootstrap-app-roles.sql`,
  `tests/test_app_db_role_bootstrap_postgres.py`, `tests/test_app_db_role_contract.py`).
  Verified on PostgreSQL 17 before the change: `ue_app` had UPDATE/DELETE on
  `data_access_logs` and its partitions and on `stored_events`, privileges on
  `alembic_version`, and INSERT/UPDATE/DELETE on `tenants`. Target: the runtime
  role keeps only what runtime code uses (prove each grant from code paths),
  nothing on `alembic_version`, and retention jobs keep working as `ue_worker`.
  The owned PostgreSQL tests were erroring when work stopped; make them pass
  with behavioural assertions (denied operations raise `insufficient_privilege`).
- **WebSocket tenant scope** (`app/core/middleware/tenant.py`,
  `tests/test_ws_tenant_scope.py`): confirm that a WebSocket connection cannot
  reach tenant-scoped data without tenant binding, and keep the test.
- **`app/server/gunicorn_conf.py`** was removed as unused. Confirm that nothing
  (Dockerfile, charts, compose, tests) references it.
- **NATS send diagnostics** (`scripts/owned_nats_http_adapter.py`,
  `scripts/owned_nats_coordinator.py`, `scripts/live_stand.py` and their tests).
  On a send failure the adapter reports one closed phase token: `http_status=<n>`,
  `timeout`, `connect_error`, `body_mismatch` or `not_ready`. The coordinator sets
  a dedicated checkpoint before the send. The final line reads
  `... stage=send checkpoint=<name> phase=<token>`. Four `OutageResult`
  field-set contracts still failed. Never print a URI, header, body or
  exception text. The next CI run then shows the real cause; fix that cause.

## Rules that must hold

- No `--no-verify`, force-push, admin bypass or `Co-Authored-By` trailer. Do not
  merge PR #1343 before every required check is green on the exact SHA. Do not
  tag v1.0.0, publish to GHCR or deploy: those need the owner.
- Never weaken a gate, threshold, required check or coverage floor. Do not add
  `pragma: allowlist secret`, `type: ignore`, `nosemgrep`, skip or xfail. A
  `# noqa: S603  # <reason>` on a fixed-argv subprocess call is the accepted
  convention.
- Security inventories: 1:1 rebinds of existing identities (same path and type)
  and removal of identities whose file is gone are allowed. A brand-new
  identity needs the owner. Prefer code that keeps public hex ids out of
  literals, as `tests/test_verify_secrets_baseline.py` does by reading them
  from source lines.
- `.github/workflows/reusable-backend-tests.yml` has an exact reviewed-bytes
  model in `tests/test_verify_secrets_baseline.py`. Any edit needs a matching,
  narrowly anchored model change.
- Audit documents (`docs/audits/**`) change only after hosted CI is green on an
  exact SHA, with named job receipts. Original acceptance criteria are never
  narrowed.

## Owner decisions in force

- ADR-051: one Alembic baseline `202611020000`. Squawk lints changed migrations
  with `--diff-filter=ACMR`, so deleted revisions are skipped.
- go-jose/v3 GHSA-mgcc-cww5-fp2q: bounded exception only for
  `services/caddy/go.mod`, owner egorribun, until 2027-01-10.
- `howett.net/plist` license: one name-only `allow-dependencies-licenses` entry,
  bound by `scripts/quality/verify_dependency_review_scope.py` to
  `services/caddy/go.mod` version 1.0.1 (ADR-047 note 2026-11-03).
- Ten public Git object ids of the pinned
  `actions/dependency-review-action` v5.0.0 are approved dispositions
  (2026-11-02). The parallel agent's three 2026-11-02 dispositions and one
  Gitleaks record are confirmed.
- Password policy: minimum 12 characters and zxcvbn score of at least 2.
  Internal mTLS uses SPIFFE/SPIRE behind a production-on flag. The application
  database role is not a superuser. Policy changes only tighten.
- Pre-authorized: push verified rounds; rerun CI only for a proven
  infrastructure failure; merge green Dependabot PRs; an ordinary merge of
  #1343 once every required check is green.
- Hard date: 2026-11-13.

## Known follow-ups

- SpiceDB and Temporal still connect as the bootstrap superuser
  (`KNOWN_SUPERUSER_RUNTIME` in `tests/test_compose_runtime_credential_isolation.py`).
  They need dedicated roles.
- ws-hub `NewInternalAPIAuthClient` and `NewHub` still panic on cache
  construction failure (AGENTS.md 2.1 prefers returned errors).
- Test hygiene:
  - a test in `tests/test_full_backend_reusable_contract.py` sits after the
    `__main__` block;
  - two asserts in `tests/test_dependency_resolution_policy.py` and the tier-0
    rglob check in `tests/test_quality_contract.py` are tautological;
  - `tests/test_internal_http_mtls.py` uses a CWD-relative `Path("backend.Dockerfile")`;
  - pgbouncer settings in `tests/test_docker_startup_contracts.py` are checked
    by substring;
  - setup-python pins are duplicated as literals in five tests.
- The frontend OpenTelemetry package set was moved to a coherent older set in
  `eb470c8e4`. Record the reason in an ADR.
- Helm default values fail `helm lint` (pre-existing, fails closed).
