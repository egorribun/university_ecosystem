# ADR-050: Two exact security-release cooldown exceptions

- Status: accepted for the two named updates only; implementation validation pending.
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

## Decision and limits

This is a finite manual maturity exception for these two exact release
identities, not a global cooldown removal or permission for other versions,
packages, prereleases, overrides or future updates. Each exception is consumed
by its named reviewed update. Preserve frontend/.npmrc, all routine
minimumReleaseAge policies, engine/script restrictions, lock integrity,
scanner gates and the existing quality thresholds.

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
download diagnostics. These two approvals do not authorize new secret/hash
dispositions, baseline entries, Gitleaks changes, Squawk admission, production
database maintenance or bypass of a system safety restriction.
