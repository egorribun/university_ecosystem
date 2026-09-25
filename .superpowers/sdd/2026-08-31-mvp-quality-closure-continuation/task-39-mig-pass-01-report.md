# Task 39 — MIG-PASS-01 implementation report

Date: 2026-09-08
Baseline before implementation: `2c6493366a30271f56a73974e0048b35ea46a162`
Implementation commit: `f676532af382dc5e7be1e444bce9541ed945b3c7`

## Outcome

The legacy-password migration command is now a read-only release preflight. It
counts active bcrypt credentials in SQL, optionally samples bounded opaque UUIDs,
and exposes a fail-closed `assert-none` command. The removed Kubernetes Job and
its sole-consumer NetworkPolicy could only perform the deleted pseudo-reset
mutation and were removed after a repository-wide reference scan. No schema,
user state flag, password-reset API, bcrypt verifier, or plaintext credential
path was introduced.

## RED evidence

The stale DML still fails at PostgreSQL compilation, proving that the old
`must_reset_password` mutation was not executable:

```text
sqlalchemy.exc.CompileError: Unconsumed column names: must_reset_password
```

The reproduction exited with status 1 using SQLAlchemy's PostgreSQL dialect.
The former batch implementation also selected rows before filtering in Python,
which could report zero while a bcrypt row remained; the new tests encode the
SQL predicate-before-limit contract instead.

## GREEN evidence

Focused unit and contract tests:

```text
uv run pytest tests/test_cli_migrate_passwords.py \
  tests/test_cli_migrate_passwords_closure.py -q -rA
15 passed in 7.36s
```

The suite covers all `$2a$`, `$2b$`, and `$2y$` prefixes, active filtering,
count-only output, explicit UUID sampling, negative/zero limits, nonzero
`assert-none`, no DML/completion claims, SQL projection/order, and RLS context
reset on both success and query failure.

The real PostgreSQL integration test is present at
`tests/integration/test_cli_migrate_passwords_postgres.py`. It provisions a
digest-pinned disposable PostgreSQL container, a `NOSUPERUSER NOBYPASSRLS`
reader, FORCE ROW LEVEL SECURITY, and mixed legacy/Argon2 rows. It was not
executed on this Windows workstation because the Docker daemon was unavailable
(`dockerDesktopLinuxEngine` named pipe was absent); the default run therefore
reported one explicit skip. This is an environmental limitation, not a green
integration result, and canonical Linux CI must execute it with
`RUN_INTEGRATION_TESTS=1`.

Static checks for the changed Python sources:

```text
uv run ruff check ...                         PASS
uv run mypy --config-file pyproject.toml app/cli/migrate_passwords.py  PASS
git diff --check                               PASS
```

The repository pre-commit hooks passed Ruff, formatting, detect-secrets,
hardcoded-secret detection, Bandit, Python-2-except, and workflow checks. The
Docker-backed `semgrep-docker` hook could not start because Docker was not
running, so it was skipped for this local commit and remains a required CI
gate.

## Privacy and reference audit

`report` prints only the exact count by default. `--show-ids` is an explicit,
bounded opt-in and selects only UUIDs; email addresses, password hashes, reset
tokens, and other account PII are never selected or printed. `assert-none`
returns 0 only for count zero and returns 1 when any active legacy credential
remains; database failures propagate as nonzero failures.

The final case-insensitive repository scan for `force-reset`,
`must_reset_password`, `password-migration`, and `migrate-passwords` found only
the live CLI registration plus historical audit references. No tracked raw
Kubernetes workload invokes the removed mutation command.

## Immutable downstream contract

```text
python -m app.cli migrate-passwords assert-none
exit 0: active legacy bcrypt count is exactly zero
exit 1: one or more active legacy bcrypt credentials remain
output: bounded count only; no email/hash/token
database access: read-only SELECT on users
```

Task 40/42 must invoke this command from the exact digest-pinned backend image
and secret-backed database identity. Missing database connectivity or command
failure is a release failure, never a success or skip.

## Review result and remaining verification

Implementation self-review is PASS for the SQL/read-only/privacy contract and
the focused tests. An independent security review, real PostgreSQL execution,
canonical backend coverage, and mutmut verification remain required in the
downstream CI matrix. No coverage, mutation, security, or CI exclusions were
added.
