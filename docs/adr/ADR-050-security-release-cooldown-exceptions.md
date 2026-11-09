# ADR-050: Exact security-release cooldown exceptions

- Status: accepted for the two 2026-10-31 updates and the exact Undici 8.12.4 exception below; amended 2026-11-06. Implementation validation pending.
- Date: 2026-10-31.
- Decision owner: repository owner.
- Scope: egorribun/university_ecosystem, branch egorribun; no merge or deployment authorization.

## Context

The owner separately approved the security updates below, then explicitly
approved one-time exceptions to the seven-day release-maturity window at
2026-10-31 06:32 UTC. The go-jose release is younger than seven days; the exact
npm publication age has not been established by the bounded metadata receipt.
Neither uncertainty is represented as a mature-release proof.

| Package | Exact update | Scope |
| --- | --- | --- |
| follow-redirects | 1.16.1 to 1.16.2 | One existing frontend lock record; Axios 1.20.0 and every other dependency stay unchanged. |
| github.com/go-jose/go-jose/v4 | 4.1.6 to 4.1.7 | Five existing Go module graphs/sums, the existing grpc-health-probe override and two version-pin contracts; exactly the separately approved 13-file update. |

The [follow-redirects advisory](https://github.com/advisories/GHSA-mrwp-f3q8-3g9p)
identifies the fixed release. No credential leak in the current Axios consumer
has been reproduced. The [go-jose/v4 release](https://github.com/go-jose/go-jose/releases/tag/v4.1.7)
includes security fixes and compatibility changes, including limits of 32
signatures/recipients and stricter malformed-key handling. The separate
go-jose/v3 advisory is not fixed by this decision.

## Owner-approved Undici exception (exact one-time scope)

The npm registry published `undici` 8.12.4 at 2026-11-05T08:55:59.361Z. Its normal seven-day maturity point is 2026-11-12T08:55:59.361Z. The current frontend lockfile entry is 8.12.2. The [GHSA-mqg3-3v4r-cm32 advisory](https://github.com/nodejs/undici/security/advisories/GHSA-mqg3-3v4r-cm32) identifies a high-severity redirect-cache issue affecting 8.12.2 and 8.12.3; the [GHSA-r4pc-4jcp-7pqc advisory](https://github.com/nodejs/undici/security/advisories/GHSA-r4pc-4jcp-7pqc) identifies an SRI whitespace bypass fixed by 8.12.4.

The owner-approved one-time exception is limited to changing the single `packages.node_modules/undici` record in `frontend/package-lock.json` from 8.12.2 to 8.12.4, updating only that record's version, resolved URL and integrity. `frontend/package.json`, every other lock record, and the `seroval` 1.6.12 lock/override remain unchanged. This lock record is marked development-only; this approval would make no claim about production runtime use.

The approved exception is usable only for this exact lockfile update and only before 2026-11-12T08:55:59.361Z. After that timestamp, the normal seven-day rule is satisfied and no exception is needed. Keep `frontend/.npmrc`, including `min-release-age=7`, and Renovate's routine seven-day minimum release age unchanged. The registry tarball's recorded SRI and SHA-1 were verified against the downloaded package bytes. A bounded loopback SRI negative-control probe corroborated the whitespace fix; that diagnostic is not install, maturity, full-suite or hosted-check evidence.

This ADR records only the cooldown exception; the separately approved Semgrep row #15 companion rebind and exact `public_integrity_digest` disposition are recorded in ADR-047 and the owner packet. Their exact scopes remain separate and are integrated with this lock change only as authorized. No baseline entry is requested.

## Decision and limits

The two accepted maturity exceptions above remain finite and exact. The Undici exception is approved only for the one exact lockfile update described above and is consumed by that update. None of these decisions removes the global cooldown or permits other versions, packages, prereleases, overrides or future updates. Preserve frontend/.npmrc, all routine minimumReleaseAge policies, engine/script restrictions, lock integrity, scanner gates and existing quality thresholds.

Before integration, verify authoritative source metadata and hashes, prove the
whole graph delta is confined to the approved package, review compatibility
controls and obtain the new source's own install/audit/scan/test receipts.
The follow-redirects registry metadata was captured by
[own-source Node audit job 124464781669](https://github.com/egorribun/university_ecosystem/actions/runs/41176285302/job/124464781669);
that job's advisory failure concerns the still-old lock and is not proof of
the proposed lock's installation or scan result.
Go sums require an isolated authenticated Go checksum-database verification;
a bare HTTPS lookup or an ordinary download trusting pre-existing go.sum is
not sufficient.

Temporary metadata capture is diagnostic, never a scanner waiver. Remove each
capture and its temporary expectations when its verified dependency update
is committed. Do not print raw environments, credentials or unbounded
download diagnostics. These approvals do not authorize new secret/hash
dispositions, baseline entries, Gitleaks changes, Squawk admission, production
database maintenance or bypass of a system safety restriction. The exact Undici exception likewise authorizes none of those actions.
