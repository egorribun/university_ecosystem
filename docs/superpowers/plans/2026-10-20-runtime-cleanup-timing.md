# Runtime cleanup and CI timing reconciliation

## AUD-091 tests first

Seven appended cases exercise the actual sequential shutdown function with isolated finalizers and one real background task. DI-close, later asynchronous cache, and synchronous webpush failures must leave the original RuntimeError observable while every later independent finalizer is attempted exactly once in order. The success control preserves readiness, scheduler, CDC stop, background cancellation and existing cleanup order. The DI marker must be set before close and remain set after a failure.

The new test owns and cancels its background task even on assertion failure. All external finalizers are controlled; no real application clients are closed. Additional cases retain both original exceptions in a finite context chain for DI plus later cache failure. Standard cleanup-stack semantics are explicit: the last failure is primary; earlier exact objects remain in __context__. DI-finalizer-raised CancelledError is preserved alone or in that chain when a later finalizer also fails. These are not external cancellation shielding, repeated cancellation or bounded-shutdown guarantees. No source correction is included until the predicted short-circuit failures are observed. Before any correction, isolate newly reachable finalizers in the existing restart close-failure test while retaining its marker and recreation assertions.

## AUD-093 tests first

Six additive cases separate dependency execution duration from a one-hour scheduling gap between two independent ten-second jobs. The real strict DAG/provenance path establishes a ten-second critical path, while diagnostic mode must retain its unknown-dependency labels and 3610-second wall span but report only the ten-second defensible lower bound. The offline CLI must serialize the same distinction with a valid report digest. All-zero and late-zero controls preserve existing utilization behavior.

The current diagnostic report incorrectly reuses wall span for its lower bound. Two staggered cases are expected to fail; that is a prediction until hosted execution. Strict provenance, queue/rerun handling, CLI flags and report schema remain unchanged.

Although the analyzer suite is already listed in a later workflow step, the earlier intentional outage hold prevents that step from running. Add the two new analyzer test nodes to existing line 155, alongside the new lifespan cases, three existing shutdown-order controls and restart contracts. Keep the existing five-minute budget; do not duplicate the whole analyzer suite in this earlier command. Retain all existing selections and baseline line coordinates; no skip or waiver is added.

## AUD-094 proof selection

Existing reversible UTF-8 key escaping and decoded-name glob matching already correct colon-separated cache keys. Select the whole existing tests/test_nats_kv_cache.py instead of its four previously selected empty-bucket cases, preserving those controls and adding the existing round-trip/grammar regressions. No production rewrite is warranted before evidence. Grammar-enforcing in-memory KV is not a real broker, TTL, arbitrary empty-key or legacy escaped-name migration proof.

## AUD-095 accepted scope

At source 1ed440f88de239971ce9e4e6900a41ed6adad7c3, hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b has identical tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Go job 118448423362 succeeds under go test -v -race. TestStopGRPCServerForcesStopWhileHealthWatchStaysOpen and TestStopGRPCServerReturnsImmediatelyWhenCallsDrain explicitly pass at 04:08:59 UTC.

Production source 33ba89ba1aef611632798664e9d0d49a3898603f integrates stopGRPCServer into runServers. Test blob 25eafd1c4112ee07970af56e9d2c94d238800bdb opens a real loopback Health.Watch, receives SERVING, keeps the stream open during shutdown, and verifies helper return plus stream termination. This accepts the original standard Health.Watch hang, not a universal wall-clock bound or whole-process/SIGTERM/deployment proof. Production grace is ten seconds; the test uses fifty milliseconds and a five-second watchdog. No earlier RED is claimed.

The existing comment that shutdown always completes is overbroad: Stop and the final drained wait do not independently bound arbitrary cancellation-ignoring handlers. Follow-up test hygiene should register listener/server cleanup immediately and bound setup/receive waits without allowing a client deadline to manufacture the forced-stop oracle. Those failure-path improvements do not erase the observed successful real-transport evidence.

## AUD-092 tests first

Ten actual Helm render cases cover development/staging across short default/full overrides, the exact 63-character file-processor boundary, a valid 53-character release, and a schema-valid 63-character fullnameOverride. Root nameOverride is absent from the closed values schema and is not supplied or newly enabled. They require five distinct DNS-label Service names, matching unchanged Pod selectors, all generated internal URLs, Ingress and isolated dormant Gateway API references. The existing isolated renderer receives only an optional release_name argument; no new process primitive or waiver is introduced. Missing Helm is an assertion failure before any skip-capable helper.

Four long-name cases are expected to expose suffixes added after a 63-character base; six controls preserve valid short names. Existing helper and chart source remain unchanged until actual RED. The proposed component helper must preserve each known suffix within the 63-character Service limit and update every generated reference, without renaming Deployments, selectors, HPA/KEDA targets or valid existing names. Distinct known suffixes prevent within-release Service collisions; cross-release truncated-prefix collision resistance is not claimed.

Explicit operator-owned JWKS URLs, release issuer, TLS serverName and dependency endpoints stay unchanged. Actual certificate/hostname alignment remains a deployment concern. Gateway API is tested only through its existing isolated renderer; the full-chart activation gate remains closed. No dependency update, cluster contact or deployment is performed.

## Observed RED and narrow corrections

On db83651 / job 118456912531, all twelve intended failures occur: cleanup traces stop at the failed finalizer or retain only its error; diagnostic output reports 3610 seconds instead of 10; four long-name renders exceed the suffix-aware Service budget. All preservation controls pass. Aggregate 888 PASS / 13 FAIL includes the existing outage hold.

AUD-091 uses AsyncExitStack for sequential independent finalizers after the unchanged readiness/CDC/background-task phase. Single exceptions retain identity; with multiple failures, the last is primary and earlier originals remain in context. Finalizer-raised cancellation is retained, not silently converted to success. No external cancellation shielding or bounded duration is claimed. The existing restart failure test now isolates newly reachable finalizers while retaining its marker and recreation assertions.

AUD-092 adds one component-name helper, changes five Service metadata names and ten generated reference sites, and updates the exact dormant Gateway source assertion. Already-valid short names, Deployments, selectors, ports, explicit JWKS/TLS identities, dependency names and Gateway activation gate remain unchanged. The existing closed values schema still does not admit root nameOverride. Cross-release truncation collisions and other resource-name limits remain outside this correction.

AUD-093 retains wall-clock metrics and strict DAG/provenance semantics, but diagnostic lower bound becomes the maximum measured job execution duration. It does not invent dependencies or incorporate scheduler gaps. These three corrections require their own hosted GREEN before acceptance.

## AUD-094 accepted

Job 118456912531 explicitly passes colon-key round-trip/glob invalidation, four encoding round-trips and non-UTF-8 escape preservation. Source is unchanged; full-file selection supplies the missing proof. Scope remains in-memory grammar enforcement, not operational NATS, TTL or legacy escaped-name migration.

## AUD-096 listener tests first

Six cases exercise actual _listen_loop with deterministic synthetic connections and real asyncpg exception classes. A closed-connection InterfaceError and ConnectionDoesNotExistError must close the first connection before reconnecting and registering the second listener. Cancellation, the same InterfaceError text on an open connection, permanent SQL and authentication errors are preservation controls. Exact connect/sleep cardinalities prevent an accidentally broadened loop from spinning. asyncio.sleep is restored before fixture teardown. Existing successful-listener and builtin reconnect cases remain selected.

Do not classify InterfaceError after finally closes the connection: that would make open-connection programming errors appear retryable. No live PostgreSQL outage, outbox delivery, production retry-policy change or broader PostgresError catch is established by these tests.
