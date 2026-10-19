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
- Acceptance requires privately verified effective worker max_retries=5, batch_size>=2, and a finite poll interval from 1 through 10 seconds. Refuse unsuitable settings; never modify them. The used full/live Compose files do not pin1s/50: code defaults are5s/20/5 and generated worker environment may override them. Restore on the first retryable observation with error_count1..4; no fixed outage duration or extra wait after that observation.
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

Files: scripts/owned_nats_coordinator.py; tests/test_owned_nats_outage_coordinator.py; tests/helpers/owned_nats_coordinator.py; existing pure contracts in scripts/owned_nats_outage.py.

- [x] First finish the pure inventory validator RED/GREEN cycle. Admission accepts only the caller's already verified signed selection, not a self-authenticated arbitrary inventory.
- [x] Define immutable actual evidence records and a narrow operation protocol with NOT_READY runner/wait seams. The adapter must not replace raw evidence with admitted/drained/valid booleans.
- [x] Observe hosted assertion RED for all101 coordinator/wait cases before implementation:8481 job118162897442,102FAIL335PASS107.40s including the absent workflow step.
- [ ] Cover valid exact success, bad ownership/inventory/participants, zero/nonzero pending count, empty/duplicate/mismatched event correlation, retry0/1..4/terminal/DLQ/prematureprocessed states, and exact retained event IDs.
- [ ] Cover failed/partial/timed-out stop, no send afterward, primary budget exhaustion, independent restoration, health failure, owner drift, changed target and every non-target runtime field.
- [ ] Cover exact broker envelope/subject/room/type/message/chat matching and missing-message-only polling; reject missing-stream/auth/transport/parse errors.
- [ ] Implement only after observed behavior RED; run hosted deterministic tests to GREEN. The command and workflow still do not invoke live transport.

## Task 3: Bounded owner-scoped transport

Files: scripts/live_nats_transport.py; scripts/live_stand.py; tests/test_live_nats_transport.py.

- [ ] Add actual testable adapter seam and tests before operation implementation. Prove every nested deadline and lock acquisition, including failure paths.
- [ ] Use owner-pinned read-only PostgreSQL principal verification, fixed SQL stdin, validated UUID parameters and transaction-local deadlines. Never use RLS bypass, SET ROLE or role modification.
- [ ] Privately verify the effective outbox worker command/settings under the owned full/live Compose model: max_retries=5, batch_size>=2, finite 1<=poll<=10 seconds. Base docker-compose.yml overrides are not evidence for this stand. Refuse an unsupported effective policy without configuration changes.
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

Inventory scoped GREEN: bcaae3 job118069006472 has52 inventory tests passing; overall early gate1FAIL99PASS26.65s because the live NATS step is still intentionally absent. Next: Message/StoredEvent pure-correlation NOT_READY seam plus33 assertion tests; no implementation or runtime enablement before their observed RED.

Exact correlation RED: ebc9 job118074359416 produced33 correlation assertion failures plus the absent workflow step,99passes in36.30s. Correlation implementation and seven supplemental malformed-input cases now await GREEN. Next NOT_READY seam tests post-restoration evidence invariants using the shared unchanged Core fixture; no actual restoration/coordinator/transport is implemented. Stored event identity always means stored_events.id, not the domain ID in metadata.

Restoration evidence RED: 2a2 job 118084880278 produced 32 invariant failures plus one workflow failure; 139 tests passed in 42.32s, including all 40 correlation and 52 inventory cases. The pure restoration validator is implemented pending GREEN. Next NOT_READY seams and tests cover effective worker policy and exact retry/drain states; no operational restoration, transport or outage is enabled.

Worker-policy/state RED: fb822 job 118093454598 produced 61 NOT_READY assertion failures plus the absent workflow step; 171 tests passed in 60.06s. All 32 restoration tests are now scoped GREEN. Policy and exact row classifiers are implemented pending own-source GREEN. The next 39 broker-contract assertions retain NOT_READY seams until observed RED. CLI execution, coordinator, bounded transport and live outage step remain unavailable.

Broker RED: de592 job 118102431402 produced 39 NOT_READY broker assertion failures plus the absent workflow step; 232 tests passed in 72.31s, including all 61 policy/state cases. The pure broker validator is implemented pending its own GREEN. Next are 27 deterministic absolute-deadline cases with NOT_READY seams, including shared clock-regression guards and independent restoration reserve. No lock, subprocess, HTTP, SQL, NATS connection or actual outage is enabled by this slice.

Deadline RED: 9c3 job 118109224196 produced 27 deadline assertion failures plus the absent workflow step; 271 tests passed in 72.90s, including all 39 broker cases. Minimal absolute-deadline implementation now awaits its own GREEN. It supplies only validated budgets; coordinator and adapters must separately prove bounded nested operations, no send after uncertain stop, independent safe restoration, and client/lock cleanup. No runtime command or workflow outage step is enabled.

Deadline scoped GREEN: 7195378 job 118116223502 has all27 deadline cases passing, with298 total PASS and only the intentionally absent workflow step failing in72.36s. The new coordinator boundary/test proposal will live in scripts/owned_nats_coordinator.py and tests/test_owned_nats_outage_coordinator.py, importing the existing pure contracts without runtime imports of app/live_stand. It remains under review, not published or executable. Restoration will use only the captured container ID under the pinned daemon; each Compose read retains explicit owner project/overlay. Independent client-close and lock-release cleanup budgets must not extend acceptance or consume each other's opportunity.

Coordinator scaffold is now source-defined but unavailable. Its adapter boundary requires exact captured container-ID stop/start under the pinned daemon; owner/resource drift fails acceptance, while restoration of a still-verifiable original target remains mandatory. The inner finally restores before drain/receipt; the outer finally closes clients and releases the lock with separate fresh10second reserves. All ordinary operations remain capped at10seconds, stop at15seconds, within their phase budgets. The in-memory fake checks these operation contracts outside runner exception handling. The CLI and live workflow remain disabled until deterministic behavior and bounded transport are verified.

Coordinator hosted execution is still pending: f917 fast job118135431503 failed only on Ruff S108 fixture literals and two formatting layouts before backend tests could run. Synthetic evidence-only state paths and exact formatter corrections preserve the 94 test oracles. NOT_READY seams remain unchanged until actual assertion RED; no runtime enablement or lint exceptions. The same existing early workflow line adds ten historical regression cases, with no removed targets or added lines.

Coordinator RED observed on 5c71: job118145641655 reports 94 NOT_READY assertion failures plus the absent workflow step, with333 PASS in131.75s. The reviewed implementation draft is not published. Review adds seven tests-first cases before implementation: stop pre-invocation expiry must not start an untouched target; a late acquired lease must be released; final owner/resource/non-target/NATS-health/target-identity drift after broker receipt fails acceptance. These seven new cases still await observed RED. The existing94 assertions remain unchanged.

Ruling: final signed-owner and complete-inventory verification belongs after broker receipt under the original primary deadline, not only before drain. Restoration is required only once stop invocation could have side effects; it must still be limited to the verifiable original target under the pinned daemon. This clarifies the accepted safety boundary without adding runtime authority. If wrong, the cost would be unsafe targeting or accepting a drifted stand; the new tests guard both boundaries. No bounded adapter or operational outage is enabled.

Coordinator implementation published only after the supplemental RED above. Review corrections are covered: stop invocation flag follows a valid child deadline; late returned lease remains available to cleanup; full owner/runtime validation runs again after broker receipt under the primary deadline. Independent recovery and close/release budgets remain separate. Hosted GREEN is pending; no transport or operational enablement.
