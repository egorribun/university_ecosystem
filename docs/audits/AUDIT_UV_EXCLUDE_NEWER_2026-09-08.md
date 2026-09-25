# Audit: `uv` `exclude-newer` configuration

Date: 2026-09-08
Repository: `egorribun/university_ecosystem`
Configured toolchain: `uv==0.11.28`

## Scope

The quality-closure plan records a historical Linux CI warning for
`[tool.uv] exclude-newer = "7 days"` and requires an exact reproduction before
changing the representation.  This note records the bounded reproduction and
the decision about whether a project or lockfile change is justified.

## Configuration under audit

- `pyproject.toml`: `required-version = "==0.11.28"` and
  `exclude-newer = "7 days"`.
- `uv.lock`: `options.exclude-newer-span = "P7D"`.
- No dependency requirement or resolved package was changed during this audit.

The current uv documentation explicitly lists both friendly durations (for
example, `7 days`) and ISO 8601 durations (for example, `P7D`) as supported
values for `exclude-newer`:

- [uv CLI reference](https://docs.astral.sh/uv/reference/cli/#--exclude-newer-exclude-newer)
- [uv settings reference](https://docs.astral.sh/uv/reference/settings/#exclude-newer)

## Reproduction evidence

### Windows developer environment

The required local binary reports `uv 0.11.28 (ebf0f43d7 2026-07-07
x86_64-pc-windows-msvc)`.

```text
uv lock --check --verbose
Resolved 258 packages in 3ms
exit 0
```

`uv sync --frozen --dry-run --verbose` also exits 0 and emits no
`exclude-newer` warning.  Its package-environment differences are the expected
result of this workstation's existing virtual environment and are not a lock
or resolver failure.

### Linux parser/resolver reproduction

To exercise the Linux build of the exact pinned uv version without Docker, the
`uv-x86_64-unknown-linux-musl` 0.11.28 release binary and the CPython 3.14.6
musl standalone build were run from a mounted temporary directory.  The
workspace itself was read-only for these commands (`--check`/`--dry-run`).

```text
uv lock --check --python <python-3.14.6-musl> --verbose
Using CPython 3.14.6 interpreter
Existing `uv.lock` satisfies workspace requirements
Resolved 258 packages in 99ms
exit 0; no warning

UV_EXCLUDE_NEWER=P7D uv lock --check --python <python-3.14.6-musl> --verbose
Existing `uv.lock` satisfies workspace requirements
Resolved 258 packages in 112ms
exit 0; no warning

uv sync --frozen --dry-run --python <python-3.14.6-musl> --verbose
Would install the locked 258-package environment
exit 0; no warning
```

The friendly project value and an explicit `P7D` override therefore produce the
same locked package set under uv 0.11.28.  No parser rejection or resolver
drift is reproducible.

### Fresh hosted CI signal

The latest available Linux-hosted matrix run (`34169372392`, 2026-09-07) used
`astral-sh/setup-uv` with the project-pinned 0.11.28 binary.  The inspected
setup/lock/sync logs for `Verify Runtime Requirements`, `Pre-commit Security &
Types`, `Backend Type Check`, `Alembic Migrations`, and `MSW Mock Drift Gate`
contain no `exclude-newer`, `7 days`, or `P7D` warning.  The warnings present in
those logs are unrelated Git/Node/application warnings.

## Decision and bounded remainder

No source or dependency change is justified by the available evidence:

1. uv 0.11.28 officially supports the current friendly representation.
2. The exact pinned version accepts it on Windows and Linux and resolves the
   existing lockfile without warning.
3. The ISO form is already recorded in the lock metadata as `P7D`.
4. Replacing `7 days` with `P7D` would be a representation-only churn without a
   reproduced defect, and would violate the plan's fail-closed diagnostic rule.

The remaining evidence boundary is an exact hosted Ubuntu/glibc reproduction
of the historical warning.  Docker is unavailable in this workstation, so
that runner-image check remains CI-owned.  If a fresh pinned-uv Ubuntu run
again emits a project-owned warning, make the minimal one-line `P7D` change,
update the configuration contract assertion, and rerun `uv lock --check` and
`uv sync --frozen` without regenerating `uv.lock`.  Otherwise retain this note
as the audit record and do not alter the dependency graph.
