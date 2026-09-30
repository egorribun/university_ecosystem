# Audit trail

This directory indexes the active MVP closure work and its audit inputs. Audit
reports describe the repository at their recorded commit; they are historical
evidence, not current configuration or release certification.

## Current quality-closure roadmap

- [Active MVP closure status](../superpowers/plans/STATUS.md) — the current
  operational status. It is a plan, not an audit certificate; every release
  claim still requires fresh exact-SHA evidence.
- [Platform audit ledger](AUDIT_PLATFORM_FULL.md) — working classification of
  63 external-audit findings. Revalidate its evidence against the release SHA;
  the ledger is not a release certificate and is removed only after its useful
  rationale and findings have been transferred and reviewed.

## Legacy archive cleanup and recovery

The former directories `archive/` and `../superpowers/plans/archive/` contained
112 audit reports and 8 plan snapshots. Applicable requirements were reconciled
against the master plan, ADRs, tests, and current workflow contracts; the two
directories were removed in separate commits after inventory, credential
disposition, and recovery verification. The repository history remains the
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
The user also confirmed that the seeded-admin password was used only in an
ephemeral CI database. Keep the rescue bundle private and do not redistribute it.
Remove archive files only after final review of the transferred requirements,
credential disposition, inventory, and links.
To recover files without rewriting history, resolve the sibling bundle and
clone it to a temporary directory, for example:

```powershell
$bundle = Join-Path (Split-Path -Parent (Get-Location).Path) 'university_ecosystem-rescue-2026-09-30-d0aad7c.bundle'
$rescue = Join-Path $env:TEMP 'university-ecosystem-rescue'
git bundle verify $bundle
git clone --no-checkout $bundle $rescue
git -C $rescue checkout d0aad7c296facd79b3d41b037bc4160f5b3132be -- docs/audits/archive docs/superpowers/plans/archive
```

After archive removal, both the default and `--include-archives` link checks pass
for all 436 remaining Markdown files with no historical-link allowlist. Keep
`--include-archives` as a diagnostic mode for verifying restored snapshots; do
not invent replacement links for files that are not present.

## Current working references

- [MVP master plan](../superpowers/plans/MVP_MASTER_PLAN.md) — approved scope,
  decisions, sequence, and acceptance criteria.
- [Active closure status](../superpowers/plans/STATUS.md) — current state and
  next actions.
- [Machine-enforced quality contract](../../quality/quality-contract.json) —
  mandatory quality gates.

Other audit reports describe particular historical snapshots. Do not treat a
report as current merely because its file remains in this directory.

## Supplemental historical evidence

- [CI capacity and mutation bottleneck audit](CI_CAPACITY_AUDIT_2026-09-08.md)
  — historical queue/capacity observations and the evidence required before a
  future concurrency change. This is diagnostic evidence only, not a current
  quality certificate or a reason to relax any gate.
- [Migration and dead-letter UUID audit](AUDIT_MIGRATION_148642_UUID_2026-09-08.md)
  — bounded historical schema-contract audit.
- [Backend defaults and CDC worker audit](AUDIT_BE_DEFAULTS_CDC_2026-09-08.md)
  — bounded historical backend audit.
- [uv `exclude-newer` audit](AUDIT_UV_EXCLUDE_NEWER_2026-09-08.md)
  — bounded toolchain-configuration audit.

Supplemental reports preserve reproducible historical context. They do not
supersede the current quality contract, a fresh same-SHA CI result, or a
certified release snapshot.

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
