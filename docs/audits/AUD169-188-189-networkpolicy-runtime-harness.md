# Enforcing-CNI evidence for AUD-169, AUD-188 and AUD-189

**Status: not accepted.** The hosted kind job is defined and contract-tested. A
local validation run on the uncommitted working tree passed (see "Local validation
run"), but it is not hosted evidence for any source SHA, and no finding is accepted
by this document. This is a test protocol, not authorization to deploy, alter a
workload, attach a debug container, rotate a key or contact a cluster. Use only in an
owner-authorized, isolated test environment with the same CNI and relevant settings
as the target environment. Reconcile the evidence separately for each target
environment and source SHA. Staging and production are not assumed to exist.

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

## Hosted kind run (AUD-169, AUD-188, AUD-189, AUD-438)

Owner decision (2026-11-12): a disposable kind cluster with Calico enforcing
NetworkPolicy is the accepted target environment for these findings. The hosted
job is `.github/workflows/k8s-networkpolicy-runtime.yml`. It runs on
`workflow_dispatch`, weekly, and on pull requests that touch `charts/**`,
`k8s/**`, `backend.Dockerfile`, the job's scripts or the probe test helpers. It is
not a required check and does not change branch protection.

What the job does, in order:

1. Installs the pinned kind v0.31.0, kubectl v1.36.4 and Helm v4.2.4 binaries,
   verifying each against its official checksum (same pins as the AUD-373 job).
2. Creates a uniquely named kind cluster from the digest-pinned
   `kindest/node:v1.36.4` image with `disableDefaultCNI: true`. It then adds the
   link-local address `169.254.10.10/32` to the node container's `eth0`
   (`docker exec`, verified with `ip -4 addr show`; the job fails if it is absent).
3. Installs Calico v3.30.3 from a manifest whose sha256 is checked before
   `kubectl apply`, and waits for calico-node, calico-kube-controllers and CoreDNS.
4. Runs `scripts/k8s/networkpolicy_runtime_probe.py` (with its helper modules
   `networkpolicy_runtime_{kube,rows,app,standins}.py`) through
   `scripts/k8s/networkpolicy_runtime_proof.sh`. The probe renders the
   university-ecosystem and revocation-store charts for two releases (`probe-a`,
   `probe-b`) with the staging-contract arguments and asserts the rendered ports it
   depends on (fails closed on drift). Both releases render with `backup.enabled=true`
   (and an https `backup.minioEndpoint`, which staging validation requires; the name
   is never resolved), so the rendered `*-backup-policy` is applied.
5. Deploys the **real revocation Redis** StatefulSet and Services from the store
   chart in each release namespace, with a generated password Secret
   (`revocation-redis-credentials`, key `revocation-redis-password`) created for the
   run. The Redis image is the store chart's pinned digest. The metrics exporter
   sidecar, its password-file init container and its volume are removed from the
   rendered StatefulSet. The chart requires that init to use the private backend
   image, which kind cannot pull. The Redis server and its `redis-auth-acl` init,
   which installs the password, are unchanged.
6. Creates stand-in pods with the rendered pod-template labels of the
   file-processor, backend, ws-hub, gateway, frontend and outbox-worker workloads
   (the gateway, frontend and outbox-worker stand-ins are in `probe-a` only), plus
   an unrelated source, an in-cluster decoy (TCP 53, 80, 443), a Prometheus-labelled
   pod, a non-Prometheus monitoring pod and an ingress-controller-labelled pod. The
   stand-in base image is read at runtime from the runtime `FROM` line of
   `backend.Dockerfile`; the probe fails closed unless exactly one such line exists.
   Stand-ins run only the Python standard library. They are not the application
   images. Additional stand-ins added for the acceptance gaps:
   - `a-backup`: the rendered `db-backup` CronJob's pod-template labels (the backup
     policy's selector).
   - `a-temporal` and `a-nats`: pods labelled only `app.kubernetes.io/name=temporal`
     (port 7233) and `=nats` (port 4222) in `probe-a`. They carry no release
     selector labels, so no release default-deny applies to them.
   - `decoy-temporal` and `decoy-nats`: the same labels in the unselected namespace.
   - `linklocal`: a host-network pod (`hostNetwork: true`) listening on TCP/443 of
     `169.254.10.10`. Host-network traffic is not subject to pod NetworkPolicy, so
     this pod is the same-destination control for every link-local denial.
7. Proves every target and control is reachable before any policy is applied
   (baseline), and that the authenticated Redis PING succeeds before policy. It
   then applies the rendered policies and runs the 40-row probe matrix. Each denied
   attempt is bracketed by a control to the same destination that must succeed
   before and after it. A timeout without a live control is inconclusive, not a
   pass.
8. Runs the application-level checks in the enforced cluster (see below).
9. Writes `receipt.json` with one row per probe (finding, probe, source,
   destination, protocol, port, expected, observed, baseline, control, verdict),
   the resolver check, the `app_level` results, pod UIDs and IPs, policy names and
   spec hashes, and an explicit `not_run` list. The job exits non-zero on any
   non-pass verdict, including a failed baseline. No credential or key material is
   written to the receipt.
10. Uploads the receipt and diagnostics as the artifact
    `aud169-188-189-networkpolicy-runtime-receipt` with 90-day retention.

### Application-level checks

- **AUD-169 (revocation Redis).** From a pod with the file-processor's rendered
  labels, an `AUTH` with the generated password followed by `PING` must return
  `PONG`. An unauthenticated `PING` must return `NOAUTH`, and a wrong password must
  return `WRONGPASS`. From the unrelated-labels pod, the same correct password must
  time out at the network layer, bracketed by successful file-processor controls to
  the same Redis before and after. The password is supplied on stdin for each exec
  and is not in a pod spec.
- **AUD-188 (RS256 JWKS consumer).** The publisher is the backend-labelled stand-in,
  which serves a JWKS document written by the probe. The consumer is the
  file-processor-labelled stand-in, which fetches the JWKS over the enforced path and
  verifies RS256 with an RSA PKCS#1 v1.5 / SHA-256 check in the standard library. The
  sequence is: key 1 published and its token accepted; key 2 token rejected
  (`unknown-kid`) before publication; key 1 and key 2 published and key 2 accepted;
  key 1 still accepted during the transition; a token signed by an unpublished key
  rejected; a token with a published `kid` but another key's signature rejected
  (`bad-signature`); an `alg: none` token rejected; key 1 retired and its token
  rejected; key 2 still accepted. Keys are generated in-process with the project's
  `cryptography` dependency. Tokens and private keys are never written to the
  receipt.

### What the job does not prove (receipt `not_run`)

- **Real file-processor process.** Its JWKS refresher, gRPC `ProcessFile`
  acceptance and startup Redis ping are not run. `services/file-processor/cmd/
  file-processor/main.go` requires Temporal and NATS at startup, so the process
  cannot reach serving state in kind. The stand-in consumer exercises the same RS256
  and JWKS contract, but not the refresher's interval or last-known-good logic.
- Revoked and unrevoked token pairs through the file-processor (AUD-169).
- The backup CronJob's real `pg_dump` and `rclone` images. The backup policy is
  proven through a stand-in pod that carries the CronJob's pod-template labels, so
  the probes show policy enforcement only, not the dump or the upload.
- The ws-hub metrics payload. The `/metrics` stand-in answers any GET with HTTP 200,
  so the rows prove reachability on the `/metrics` path, not the exposition content.
- Staging or production topology, real NAT, or cloud load balancer behavior.
- The Redis metrics exporter, which is removed from the rendered workload (see
  step 5).

### Public TCP/443 exception (AUD-189, ADR-054 addendum 2026-11-12)

Owner-accepted residual risk: the `backend` and `backup` workloads may reach public
TCP/443 destinations, excluding the private, carrier-grade NAT and link-local
ranges. The job proves that the backend and the backup stand-in each reach
`1.1.1.1:443` (allowed rows), and that the file-processor, ws-hub, gateway, frontend
and outbox-worker stand-ins are denied the same destination, each with a backend
control. The exception does not count as proof of any specific provider.

### Probes added for the acceptance gaps (AUD-169, AUD-188, AUD-189, AUD-438)

Each row is a connection attempt from a stand-in source; denials are bracketed by a
live control to the same destination. The rows are defined in
`scripts/k8s/networkpolicy_runtime_rows.py`.

- **AUD-188, file-processor Temporal and NATS egress.** `aud188-temporal-allow`
  (`a-fp` to `a-temporal-pod`, TCP/7233) and `aud188-nats-allow` (`a-fp` to
  `a-nats-pod`, TCP/4222) must connect. `aud188-temporal-decoy` and
  `aud188-nats-decoy` must be denied to the identically labelled pods in the
  unselected namespace, with an unrelated-source control. The source is the
  stand-in carrying the rendered file-processor Deployment labels, not the binary.
- **AUD-189, backup egress.** `aud189-backup-public` (`a-backup` to `1.1.1.1:443`)
  is the only allowed backup row. `aud189-backup-decoy-443` (in-cluster TCP/443),
  `aud189-backup-decoy-80` (in-cluster TCP/80) and `aud189-backup-backend-8000`
  (release backend TCP/8000, with a file-processor control) must be denied, so
  nothing except public TCP/443 (plus DNS) is granted to the backup workload.
- **AUD-189, link-local denial.** `aud189-linklocal-fp`, `aud189-linklocal-backend`
  and `aud189-linklocal-backup` must be denied for TCP/443 to `169.254.10.10`, the
  host-network listener. The same address is reachable from the host-network control
  before policy (baseline) and after it. The backend and backup workloads hold a
  TCP/443 public grant, so their link-local rows are the ones that test the
  `169.254.0.0/16` exception in `httpsEgressRules`.
- **AUD-438, `/metrics`.** `aud438-metrics-prometheus` must return HTTP 200 for
  `GET /metrics` on the ws-hub metrics port from the Prometheus pod. The denials
  `aud438-metrics-other` (monitoring, non-Prometheus pod), `aud438-metrics-unrelated`
  (unselected namespace) and `aud438-metrics-ingress` (ingress controller) use the
  Prometheus HTTP request as their control. The public WebSocket port rows are
  unchanged.

The link-local proof depends on the kind node accepting a link-local `/32` on
`eth0` and on the host-network route to it; a failure of either is a setup failure,
not a pass.

### Elasticsearch peer (AUD-189, chart contract)

An in-cluster `backend.config.elasticsearchURL` (a single-label host or a host in
the release namespace) is admitted only through `networkPolicy.elasticsearch`
selectors and its explicit port. Without them, or without an explicit port, the
chart fails to render. External endpoints keep their TCP/443 CIDR requirement. These
rules are checked by the chart contract tests, not by the kind job. The
Elasticsearch release must admit this workload in its own policy.

Local validation run (2026-11-12, not hosted): the probe was run against a local
kind v1.36.4 cluster with Calico v3.30.3 on Docker Desktop, using the uncommitted
working tree. The verdict was `pass`: 27 probe rows, 4 AUD-169 checks, 9 AUD-188
checks and the resolver check. That run predates the Temporal/NATS, backup,
link-local and `/metrics` probes described below; the 40-row matrix has not been run
anywhere, locally or hosted. The shell proof script is Linux-only and was not
run; its pins and the probe arguments are the same. A first run exposed an invalid
public-denial row for an unlabelled namespace, which has no chart policy and was
replaced by denials for the chart workloads. This run is not acceptance evidence.

Current status: the workflow, probe modules and contract tests are in the
repository. No hosted run is recorded for any source SHA, and this document does
not accept AUD-169, AUD-188, AUD-189 or AUD-438. Acceptance requires a green hosted
run of the job for the exact source SHA, with the receipt artifact retained, plus
owner review of the `not_run` items above. The orchestrator records that acceptance
after the run; this document does not.

To run it manually: open the "Kubernetes NetworkPolicy runtime proof" workflow in
GitHub Actions and choose "Run workflow" on the branch under test. Locally, the
shell script needs Linux x86_64, Docker, and uv, and it creates and deletes its own
kind cluster:

```sh
bash scripts/k8s/networkpolicy_runtime_proof.sh
```

The public denial rows and their controls use `1.1.1.1:443`, so the hosted run
needs outbound internet access from the runner.

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
| AUD-169 | A file-processor to A revocation Redis, direct Pod IP and configured Service | TCP/6379 succeeds through both policy directions; authenticated Redis PING succeeds without printing credentials. |
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

The kind job's stand-in RS256 consumer (see "Application-level checks") does not
replace steps 1 to 4 for the real file-processor. It covers the key-set and
signature contract on the enforced network path only.

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
