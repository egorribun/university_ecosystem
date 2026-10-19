# Owned NATS acceptance implementation plan

> **For agentic workers:** Use the accepted spec and this plan task by task. Root owns GitHub publication and evidence review. No runtime enablement from capability tests alone.

**Goal:** Prove one exact message/outbox event survives a bounded NATS-only outage in the existing owned PR Core stand and reaches existing broker storage after restoration.
**Architecture:** A pure typed coordinator validates evidence from a bounded transport adapter. The existing launcher exposes a thin owner-scoped command; the live workflow enables it only after deterministic safety verification.
**Tech stack:** Existing Python standard library, locked nats-py inside the backend container, existing Docker/Compose/psql, hosted GitHub Actions.
**Spec:** [Owned NATS send-message acceptance](../specs/2026-10-18-owned-nats-outbox-acceptance.md).

## Invariants

- GitHub plugin only, branch egorribun, existing PR1306. No main/merge/deployment or security gate/baseline changes.
- Existing signed Core stand, daemon/resource fingerprints and exact container IDs; no new services, credentials, accounts, ports, seed containers or probe endpoints.
- Existing administrator and exact reserved peer; read the generated admin credential, never create/rotate it. Refuse a pre-existing administrator/peer DM.
- Normal cookie/CSRF login and multipart send, exactly one write attempt; no retry after ambiguous send.
- Exact Message and chat/sender/content identity; exactly one chat.message_sent StoredEvent, aggregate_type Message and schema1, retained event ID for every later query.
- Existing finite five-attempt outbox policy. Restore on the first retryable observation with error_count1..4; no fixed outage duration or extra wait after that observation.
- Existing identity-only quiesce comparator stays unchanged. New snapshots additionally compare non-NATS runtime, restart count, exit code and OOM state.
- Closed public stage/outcome labels only; never include raw exceptions, identities, SQL rows, credentials, cookies or message bodies.
- Broker-storage receipt only, no exactly-once or recipient/browser ACK claim.

## Budget and recovery contract

All deadlines are absolute monotonic values, converted to remaining time at each operation. Every nested lock/subprocess/daemon/config/list/inspect operation on the new path must be bounded. Reusing an existing unbounded helper unchanged is forbidden; pure parsers may be reused.

Lock acquisition10s; primary phase180s; inventory phase45s; ordinary subprocess10s; stop explicitly15s; HTTP request10s; psql outer10s with transaction statement5s/lock1s; first retry observation30s; independent restoration120s; drain60s; broker receipt45s; workflow outer10minutes. Clamp every per-call timeout to the remaining phase time. The backend probe has its own asyncio connect/read/close deadline; a local Docker timeout does not prove remote execution stopped.

Capture the original verified daemon/container identity before stop. Mark restoration required before attempting stop. A failed/uncertain stop never permits send. Always attempt safe restoration with a fresh independent reserve, including when the primary deadline expired. Never start an unverified or replacement target after drift. If the original target can still be verified, restore that exact target but fail acceptance on owner/resource drift. If it cannot be verified, report restoration unverified and fail; do not widen authority. Require same-container healthy state after restoration even if the primary operation failed.

## Task 1: Capability and unavailable scaffold

Files: tests/test_live_stand.py; tests/test_live_acceptance_workflow.py; scripts/live_stand.py; scripts/owned_nats_outage.py.

- [x] Publish tests for nats-outage help/owned-state flags and exact one bounded/gated workflow step with metadata-only outcome.
- [x] Observe hosted capability RED: db4 job118049340089,2FAIL45PASS18.01s; exit2vs0 and missingstep0vs1. This is not behavioral outage proof.
- [x] Add CLI help and an explicit unavailable result before state-mode configuration or any I/O. The workflow step remains absent.
- [x] First add a small pure inventory admission seam returning a closed not_ready verdict without I/O. Its immutable record extends the existing canonical identity digest with restart/exit/OOM fields. No coordinator or transport implementation is hidden in the scaffold.
- [x] Add deterministic inventory tests against that real seam: complete unique signed selection, canonical IDs/digests, healthy critical services, valid running services and completed initializers. Verify assertion RED, not missing imports or setup errors. Implement this pure validator only after that RED; add runtime invariance/correlation/deadline coordinator slices incrementally rather than a monolithic runner.

## Task 2: Evidence-validating coordinator

Files: scripts/owned_nats_outage.py; tests/test_owned_nats_outage.py.

- [ ] First finish the pure inventory validator RED/GREEN cycle. Admission accepts only the caller's already verified signed selection, not a self-authenticated arbitrary inventory.
- [ ] Define immutable actual evidence records and a narrow operation protocol. The adapter must not replace raw evidence with admitted/drained/valid booleans.
- [ ] Cover valid exact success, bad ownership/inventory/participants, zero/nonzero pending count, empty/duplicate/mismatched event correlation, retry0/1..4/terminal/DLQ/prematureprocessed states, and exact retained event IDs.
- [ ] Cover failed/partial/timed-out stop, no send afterward, primary budget exhaustion, independent restoration, health failure, owner drift, changed target and every non-target runtime field.
- [ ] Cover exact broker envelope/subject/room/type/message/chat matching and missing-message-only polling; reject missing-stream/auth/transport/parse errors.
- [ ] Implement only after observed behavior RED; run hosted deterministic tests to GREEN. The command and workflow still do not invoke live transport.

## Task 3: Bounded owner-scoped transport

Files: scripts/live_nats_transport.py; scripts/live_stand.py; tests/test_live_nats_transport.py.

- [ ] Add actual testable adapter seam and tests before operation implementation. Prove every nested deadline and lock acquisition, including failure paths.
- [ ] Use owner-pinned read-only PostgreSQL principal verification, fixed SQL stdin, validated UUID parameters and transaction-local deadlines. Never use RLS bypass, SET ROLE or role modification.
- [ ] Verify active administrator/reserved peer and absent pair, use cookie jar and CSRF login, create exact DM once, verify participants, then count-only zero-pending check immediately before stop.
- [ ] Capture exact container inventory with explicit project/daemon identity; stop/start only the originally verified NATS target. Preserve old lifecycle APIs/defaults for unrelated callers.
- [ ] Use a static bounded backend Python stdin broker probe with get_last_msg(direct=False); no stream/consumer mutation or production connect helper.
- [ ] Poll only exact404/10037; fail404/10059 and unknown404. Close HTTP/NATS clients under bounded cleanup.
- [ ] Independently review adapter/probe SQL, state ownership, output redaction and fail-closed behavior before enabling the command.

## Task 4: Guarded runtime acceptance

Files: .github/workflows/live-acceptance.yml; existing metadata-only Core receipt.

- [ ] Make the existing workflow capability test GREEN only after coordinator and transport safety tests pass.
- [ ] Gate exact PR head repository egorribun/university_ecosystem and head.ref egorribun after core-e2e success. No main/nightly/frozen-RC widening.
- [ ] Use same owned state, one step,10minute outer timeout, unchanged always-run cleanup and receipt schema; add closed NATS_OUTAGE_OUTCOME/nats_outage field.
- [ ] Run the approved scenario on hosted PR Core; require exact retryable event, safe restore/health, same-event drain/noDLQ and exact broker receipt.
- [ ] Verify receipt/cleanup source-tree provenance and all full CI gates before acceptance. Failed or unexecuted stages remain explicit.

## Review focus

- Actor is the existing administrator, not the primary seeded student; those are different DM pairs.
- Owner metadata drift must neither target a replacement nor silently suppress a safe original-target restoration.
- Stop15s explicitly overrides the generic subprocess10s cap while still respecting its phase deadline.
- Raw probe success is not acceptance: the coordinator validates exact message, event and broker evidence.
- Capability help/step tests are not outage behavior; the unavailable scaffold must remain non-operational until later safety gates pass.

Current source evidence:7a7 job118062740060 produced52 inventory assertion failures and one workflow capability failure, with47 passes in25.63s. CLI help/refusal passed. Pure-validator implementation is awaiting its own hosted GREEN; coordinator, transport and runtime enablement remain incomplete.
