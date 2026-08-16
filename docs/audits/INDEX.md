# Audit trail

This directory is the canonical audit-history surface for University
Ecosystem. Audit reports describe the repository at the recorded commit and
must not be treated as current configuration or current quality evidence.

## Current reference set

- [Wave 211](AUDIT_WAVE211.md) — forwarding and group-chat completion
- [Wave 210](AUDIT_WAVE210.md) — group-message backend foundation
- [Wave 209](AUDIT_WAVE209.md) — group-chat foundation

The active reference set is deliberately limited to the three most recent
reports. New audit reports must move the oldest active report into `archive/`
in the same change.

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
