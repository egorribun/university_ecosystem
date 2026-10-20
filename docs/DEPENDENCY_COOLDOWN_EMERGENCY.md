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
command. The targeted command above is the default package-specific cooldown
exception; an explicitly approved exact-release timestamp cutoff may be used
instead when recorded below and preserved in both project and lock metadata.

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

## Owner-approved Rclone exception, 2026-10-14

The owner approved only `rclone/rclone:1.75.2` for the backup upload image in
PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306). The
[official changelog](https://rclone.org/changelog/#v1-75-2-2026-10-09) identifies
Go security fixes including CVE-2026-78660 and CVE-2026-97031. The exception
covers only the seven-day release-age requirement for this version and its
verified manifest digest in `charts/university-ecosystem/values.yaml`.
It expires on 2026-10-16 at 11:03:19 UTC, seven days after the release.

The backup command remains an S3-client `mkdir` followed by `copyto`; the
reviewed Helm renders differ only in the upload image. No deployment, new
secret disposition, advisory waiver or merge bypass is authorized by this
decision. Ordinary hooks, vulnerability and backup compatibility checks,
78 required contexts and blocking CodeQL remain required on the final source.

## Owner-approved Certifi exception, 2026-10-20

The owner approved only certifi `2026.10.19` in the existing normal PR
[#1306](https://github.com/egorribun/university_ecosystem/pull/1306), addressing
[GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
The owner is the approving security reviewer. The fixed release removes the
affected emSign trust anchor; no TLS verification or advisory gate is disabled.

The exact version constraint and package-specific cutoff
`2026-10-20T02:24:17Z` admit this release without admitting subsequent uploads.
The global seven-day maturity policy and every other package remain unchanged.
The exception covers the matching certifi version and artifact hashes in
`uv.lock` and `security/detect-secrets-requirements.txt`. It expires on
2026-10-27 at 02:24:17 UTC, after both release artifacts have matured.
Remove the cutoff and replace the temporary exact pin with the security floor
through a reviewed, targeted lock refresh at that point.

For this exact approved release, use pinned uv 0.12.23 and the recorded
persistent cutoff with `uv lock --upgrade-package "certifi==2026.10.19"`,
then `uv lock --check`. Review the `uv.lock` diff: only certifi, its exact
manifest constraint and its package cutoff may change. The temporary hosted
generation step restores the checked-in lock before the normal lock gate;
a generated candidate is not a passing checked-in-source validation.
Final-source lock consistency, scanner integrity, tests and vulnerability
checks remain required. No baseline edit, new false-positive disposition,
advisory waiver, merge or deployment is authorized by this exception.

The bounded generation was executed on source `dd27830a` in
[run 39494503454](https://github.com/egorribun/university_ecosystem/actions/runs/39494503454),
job 118875905694. The candidate passes `uv lock --check`; all other 229 package
records remain unchanged. The original lock was restored and the ordinary
checked-in lock gate correctly refused it. The reviewed generated diff is
integrated by the follow-up, which removes the temporary generator. This
records generation provenance, not a passing final-source security gate.

## Owner-approved Pillow exception, 2026-10-20

At 21:57 UTC the owner separately approved Pillow `13.0.0`, the direct major
range change to `>=13.0.0,<14`, and its exact-release cooldown exception in
normal PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
The owner is the approving security reviewer. The current Pillow 12.3.0 gate
reports CVE-2026-112395, CVE-2026-112397, CVE-2026-112400,
CVE-2026-112403, CVE-2026-112404, CVE-2026-112895, CVE-2026-112896,
CVE-2026-112897 and CVE-2026-112899.
[Upstream 13.0.0 release](https://github.com/python-pillow/Pillow/releases/tag/13.0.0)
and [release notes](https://github.com/python-pillow/Pillow/blob/13.0.0/docs/releasenotes/13.0.0.rst)
describe the security and compatibility changes.

Only Pillow receives the additional cutoff `2026-10-16T22:18:10Z` and exact
constraint `pillow==13.0.0`. The targeted command is
`uv lock --upgrade-package "pillow==13.0.0"`, with pinned uv 0.12.23.
The certifi exception, global seven-day policy and all unrelated constraints
remain unchanged. Remove the Pillow cutoff and review the temporary exact pin
after 2026-10-23 at 22:18:10 UTC, once the admitted artifacts have matured.

The temporary existing-job generator fetches bounded HTTPS release metadata
from PyPI without redirects. It validates each generated artifact's URL, digest,
size, non-yanked status and upload time against that inventory and the cutoff.
Whole-lock comparison permits only the Pillow package, its cutoff/constraint
and the root project's direct Pillow requirement metadata. The generated diff
is limited to 128 KiB. The original lock is restored before the normal
`uv lock --check`; that checked-in gate must remain failing until the reviewed
candidate is integrated. Artifact records are not authored manually.

Real AVIF tests exercise both explicitly selected native and external handlers
with RGB/RGBA inputs; real Pillow-only RGBA/LA thumbnail tests check transparency
and lossy color fidelity. They do not prove plugin-absent startup, deployment,
or every image format. Existing privacy, image-budget and upload regressions,
ordinary hooks, final-source lock consistency and vulnerability gates remain
required. At this preparation checkpoint the new lock and real-codec results
are not yet verified. No advisory waiver, scanner disposition, baseline edit,
merge or deployment is authorized by this exception.

The hosted generator on source `19509334`,
[run 39505978632](https://github.com/egorribun/university_ecosystem/actions/runs/39505978632),
job 118914878260, validates the source distribution and 47 wheels against PyPI.
Merge checkout `fc5b468231e3f9ff8b693679f344cdfae83ad121` has the same tree
`66babb04edf7b7e1ccb3072306016db51fe64541`. Candidate lock checking and the
whole-lock scope guard pass; the restored original lock then fails normally.
The reviewed 131-line diff is integrated and the temporary generator removed.
Final-source compatibility and vulnerability checks remain required.

The initial metadata guard rejected sub-millisecond precision: authoritative
PyPI time `22:18:09.718711Z` versus generated `22:18:09.718Z`.
Pinned [uv 0.12.23 stores milliseconds](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-distribution-types/src/file.rs#L56).
The corrected comparison uses exact millisecond truncation, not a tolerance;
the unmodified raw PyPI timestamp still must meet the original cutoff.
Both the observed truncation and distinct-millisecond rejection controls pass
inside the successful generator. No upload-time boundary was relaxed.
