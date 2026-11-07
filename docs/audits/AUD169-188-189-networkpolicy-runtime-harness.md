# Pending enforcing-CNI evidence for AUD-169, AUD-188 and AUD-189

**Status: not run.** This is a future test protocol, not authorization to
deploy, alter a workload, attach a debug container, rotate a key or contact a
cluster. Use only in an owner-authorized, isolated test environment with the
same CNI and relevant settings as the target environment. Reconcile the evidence
separately for each target environment and source SHA. Staging and production are
not assumed to exist.

The local `tests/test_aud169_188_189_networkpolicy_topology.py` renders two
synthetic application releases and their revocation stores, checks service and
workload metadata, and evaluates the rendered policies' selector/port intent. It
does not observe a cluster, resolve a Secret, test a packet, verify a JWKS
refresh, or establish behavior across Service DNAT or implementation-specific
CNI policy. Its addresses are synthetic examples. The default HTTPS exceptions
cover the listed private, carrier-grade NAT and link-local ranges, not every
possible cluster or Service CIDR. Operator-verified CIDRs and runtime evidence
are required, particularly for globally routable cluster ranges and for
explicitly configured private HTTPS exceptions.

## Prerequisites and inventory

1. Record the exact source commit and image digests, chart versions and resolved
   non-secret values, test namespace, timestamp, Kubernetes version, CNI name
   and version, IP families, Pod and Service CIDRs, and DNS topology including
   any NodeLocal DNS cache. Capture pod UIDs, Pod IPs, node names and network
   namespace identity, Service selectors/ClusterIPs/ports and ready EndpointSlice
   addresses. Confirm that both the app and its dedicated revocation store use
   the same namespace and release identity. Verify the configured Redis URL's
   **host and port only**, without collecting its credentials or Secret value.
2. Capture **all** effective namespaced Kubernetes NetworkPolicies selecting the
   test workloads and targets, including other releases and default-deny rules,
   plus applicable CNI-specific global/cluster policies. NetworkPolicies are
   additive. Record any additional policy, NAT behavior or explicit HTTPS
   `privateCIDRs` allowance that changes the expected result. Do not infer an
   effective deny by inspecting just one chart policy.
3. Establish a controlled positive/negative CNI canary in the authorized test
   environment: a known listening destination accepts a connection from an
   allowed source, while a separately isolated source is denied to **the same
   destination**; observe the corresponding CNI policy verdict. An open
   listener, missing routing, or an unready pod can otherwise look like policy
   enforcement. If either side or the CNI verdict is unavailable, mark the
   affected result **inconclusive**.
4. Select two application releases, A and B, each with its own backend and
   revocation store, and an unrelated source pod. Run any debug process in the
   **existing test pod's network namespace**, so the source IP and policy
   identity really are those of that pod. The file-processor image is
   distroless and has no assumed shell or Python: a separately authorized,
   non-root diagnostic ephemeral container can provide `python3` and `dig`.
   It must use the pod's existing network namespace, no host network, no host
   mounts, no added capabilities and no privilege escalation. Record pod UID,
   container image digest and proof of the shared namespace. Do not create a
   lookalike pod with workload labels: it could be selected by Services or
   controllers. Attach no diagnostic container to production under this
   protocol.
5. Prepare operator-owned listeners on TCP/443 at a private Pod IP, a private
   ClusterIP, a link-local destination if supported, and an approved public
   address. These must be separate from DNS and other existing permitted
   workload ports. Provide at least one permitted control source able to connect
   to the same destination throughout each denial test. For every IP family
   actually deployed, use matching-family sources and targets. Never probe an
   unowned endpoint.

## Connection probe

Run this from an operator workstation after the authorized diagnostic
container is present. The same command works against Pod IPs and Service IPs;
`$POD`, `$DIAG_CONTAINER`, `$DESTINATION`, `$PORT` and `$NS` are explicit
operator-supplied test values. It only attempts a bounded TCP connection and
prints the outcome, not credentials. A refused connection is not by itself a
NetworkPolicy denial.

```sh
kubectl -n "$NS" exec "$POD" -c "$DIAG_CONTAINER" -- \
  python3 -c 'import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=4); s.close(); print("connected")' \
  "$DESTINATION" "$PORT"
```

For each denied case, interleave a successful control probe to the **same**
destination immediately before and after the denied attempt, record the source
and destination Pod IPs and timestamps, and correlate the denied attempt with
the CNI's direction, policy identity and drop/reject verdict. A timeout, RST,
DNS failure or connection refusal without this corroboration is inconclusive.
Separate egress and ingress attribution: a target must permit both sources
when testing source egress, and both sources must have permitted egress when
testing target ingress. If a synthetic control changes labels or policies,
record those changes and do not treat its result as a production observation.

| Finding | Source and destination | Required observation |
| --- | --- | --- |
| AUD-169 | A file-processor to A revocation Redis, direct Pod IP and configured Service | TCP/6379 succeeds through both policy directions; independently confirm application startup and authenticated Redis PING without printing credentials. |
| AUD-169 | A file-processor to B revocation Redis; unrelated source to A Redis | Denied with live target controls and attributable policy verdict; B file-processor to B Redis succeeds. |
| AUD-188 | A file-processor to A backend JWKS, direct Pod IP and configured Service | TCP backend port and HTTP 200 for the actual `/.well-known/jwks.json` URL, no redirect, from the actual file-processor network namespace. |
| AUD-188 | A file-processor to B backend; unrelated source to A backend | Denied with live target controls and attributable policy verdict; B to B backend succeeds. |
| AUD-189 | A file-processor to actual configured resolver, UDP and TCP 53 | A known test name returns the expected answer on each transport. Test the actual DNS path, including any NodeLocal cache and both IP families if deployed. |
| AUD-189 | A file-processor to a controlled non-resolver listener on UDP/TCP 53 | Denied with a live same-destination control and CNI verdict. A DNS name that simply fails to resolve is not evidence. |
| AUD-189 | A file-processor to private Pod IP, private ClusterIP, link-local and approved public TCP/443 listeners | Private/link-local targets are denied unless an explicitly reviewed allowance applies; approved public target succeeds. Record actual Pod/Service CIDRs, explicit exceptions and post-/pre-DNAT verdicts. |

For the JWKS URL, an approved diagnostic image containing `curl` can verify
the HTTP status without following redirects or printing the response body:

```sh
kubectl -n "$NS" exec "$POD" -c "$DIAG_CONTAINER" -- \
  curl --silent --show-error --max-time 5 --output /dev/null \
  --write-out '%{http_code}\n' "$JWKS_URL"
```

Require `200` and a successful command exit; keep TLS certificate verification
enabled for HTTPS. The URL must be the credential-free configured endpoint.
This probe tests HTTP reachability only; the application's fetch and key refresh
still need the per-replica authentication sequence below.

Use an owned DNS name with a known answer. For each actual resolver IP, run
`dig +time=3 +tries=1 @<resolver-IP> <owned-name> A` inside the diagnostic
container, repeat with `+tcp`, and check both status `NOERROR` and the expected
answer. Repeat with `AAAA` when applicable. For negative UDP/TCP DNS cases use
the same query against a known responsive, controlled non-resolver DNS listener;
check the control and CNI verdict as above. A TCP connect alone does not prove
UDP DNS operation. Substitute concrete test addresses, not guessed ranges.

## JWKS refresh and application evidence

Use a dedicated, authorized isolated issuer and synthetic test identities, with
short-lived keys and tokens and release-equivalent authentication and mTLS
settings. Record only opaque public key identifiers, timestamps, status codes,
and the target pod UID; never save bearer tokens, private keys or credentials in
the receipt. Exercise each file-processor replica directly, so load balancing
cannot substitute a different process. Run the authentication client from an
authorized test gateway pod's network namespace: the file-processor ingress
policy permits the gateway, not an arbitrary diagnostic source. The client must
have the required test-only mTLS identity and access its test token and key via
protected files; if that cannot be arranged, mark the application probe pending.

1. Establish that an authenticated request signed with currently published key
   A reaches the file-processor authentication boundary and passes validation.
   A safe probe is an otherwise valid authenticated `ProcessFile` call with an
   empty request: after authentication it must return `InvalidArgument` before
   any workflow starts. `grpc.health.v1.Health` is exempt from authentication
   and cannot establish JWT acceptance. Use the required mTLS client identity
   and a purpose-built client that reads its token from a protected file rather
   than a command argument or log. Confirm the no-side-effect behavior against
   the current source before running.
2. Generate a distinct key B and correctly scoped, unrevoked synthetic token B.
   Before B is published, the same pod and same request must return
   `Unauthenticated`; verify the token's issuer, audience, expiry, active state
   and revocation independently so an unrelated error cannot fake the result.
3. Publish B through the authorized test issuer's normal rotation procedure;
   retain A according to the dual-key rotation contract. Record the publication
   time and actual `FP_JWKS_REFRESH_INTERVAL`. After the next bounded refresh,
   require B to return `InvalidArgument` at each unchanged pod UID, with a
   corresponding backend JWKS request or equivalent observation from that
   pod. This proves the new key was used without restarting the process. If
   publication, per-replica routing, an auth-only client, or correlation is
   unavailable, mark refresh **not demonstrated**; do not substitute a TCP or
   generic health check.
4. For AUD-169, retain the startup and Redis PING evidence plus a synthetic
   unrevoked/revoked token pair, using the same non-mutating gRPC request and
   application authentication boundary. The revoked token must be rejected
   and the unrevoked token must pass authentication. No real user session is
   needed. Actual secret references, key material and tokens stay private.

## Receipt and acceptance limits

Store a private receipt per source SHA and environment with: UTC start/end;
cluster/CNI identity and policy-enforcement canary; source/destination pod UIDs,
node and IP family; Service and EndpointSlice mapping; all selected policy
names, UIDs and hashes; configuration and image digests; actual DNS and network
CIDRs; probe matrix with pre/post controls, exit status, timestamps and CNI
verdict; JWKS publication/refresh observations; and the application-level Redis
and JWT results. Record skipped, unsupported and inconclusive cases explicitly.
Review Service translation and any CNI-specific policy independently. No row
passes because of a successful render, a single timeout, a generic health
check or another environment's receipt. Required hosted checks for the current
source SHA remain separate.
