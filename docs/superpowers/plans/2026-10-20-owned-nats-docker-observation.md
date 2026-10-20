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

## Request/decode GREEN and collector composition tests first

On 4f64cdad, all fifty-two request/decode cases pass in job 118435856906; its aggregate is 837 PASS / one existing disabled-outage hold. This remains request/supplied-data validation, not an actual observed daemon or complete inventory.

The next observe_daemon_metadata seam is unavailable and returns NOT_READY. Twenty-one additive cases in the already-selected transport suite require one exact request and identical Deadline, no collection for rejected pins/deadlines, decode refusal after one collection, postcollection expiry, original exception identity, retained precollection fingerprint despite callback mutation, and no fresh deadline/retry. Fourteen positive integration oracles are expected to fail initially; seven admission controls should pass. No execution is claimed before hosted observation.

Tests replace only the existing collector boundary and retain direct process guards. The future implementation must capture the admitted expected fingerprint before calling the collector and decode against that retained value. Callback mutation intentionally bypasses frozen-dataclass protection; the proof is expectation retention, not continuing authenticity of a mutated object. No collector import, runtime caller, inventory, coordinator/CLI wiring or outage enablement is introduced by this scaffold.

## Collector composition after observed RED

On 2c85f95 / job 118442456006, fourteen composition cases fail at required one-call or exception-propagation assertions and all seven admission controls pass. The entire focused job is 847 PASS / 15 FAIL, including the existing disabled-outage hold.

The implementation uses existing preparation, refuses without collection when it returns None, retains the admitted fingerprint before the callback, invokes the existing private collector exactly once with the same Deadline, and decodes against that retained fingerprint. Unexpected exceptions and interrupts propagate unchanged. No fresh budget, retry, direct subprocess call or suppression is added.

Preparation/decoding still perform no transport I/O. Composition can invoke the existing collector when explicitly called; current tests replace that boundary and no coordinator/CLI/runtime caller is connected. Module documentation reflects this distinction. Own composition GREEN remains pending; complete inventory, executable/config/socket provenance, daemon authenticity, health admission and outage remain unproved.

## Collector composition GREEN

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 and hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b share tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Job 118448423252 passes all twenty-one observation-composition cases at 04:12:46–51 UTC, with aggregate 861 PASS / one existing disabled-outage hold in 246.72 seconds. Exact request/deadline identity, one collection, refusal before collection, result rejection, postcollection expiry, exception/interrupt identity and retained precollection fingerprint are covered.

The tests substitute the existing collector boundary. No runtime caller, coordinator, CLI, complete inventory or actual outage is enabled. Next work is explicit in-place Core Compose request preparation and private supplied-JSON projection under the original deadline, before any inventory or transport composition is accepted. Caller-owned signature/key/lease/source and Docker/plugin/config provenance remain preconditions, not facts established by this helper.
