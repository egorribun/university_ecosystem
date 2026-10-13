# Dependency Cooldown Emergency Procedure

Routine PyPI releases must remain outside the seven-day maturity window. Use this
procedure only when a confirmed advisory requires a fixed release sooner. It keeps
the security Renovate alert visible immediately, but the resulting PR must not
automerge.

Renovate expresses this sole immediate-security path through
`vulnerabilityAlerts` with `minimumReleaseAge: null` and `prCreation: immediate`;
all routine package rules retain the seven-day maturity window.

## Required approval record

Before changing the lockfile, open a normal PR that records all of the following:

- advisory ID (CVE/GHSA/OSV)
- exact package
- fixed version
- normal PR
- security reviewer
- normal test/vulnerability-gate evidence

The security reviewer must approve the targeted exception before it is merged.

## Targeted lock regeneration

Run this command only after the record above is complete, substituting the affected
package name exactly once:

```shell
uv lock --upgrade-package "<package>" --exclude-newer-package "<package>=false"
```

Then run:

```shell
uv lock --check
```

Then, review the `uv.lock` diff and confirm it contains only the named package's
security fix and the expected cooldown metadata. Run the normal test and
vulnerability gates, attach the evidence to the normal PR, and obtain the
security reviewer approval.

For ordinary regeneration, use `uv lock`. Never use the broad `uv lock --upgrade`
command; the targeted command above is the sole package-specific cooldown
exception.

## Prohibited bypasses

Do not use `--exclude-newer false`.

Do not use `UV_EXCLUDE_NEWER=false`.

Do not use `Semgrep suppression`.

Do not use `SKIP=semgrep`.

Do not use `--no-verify`.

## Owner-approved Rust exception, 2026-10-12

The owner approved only Ammonia `4.2.3` in PR
[#1306](https://github.com/egorribun/university_ecosystem/pull/1306), addressing
[RUSTSEC-2021-0157](https://rustsec.org/advisories/RUSTSEC-2021-0157.html).
The approval covers the seven-day release-age requirement for the Ammonia
version/checksum entries in `frontend/wasm-sanitizer/Cargo.lock` and
`frontend/wasm-sanitizer/fuzz/Cargo.lock`. Version `4.2.3` reaches seven days on
2026-10-18 at 06:27:36 UTC; the exception then expires.

This decision does not change routine cooldown rules, Cargo Deny configuration,
vulnerability gates, tests, or the ordinary PR flow. Sanitizer tests, the WASM
rebuild/provenance checks, and required CI must still pass on the updated source.
The owner is the approving reviewer; approval does not substitute for that
validation evidence.
