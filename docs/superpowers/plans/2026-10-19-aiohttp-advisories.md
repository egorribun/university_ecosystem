# aiohttp advisory remediation plan

Date: 2026-10-19. GitHub plugin only, egorribun, existing PR1306.

## Evidence

Locked and installed aiohttp3.14.3 fails Python audit job118217794755 on run39298318868. Canonical GitHub-reviewed records:
- [GHSA-494j-54xm-rwp3 / CVE-2026-111063](https://github.com/github/advisory-database/blob/main/advisories/github-reviewed/2026/10/GHSA-494j-54xm-rwp3/GHSA-494j-54xm-rwp3.json).
- [GHSA-5wr8-gcqf-gqf3 / CVE-2026-111064](https://github.com/github/advisory-database/blob/main/advisories/github-reviewed/2026/10/GHSA-5wr8-gcqf-gqf3/GHSA-5wr8-gcqf-gqf3.json).
- [GHSA-2g87-pp6c-29x5](https://github.com/github/advisory-database/blob/main/advisories/github-reviewed/2026/10/GHSA-2g87-pp6c-29x5/GHSA-2g87-pp6c-29x5.json).

All identify3.14.4 as fixed. The [GitHub release](https://github.com/aio-libs/aiohttp/releases/tag/v3.14.4) was published2026-10-05T17:34:36Z, but this does not prove PyPI upload age or wheel hashes. The dependency is transitive through runtime client paths; exploitability and an aiohttp server listener are not established.

## Steps

- [x] Confirm exact locked/installed version and advisory identities.
- [x] Prepare a temporary failure-only hosted resolver probe in the existing pip-audit job, restricted to exact PR1306/head repository/ref.
- [x] Observe actual uv0.12.23 resolution of aiohttp==3.14.4 under normal exclude-newer7days, with fresh cache and actual registry metadata.
- [x] Review complete bounded lock diff and candidate hash; reject unexpected package changes or incomplete output. Never invent checksums.
- [x] Publish the smallest verified lock change and remove the temporary probe.
- [ ] Run lock consistency, frozen installation, dependency audit and applicable full CI before accepting remediation.

The original vulnerability gate remains failed during the probe. No allowlist, cooldown override, new job/context, write credential or auto-commit is introduced. Backup restoration is limited to the probe's lock change; source outside uv.lock must remain unchanged. If the normal resolver rejects maturity, stop and request the specific decision rather than reuse the mimetype-only exception.

## Hosted resolver evidence

Run 39301611872 / job 118229400356 resolved 230 packages with uv 0.12.23 and the normal seven-day cutoff. Only aiohttp changed, 3.14.3 to 3.14.4. The sdist and all 79 wheels were uploaded 2026-10-05; the latest upload was 17:43:48.309Z, more than 14 days before the probe. No cooldown exception was used.

The full candidate lock SHA-256 is 3d9b8b09bbdcdf10b8af3422d658d4b160b58604ee1c627b4a9241ba35b23e6a. Strict unified-diff reconstruction, an independent full-content digest calculation and a second review agree. The resolver's lock check, whitespace check and non-lock tracked-change guard passed. This proves candidate resolution, not yet a passing frozen-install vulnerability audit.

The temporary probe declared UV_HTTP_RETRIES=2, which the unchanged CI catalog correctly rejected as inconsistent with this job's retry policy. Remove the entire diagnostic step and its temporary step ID with the lock update; do not change retry policy or suppress the catalog check.
