# Bounded Docker observation prerequisites

## Scope

Runtime observation, coordinator/CLI wiring and outage remain disabled. Prepared requests and supplied bytes do not establish actual Docker execution, executable/config/socket provenance, trusted daemon identity, complete inventory, health, image trust or mount admission.

## No-I/O Compose projection extraction

Extract the existing parsed-project body into _compose_resource_evidence_from_project; the legacy wrapper retains project validation, current process invocation/environment, JSON decoding and exact error behavior. The extraction adds no subprocess call or waiver. The existing projection body stays byte-for-byte unchanged.

Twenty-one additive tests compare the wrapper and extracted helper against independent canonical/evidence expectations: full/Core/legacy resource retention, dependency closure, port names rather than numeric values, Unicode mount changes, malformed models, selection errors and pre-projection wrapper failures. The only fake process accepts one exact command and kwargs, without a real-process fallback. Fixed synthetic models are checked for nonmutation; this is not a general purity promise. Existing resolution can append link/network-mode dependencies to a list-valued depends_on, which remains unchanged for compatibility.

These six test functions are explicitly selected on the existing focused workflow command line. Hosted execution remains pending.

## Explicit daemon request and supplied-result tests first

New owned_nats_docker contains unavailable no-I/O preparation/decode seams. DockerReadPins requires explicit executable, local endpoint, config directory, working directory, immutable environment pairs and expected daemon fingerprint. Private fields are excluded from repr. The scaffold returns None/NOT_READY and never invokes the collector.

Fifty-two additive cases live in the already-selected transport test file. Six positive cases are expected to expose unavailable preparation or decoding: two exact requests, three daemon line endings and the shared-deadline preparation control. Negative cases cover representative unsupported pins/environments, process outcomes, return codes, cleanup uncertainty, private stderr, malformed/oversized output, fingerprint mismatch and unusable/finally-expired deadlines. Guards record attempted process execution; they cover specified entry points, not every possible I/O mechanism. No expected RED is claimed until hosted observation.

After RED, preparation must use only a fixed read-only info argv, explicit empty/locale-only environment, bounded output and the supplied Deadline. Decoding accepts only confirmed EXITED/exact-zero results with bounded bytes and empty stderr, strips at most one accepted line ending, hashes the opaque daemon ID and compares the supplied expected fingerprint. It must recheck the same deadline, never learn its expected pin from the same response. No RuntimeEvidence or ContainerSnapshot is produced by this slice.

## Existing preflight deadline proof

Original AUD-084 concerns bounded return when an exited parent leaves inherited stdout open. Current source and both existing test blobs match e150, but inspected aggregate logs do not expose named execution. Select both existing suites in the same verbose focused command. Real Linux inherited-pipe evidence is the acceptance target; Windows API simulations are not physical Windows execution, and bounded return does not mean every detached descendant is terminated.

Only existing workflow line 155 is extended. The 631 split-line layout and baseline coordinates 396/406 remain byte-identical; baseline 319, dispositions 263, required contexts and security gates are unchanged.

## Named projection and preflight evidence

Source a71c6d7c756c53bd31ea661053a9974ee9fdc497 is bound to checkout fbb400bb797ed0fd683515f19da1d9275c483953 and identical tree e164ddb9bbe0550e010832adead33404763a552d. Focused job 118415057333 reports 831 PASS / 7 FAIL in 212.74 seconds: six intended unavailable daemon request/decode assertions and the existing disabled-outage workflow hold. All twenty-one Compose projection cases and all twenty-eight existing preflight cases pass.

AUD-084 is accepted narrowly for bounded runner return when an exited parent leaves inherited output pipes open. The real Linux regression test_run_check_deadline_when_descendant_inherits_output_pipes passes at 02:16:19 UTC. Source was already corrected and is unchanged; adding named selection supplies the missing source-bound proof. Windows drain cases are simulated API controls, not physical Windows execution. Bounded return does not claim termination of every detached descendant.

## Observed daemon RED and bounded implementation

The six positive assertions fail on a71c6d7 because preparation returns None and decoding returns NOT_READY. The other forty-six new cases pass. The corrected source now validates explicit lexical paths, local Unix endpoint and immutable locale-only environment before creating one fixed bounded request. Supplied process results require exact enum identity, integer zero, confirmed cleanup, bounded bytes, empty stderr, strict UTF-8 and a matching pinned fingerprint. Both operations recheck the original Deadline and perform no process or filesystem invocation.

Paths and endpoint checks are deliberately restricted capabilities, not existence/provenance checks. Root is supported for directory pins only; ambiguous endpoint query, fragment, percent encoding and backslashes are rejected. Ordinary malformed-data/deadline failures remain private; BaseException is not newly swallowed. Extra defensive shape/Unicode/path branches exceed the representative fifty-two-case cohort and are not claimed as exhaustively tested.

Own corrected-source GREEN is pending. No collector invocation, RuntimeEvidence, container inventory, coordinator/CLI wiring or outage is enabled.
