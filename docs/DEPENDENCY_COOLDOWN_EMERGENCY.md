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

Do not use `SKIP=semgrep-docker`.

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

## Owner-approved Go exception, 2026-10-21

The owner approved a narrowly scoped exception to the seven-day cooldown for
Go 1.26.10, the fixed release for GO-2026-6809 (CVE-2026-111943), and fuzz-toolchain
Go 1.27.3. The exception covers only those compiler pins and their corresponding
official Go container images. The multi-platform index digests are:

- alpine3.24: `sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca`
- bookworm: `sha256:fe3da92a5cb2881e4aa75e625cb0b7c50571632fb4cf340cbe53e6ccdcffdd51`

These image indexes were verified against docker-library/repo-info commit
01a4608bd03cd0733af707340902e3308f7b2e76 (2026-10-21 08:01:24 UTC).
See the [official advisory](https://github.com/golang/vulndb/blob/e0bad56276e98711a598adbab976de7cd914013a/data/reports/GO-2026-6809.yaml),
[alpine record](https://github.com/docker-library/repo-info/blob/01a4608bd03cd0733af707340902e3308f7b2e76/repos/golang/remote/1.26.10-alpine3.24.md),
and [bookworm record](https://github.com/docker-library/repo-info/blob/01a4608bd03cd0733af707340902e3308f7b2e76/repos/golang/remote/1.26.10-bookworm.md).

The seven-day policy for all other releases remains unchanged. No module or
dependency requirements, go.mod/go.sum, scanner policy or dispositions,
suppressions, baseline, hooks, required contexts, merge, or deployment are part
of this approval. Ordinary security, test, and hosted gates remain required.


## Owner-approved Virtualenv exception, 2026-10-21

At 22:44 UTC the owner approved only virtualenv `21.14.9`, replacing
`21.14.7` in the existing normal PR
[#1306](https://github.com/egorribun/university_ecosystem/pull/1306), for
[GHSA-c978-59m8-c77v](https://github.com/github/advisory-database/blob/4661ff0468dac85b4c01cd8f7ae4f1c50858a278/advisories/github-reviewed/2026/10/GHSA-c978-59m8-c77v/GHSA-c978-59m8-c77v.json).
The owner is the approving security reviewer. The
[official fix](https://github.com/pypa/virtualenv/pull/3417) shipped in
[21.14.9](https://github.com/pypa/virtualenv/releases/tag/21.14.9).
The project keeps this dependency in development tooling, not runtime requirements.

Only virtualenv receives the artifact cutoff `2026-10-17T16:09:43Z`,
the temporary exact constraint `virtualenv==21.14.9`, and the durable dev
floor `virtualenv>=21.14.9`. The wheel and source archive were uploaded
at 16:09:40.584Z and 16:09:42.345Z respectively; the GitHub release was
published at 16:09:47Z, a distinct timestamp. The cutoff is bounded to the
verified artifacts, not the later advisory publication date. Review removal
of the cutoff and temporary exact constraint after 2026-10-24 16:09:43 UTC;
retain the patched security floor. Certifi/Pillow exceptions and the routine
seven-day policy remain unchanged. A newer virtualenv release is not authorized.

The candidate package stanza is cross-checked against two immutable public
lockfiles: [ConfigUpdater](https://github.com/pyscaffold/configupdater/blob/c93003797846da216e2f333d11133200b96b2d91/uv.lock)
and [starknet-crypto-py](https://github.com/tradeparadex/starknet-crypto-py/blob/df220aac5f532c983bddddbd19c304de10e334f9/poetry.lock).
Its transitive requirements are unchanged. A temporary bounded existing-job
verification checks all artifact URLs, digests, sizes, non-yanked status and
upload times against bounded non-redirected official PyPI metadata. It then
runs pinned uv 0.12.23 with
`uv lock --upgrade-package "virtualenv==21.14.9"` and rejects any difference
from the reviewed lock. The original lock is always restored before the
ordinary `uv lock --check`; the temporary verification step is removed after
successful hosted verification. This records the required procedure, not a
claim that generation, installation or audit has already succeeded.

Normal hash-verified installation, final-source lock consistency, regression
and vulnerability gates still apply. No GHSA allowance, scanner disposition,
baseline edit, global cutoff change, merge or deployment is authorized.
Upgrading virtualenv does not repair previously generated environment scripts;
affected existing environments require recreation with patched tooling before
use. The known trigger requires later execution of a generated POSIX launcher
under an attacker-influenced destination path; this is not a claim of compromise.

## Owner-approved ctutils exception, 2026-10-23

The owner approved only `ctutils 0.4.4` in PR
[#1343](https://github.com/egorribun/university_ecosystem/pull/1343), addressing
[RUSTSEC-2026-0385](https://github.com/rustsec/advisory-db/blob/main/crates/ctutils/RUSTSEC-2026-0385.md).
The approved checksum is the exact value in the four lock records, verified
against the [official release metadata](https://crates.io/api/v1/crates/ctutils/0.4.4).
Approval covers only the version/checksum records in `native/rust_ext/Cargo.lock`,
`native/rust_ext/fuzz/Cargo.lock`, `frontend/rust-crypto/Cargo.lock` and
`frontend/rust-crypto/fuzz/Cargo.lock`. It expires when the release reaches seven
days on 2026-10-30 at 01:04:28.877964 UTC.

The owner is the approving reviewer. Independent private candidate checks passed
with cargo-audit 0.22.2 across the seven SBOM lockfiles and cargo-deny 0.20.2 across
the three production crates. The audit results were retained only as console
evidence, not raw JSON reports. These checks do not establish compilation or
final-source CI. All ordinary tests, WASM provenance, vulnerability gates, hooks
and required contexts remain mandatory; no advisory waiver or scanner exception
is authorized.

## Owner-approved Brotli exception, 2026-10-23

For PR [#1343](https://github.com/egorribun/university_ecosystem/pull/1343), the owner approved a package-specific artifact cutoff of `2026-10-22T14:00:13Z` for `brotli` `1.2.1`, addressing `PYSEC-2026-4322` / `CVE-2026-111497`. The temporary constraint is `brotli==1.2.1`; retain the durable floor `brotli>=1.2.1,<2`. The artifact cutoff and temporary exact constraint expire at `2026-10-29T14:00:13Z`; review and remove the temporary cutoff and pin at that time while retaining the patched floor. See [Brotli 1.2.1 on PyPI](https://pypi.org/project/brotli/1.2.1/).

This approval is limited to the named package and cutoff. The routine seven-day policy for other releases remains unchanged. It does not authorize a global `exclude-newer` change, advisory suppression, scanner disposition, baseline edit, hook or required-context change, or workflow identity. This record does not claim lock generation, installation, vulnerability audit, final-source validation, hosted checks, or release success; the ordinary dependency and security gates remain required. See the [current policy checkpoint](superpowers/plans/STATUS.md#owner-approved-scanner-and-brotli-boundaries-2026-10-23).

## Owner-approved body-parser exception, 2026-10-24

The owner explicitly approved a package-specific seven-day cooldown exception
for only `body-parser 1.20.9` in the ongoing normal PR
[#1343](https://github.com/egorribun/university_ecosystem/pull/1343), addressing
GHSA-27r3-jxmh-p828 / CVE-2026-111181. The owner is the approving security
reviewer. The exception covers only the existing development-tooling transitive
record in `frontend/package-lock.json`: version, resolved URL and integrity
for `node_modules/body-parser`, from 1.20.8 to exactly 1.20.9. Its parent Express
range already accepts this patch; no direct application dependency is introduced.

The bounded scratch generator succeeded in
[run 40045867045, job 120727506876](https://github.com/egorribun/university_ecosystem/actions/runs/40045867045/job/120727506876).
It verified the official npm publication timestamp
`2026-10-22T11:38:27.889Z`, the archive URL and both SHA-512/SHA-1 digests.
This differs from the upstream GitHub release timestamp
`2026-10-22T11:33:51Z`. The exact-release exception expires at
`2026-10-29T11:38:27.889Z`, seven days after the verified npm publication.

Generation used declared npm 11.17.0 on Node 24.21.0, isolated empty npm
configuration files and a token-free subprocess environment. Install-time
lifecycle scripts were disabled. Resolution happened only in a bounded scratch
mirror; the checked-in source was never modified. Whole-lock comparison and
the bounded diff verified that only the three approved artifact fields changed.
Source merge checkout `be3f679854de377e82578b2dea7a6f45ca594287` and source
commit `3de6d3d33a0ad497c718f5f02a5f5d580d52d068` have the identical tree
`1953a557b5782953dfe7be5b908601656945ea76`.

The original lock SHA-256 was
`d042e0f9e15b2cd2cb229b4a5e99184f67b4c6b1308895190024d976afd051d0`;
the reviewed npm-generated candidate is
`c9abaad83f2316b792825f61040290c2f5dcb950af683dc1cfef7a461983c0f6`.
The follow-up integrates that exact candidate and removes the body-parser
generator. The ordinary audit correctly failed against the untouched original
lock, also reporting Zod and Undici findings; candidate generation is not
evidence that the updated source passes the full audit.

No other package receives a cooldown exception. The existing npm configuration,
normal dependency installation and audit commands remain unchanged. This
approval does not cover Zod, Puppeteer, Undici, any advisory allowance, scanner
disposition, baseline, hook, required context, merge or deployment. Normal
lock consistency, tests, vulnerability gates and all required hosted checks
remain mandatory on the final source.


## Owner-approved Caddy Alpine Brotli exception, 2026-10-24

The owner separately approved only `brotli-libs=1.2.1-r0` from the official
Alpine 3.23 repositories in PR
[#1343](https://github.com/egorribun/university_ecosystem/pull/1343), addressing
CVE-2026-111497. The owner is the approving security reviewer. This is distinct
from the earlier PyPI Brotli exception; no other package or release is admitted.

The source-bound failure is
[run 40049236347, job 120738976897](https://github.com/egorribun/university_ecosystem/actions/runs/40049236347/job/120738976897)
for source `772a17927a1aa0cc89ff974d46e669d56b3bccd7`: Trivy identifies
Alpine 3.23.6, installed `brotli-libs 1.2.0-r0`, fixed `1.2.1-r0`, and HIGH
CVE-2026-111497. Alpine's
[3.23 security upgrade](https://github.com/alpinelinux/aports/commit/613a63bfdea80e8e7ab904805c95e19beedbcde3)
and [security annotation](https://github.com/alpinelinux/aports/blob/06a99b3e1a170b721212a85927391fdd26128460/main/brotli/APKBUILD)
identify that exact fix. Git commit dates are not APK publication timestamps;
binary repository availability and package maturity are not established by them.

The exception expires no later than `2026-10-31T02:00:00Z`. This is a finite
administrative boundary, not a claim that the APK reaches seven days then.
Before that boundary, review authoritative package publication evidence and
record maturity or seek a new specific owner decision if it remains unproven.
Expiration does not authorize a vulnerable rollback or a broader exception.

The only runtime dependency change is the exact package added to the existing
version-pinned `apk add` list. Both image digests, Caddy/xcaddy/plugin/Go module
pins, Alpine repository configuration and APK signature verification remain
unchanged. A normal hosted build must obtain the exact signed package or fail.
The existing Caddy image-scan job then checks the installed version and records
the Alpine release/repositories in a bounded, read-only, network-disabled
container without mounts or supplied credentials. The ordinary Trivy scan
remains blocking and unchanged. The three smoke workflows that directly run
unmodified upstream Caddy images retain their existing digest pins; this
custom-runtime fix does not establish that those CI-only images are patched.

At this preparation checkpoint, the updated image has not been built or scanned;
APK availability, installed-version proof, compatibility tests and final-source
hosted checks remain pending. This exception authorizes no image push,
deployment, merge, advisory waiver, scanner disposition, baseline or hook change,
new required context, or global cooldown-policy change.

## Routine Undici repair (no exception), 2026-10-24

Undici `8.12.2` repairs GHSA-xjj6-f33q-929c, GHSA-4qv8-2p9j-2685 and
GHSA-f72v-6w45-q472 in the existing development-tooling dependency. The
[official release](https://github.com/nodejs/undici/releases/tag/v8.12.2)
identifies the fixes. No cooldown exception is requested or applied.

The bounded hosted generator succeeded in
[run 40053749654, job 120752636880](https://github.com/egorribun/university_ecosystem/actions/runs/40053749654/job/120752636880).
All ten guard tests passed before generation. Official npm metadata records
publication at `2026-10-15T15:05:34.415Z`; the release reached seven days on
`2026-10-22T15:05:34.415Z`. Both the pinned npm 11.17.0 tool archive and the
Undici archive passed publication-age and SHA-512/SHA-1 verification.
The npm 11.17.0 release was published on `2026-06-11T18:42:34.887Z`.

Generation ran on Node 24.21.0 with declared npm 11.17.0, using a six-minute
operation deadline, bounded archive downloads, zero transport retries and
disabled lifecycle scripts. Resolution took place only in an isolated scratch
mirror with a token-free subprocess environment. The checkout remained
unchanged. Whole-lock comparison and the bounded emitted patch permit only
`version`, `resolved` and `integrity` for `node_modules/undici`, from 8.11.0
to 8.12.2; the integrated body-parser 1.20.9 fix and every other record remain
unchanged. The existing manifest override and normal seven-day policy are
unchanged.

Source commit `f70570f3` and merge checkout `5a64a37f` have the same tree.
The follow-up replays the exact npm-generated patch, verifies both complete
lock digests against the emitted evidence, and removes the completed temporary
generator, its tests, steps and exact temporary protected-path entries.
The separately protected React Compiler artifact probe is retained.

This proves bounded candidate generation, not a passing final-source audit.
The later compiler-probe tests intentionally failed against their unimplemented
stub; the normal installation and audit steps did not execute in this job.
The read-only advisory diagnostic still reported the original Undici and Zod
findings. Normal lock consistency, compatibility tests, vulnerability checks
and all required hosted gates remain mandatory after integration. No advisory
waiver, scanner disposition, baseline change, global cooldown change, merge or
deployment is authorized by this routine repair.

## Caddy runtime evidence and smoke-wiring follow-up, 2026-10-24

The earlier preparation-only statements above describe their recorded source,
not the later result. On source `8db323bc`,
[custom Caddy job 120757133521](https://github.com/egorribun/university_ecosystem/actions/runs/40055175068/job/120757133521)
successfully built the image, verified installed `brotli-libs=1.2.1-r0` in
the bounded offline container, and passed the blocking Trivy scan.
This does not certify every later source or all upstream Caddy images.

The smoke follow-up configures visual-audit, admin-smoke-monitoring and
unauthenticated-routes-smoke to build that same project Dockerfile at their
exact checkout SHA instead of running the unmodified upstream runtime directly.
Both base digests and all package/module pins remain unchanged. Builds load a
local image and do not push; runtime inherits UID 100:101 and uses an
unprivileged HTTP listener on 8080. Browser, backend and SSR origins agree.
Generated public routing config uses RUNNER_TEMP with mode 0444 and a read-only
bind. Explicit matching JWT_ISSUER supplies the pre-existing production-SSR
configuration prerequisite without disabling issuer or signature checks.

The three contract cases failed on the previous source before its Contract job
was cancelled. The full new workflow builds/startup/browser checks remain
unverified at integration. The unauthenticated lane is PR-triggered;
visual/admin remain manual and their exact-source runtime results are not
inferred from source review or unrelated jobs. No trigger, permissions,
timeout budget, advisory waiver or release/deployment authorization is added.
The original finite Brotli exception and its expiry are unchanged.

## Exact Caddy curl/libcurl exception, 2026-10-27

The owner authorized the early security update to exactly `curl=8.23.0-r0`
and `libcurl=8.23.0-r0` in `services/caddy/Dockerfile` for PR #1343, with
matching startup-contract expectations. Other package and image pins and the
general seven-day cooldown remain unchanged. No publication-age or expiry
timestamp is inferred from this decision.

This authorization does not establish a passing build, installed-version
check, compatibility test or Trivy result; those checks remain mandatory for
the final source. The earlier finite Brotli exception remains separate. See
[ADR-047](adr/ADR-047-risk-based-quality-policy.md#exact-caddy-dependency-cooldown)
for the bounded owner decision.
