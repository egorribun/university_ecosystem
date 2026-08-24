# ADR-017: Domain-Oriented Test File Naming

## Status

Superseded and completed (2026-08-17)

## Context

Early audit work grouped some backend tests by the implementation batch in
which they were added. That temporary convention made ownership and discovery
harder because a filename described chronology rather than the behavior under
test.

## Decision

Tests are named and grouped by the production domain or contract they verify:
`test_<domain>.py`, `test_<component>_<behavior>.py`, or an existing colocated
test module. Chronological labels and generic coverage-boost labels are not
accepted for new test files.

The migration is complete: the remaining chronological filenames were renamed
to domain-specific names, and active configuration, ownership metadata, and
documentation now reference those names.

## Rationale

- Domain names make relevant tests discoverable from the production code.
- Stable names survive release planning and audit-cycle changes.
- Clear ownership reduces duplicate tests and maintenance fragmentation.
- Coverage is a verification property, not a domain for organizing behavior.

## Consequences

- Historical audit records may retain chronological terminology as immutable
  provenance, but active test paths must remain domain-oriented.
- Tests that span several components use the narrowest stable contract name.
- Repository quality checks reject regressions to chronological test naming.
