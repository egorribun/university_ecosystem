# Pure signed Core metadata parser

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

## Why this slice

The existing live owner loader reads files through mutable global paths and accepts historical schemas. It must not be reused unchanged on the deadline-bounded outage path. First extract a small pure boundary for complete schema-11 Core marker bytes; descriptor-safe file/key reading, lifecycle locking and Docker observation remain separate later work.

## Contract

parse_signed_owner_v11 accepts bounded marker bytes, supplied 32-byte key material and explicit pinned repository/state/source strings. SIGNED_METADATA means only that supplied complete metadata matches the supplied trusted key and pins. It does not prove where those bytes came from, safe file ownership, path race resistance, current Docker daemon identity or runtime admission.

Use the existing canonical HMAC signer, project/port validators and reviewed Core roots/service set. Require the exact v11 key set, bound nonnull daemon/resource fingerprints, no resume state, exact source pin, strict types and signature equality. Reject malformed encoding, duplicate keys and over-cap input before claiming parsed metadata. Return only closed NOT_READY or repr-private metadata. Do not create or rotate keys.

## Tests-first sequence

- [x] Review the actual current writer, canonical signer and complete Core marker shape.
- [x] Add a typed NOT_READY seam with no I/O or operational wiring.
- [x] Add 36 deterministic cases, including two current-writer-compatible ASCII/Unicode positive cases, re-signed semantic invalids, wrong key/signature, malformed caller pins, duplicate JSON and size/type/encoding failures.
- [x] Observe both positive metadata assertions RED on source 834984b, job 118282261816, test line 128; setup passes.
- [x] Implement only the pure parser after RED; all original 36 cases and code gates pass on 2caf407.
- [ ] Add descriptor-safe existing-file reading and bounded lifecycle lock handling as separately tested slices.

Test fixtures use the existing legacy canonical signer independently of the parser. They forbid the listed legacy I/O helpers and guard common direct file/process APIs only during the parser call, restoring them before pytest reporting. Source review is also required: these guards are not an operating-system sandbox or proof against every possible API. No filesystem/provenance or remote-exec test is claimed here.

## Deferred transport requirements

Current owner/key paths remain .secrets/live-stand.json and .secrets/live-stand-owner.key under the existing owned state root; the lifecycle lock is its existing sibling lock path. Future file reads must preserve the existing key, reject symlinks/special/oversized files, and use safe descriptor-relative access where supported. Regular local filesystem syscalls cannot be hard-preempted, so pre/post deadline checks and explicit limitations remain necessary.

The PostgreSQL spec uses the existing owner-pinned bootstrap principal, with read-only principal verification and read-only SQL transactions; it does not request a new read-only role. Do not change _actors, roles, credentials, app.bypass_rls or RLS settings. SQL statement/lock timeouts bound database work, not necessarily a remote psql process waiting for stdin. A fixed-argv remote watchdog is a future capability requirement against the exact pinned container; its presence is not proven by generic image ancestry. Local Docker-client reaping never proves remote completion.

This module remains disconnected from the coordinator, CLI and live workflow. The approved NATS outage is not enabled by metadata-parser tests.

## Minimal implementation after observed RED

The 36 tests are unchanged. The implementation rejects duplicate/nonfinite JSON, wrong exact schema/types/key size, incomplete Core metadata, mismatched pins and signatures, and returns repr-private signed metadata only. Legacy project/port validators and canonical signer are reused without invoking their I/O loaders. Parsing/validation failures return NOT_READY; assertions and unexpected I/O exceptions are not swallowed. Own-source GREEN is pending.

The parser call uses only supplied bytes/pins and pure legacy helpers. Importing existing live_stand still performs its ordinary REPO_ROOT = Path(__file__).resolve() initialization; tests guard parser invocation, not Python module loading. No claim of an I/O-free import or descriptor-safe owner-file reading.

## Original 36-case GREEN and additive boundaries

Job 118288482456 on exact 2caf407 tree reports all 36 parser cases PASS; total 545 PASS / 1 FAIL in 157.30s, with only the absent outage step failing. Both pre-commit gates, inventory and baseline integrity pass. Thirty additive cases retain the original 36 unchanged and cover nested duplicate ports, exact 65536-byte valid payload, nonfinite/deep JSON and wrong container/string-field/pin types. These new cases await execution; no implementation or runtime authority changes accompany them.
