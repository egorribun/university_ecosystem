# Public source licensing transition

Date: 2026-11-06. The owner approved public inspection with written permission
required for additional use of future original material. Retain the public
designation `egorribun`; publish no additional personal details or contact.

Preserve earlier licenses, third-party notices, GitHub rights, and mandatory
legal exceptions. Permit ordinary use of owner-operated websites, including
necessary browser execution and caching, without granting self-hosting rights.
Accept external code/assets only after a separate executed contribution rights
agreement. Add no separate AI/branding restrictions and claim no rights in
unverified university material.

Record pre-transition snapshots and retain the old root MIT notice verbatim.
Update root notices, both READMEs, contribution guidance, documentation index,
and runtime package metadata. Keep separately licensed developer adapters and
upstream notices. Bundle the terms and retained MIT notice with WASM packages.
Use exact per-crate/version Cargo Deny mappings for the new first-party license;
leave dependency allowlists, security policy, and required checks unchanged.

Implement in an isolated `codex/` branch from `egorribun`, rebuild and verify
WASM metadata/provenance, validate TOML/JSON and notice preservation, run
appropriate existing tests and hooks, then submit separate license-only PRs to
`egorribun` and `main`. Their histories diverge substantially; do not include
unrelated development commits in the default-branch licensing change.
Source-bound hosted checks remain required; no merge or bypass is authorized.
