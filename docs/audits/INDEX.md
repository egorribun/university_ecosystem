# Audit trail

This directory is the canonical audit-history surface for University
Ecosystem. Audit reports describe the repository at the recorded commit and
must not be treated as current configuration or current quality evidence.

## Current quality-closure roadmap

- [MVP quality-closure continuation plan](../superpowers/plans/2026-08-31-mvp-quality-closure-continuation.md)
  — the current operational roadmap and evidence-boundary record. It is a
  plan, not an audit certificate; its historical checkpoints still require
  exact-SHA re-verification.

## Archive link audit (2026-09-15)

The deterministic checker can include archived reports with
`uv run python scripts/docs/check_markdown_links.py --include-archives`.
It found 123 historical link targets that were not valid from the archive
directory. 104 links whose intended repository-root targets still exist were
normalized in place; the report remains intentionally non-zero for these 12
historical-only references:

- `AUDIT_WAVE120.md:463` → `memory/wave121_backlog.md` (memory artifact no
  longer present)
- `AUDIT_WAVE140.md:382,581` → `docs/plans/2026-05-11-wave140-tier123-design.md`
  (superseded plan is not in the repository)
- `AUDIT_WAVE143.md:38,124,317` → old test/visual-audit files no longer present
- `AUDIT_WAVE145.md:15,260` → old visual-audit/design files no longer present
- `AUDIT_WAVE163.md:28` → a machine-local `.claude` memory path
- `AUDIT_WAVE192.md:272-274` → `.claude profile` placeholders

These entries are retained as historical text and are not release or current
documentation references. They must not be converted into guessed links or
removed without a separate archival-retention decision.

## Current reference set

- [PR #1249 Audit](AUDIT_PR1249.md) — multi-stack quality & architectural release certification
- [Wave 211](AUDIT_WAVE211.md) — forwarding and group-chat completion
- [Wave 210](AUDIT_WAVE210.md) — group-message backend foundation

The active reference set is deliberately limited to the three most recent
reports. New audit reports must move the oldest active report into `archive/`
in the same change.

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

Completed reports are retained in [`archive/`](archive/) as immutable evidence.
Their filenames, commits, dates, and detailed findings remain available in Git;
duplicating their full narratives in this index created a stale 200+ KB second
source of truth and is intentionally avoided.

## Maintenance rules

- Record durable architecture choices as ADRs under [`../adr/`](../adr/).
- Record current quality policy in [`../../quality/`](../../quality/) and the
  [testing guide](../../TESTING.md), not in historical audits.
- Do not append prompts, session transcripts, temporary plans, or live status
  notes to audit reports.
- Keep links relative and move-linked when rotating reports into `archive/`.
