# ADR-054: Proprietary Public Source Terms for Future Original Material

Date: 2026-11-06

Status: Owner-approved direction; implementation and hosted validation await
integration through the required PR workflow.

## Context and decision

The owner chose public source inspection with written permission required for
additional use of future original material. Adopt [the root notice](../../LICENSE)
while preserving earlier licenses, platform rights, mandatory legal exceptions,
and third-party notices. Use the existing public designation `egorribun` without
additional personal details or contact. Permit ordinary use of owner-operated
websites. Require a separate executed contribution rights agreement before
accepting external code or assets. Add no separate AI or branding restrictions;
claim no rights in unverified university material.

## Exact first-party license recognition

Use `LicenseRef-University-Ecosystem-Proprietary` in production package metadata.
Each Rust crate (`rust_ext`, `wasm-sanitizer`, and `uni-wasm-crypto`, all at
`0.1.0`) has a local Cargo Deny exception limited to its exact name, version,
and license identifier. This represents the owner's first-party licensing
decision; it does not approve proprietary third-party dependencies. Shared
dependency allowlists, confidence thresholds, required checks, and security
finding policies are unchanged. No private-workspace ignore, global license
allow, or scanner bypass is introduced.

Retain separately licensed developer adapters and upstream attributions.
Record provenance in [the transition record](../licensing/README.md) and
[the bundled-material inventory](../../THIRD_PARTY_NOTICES.md).

## Consequences and validation

Existing code remains reusable under earlier terms. Metadata changes alone
do not restrict it. Ownership and legal enforceability are not certified here.
WASM notices, manifests, distributable metadata, and provenance must agree.
Validate first-party license recognition and preserve all dependency rules.
Ordinary hooks and source-bound hosted checks remain required; this ADR is
not evidence that they passed.
