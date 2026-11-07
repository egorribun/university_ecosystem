# ADR-052: Backend SPIFFE identity at the HTTP transport boundary

## Status

Proposed and not accepted. The transport and its client integrations exist in
source. The Helm chart defaults internal HTTP mTLS off, while production chart
rendering requires it. The required SPIRE issuance and rotation proof remains
outstanding; neither the source nor the chart requirement closes AUD-373.

## Context

ADR-043 removed a nonfunctional Python identity implementation and requires a
new ADR, the actual `spiffe` dependency and demonstrated SPIRE issuance and
rotation before reintroduction. We preserve all three requirements. The
`eb470c8` listener instead loads mounted certificates once and accepts any
client chaining to its CA; this does not provide workload URI authorization or
continuous Workload API rotation. We must replace that transport, not rename it.

## Proposed decision

We use the real `spiffe==0.3.2` SDK in each Gunicorn worker, created after fork.
A bounded initial Workload API fetch must succeed before accepting HTTP. We read
`X509Source.get_x509_context()` for coherent SVID and trust-bundle snapshots;
we do not use deprecated separate properties or a fabricated SDK facade.
We reject whitespace/control characters before the 0.3.2 identity parser, whose
trailing-newline defect is fixed in 0.4.0. That version was not yet
cooldown-eligible when this proposal was recorded on 2026-11-02, and remains
outside the currently pinned dependency range.
Only the expected backend identity and its own trust-domain bundle are accepted.
Federated bundles are not pooled into the local-domain trust store.

We build a new immutable stdlib SSL context for each identity/bundle generation.
We never mutate an SSL context already used by a connection: in-place additions
would retain removed roots, and changing a live identity has unspecified effects.
A short-lived private directory on a pod-local memory-backed volume accommodates
stdlib's file-only key loader; material is unlinked before context publication.
No certificate or key is persisted as a release artifact or supplied as an HTTP
header. The agent socket, not mounted static credentials, supplies identities.

The real image CMD selects a dedicated worker. Its TLS adapter requires a valid
client chain and its H11 protocol authorizes exactly one URI SAN before calling
HTTP parsing/dispatch. Authorization is exact membership, not a trust-domain or
path-prefix match. This boundary applies to every route including health and
JWKS. Existing internal token/HMAC and user authorization remain in force.
The loopback probe presents an issued identity and validates the exact backend
URI before sending GET; loopback does not bypass authorization.

Source failure, a missing bundle, expired material, malformed configuration,
unknown clients, or a failed refresh must prevent dispatch and must never select
plaintext. New handshakes use the newest generation. Existing keepalive and
upgraded connections are tracked separately from protocol classes and retired
on trust-generation replacement or expiry;
HTTP pipelining cannot bypass checks through `on_response_complete`; a
transport-bound delegate also checks at actual ASGI task entry and receive/send.
Timers cover the actual verified peer chain, own certificate chain and local
bundle authorities, not only leaf expiry. Expired unused local bundle authorities
are rejected conservatively; SPIRE must remove them during rollover.
Enabled transport requires public verified-chain access (Python >=3.13); the
canonical runtime remains Python 3.14 and package metadata is not narrowed.
Terminal SDK closure is additionally polled every 250ms for idle connections;
every inbound dispatch checks the source directly. Already-authorized application
transactions are not rolled back by connection teardown.
The production Helm profile requires this flag, while the chart default and
staging overlay leave it off. The complete Go/backend chain and the proof below
must pass before acceptance or enablement.

## Validation required before acceptance or enablement

We must run an isolated SPIRE agent/server test against the actual image CMD:
issued server/client SVIDs, two workers, authorized caller success, wrong URI
under the same CA rejected before application invocation, no certificate and
untrusted CA rejected, exact probe server URI verification, SVID renewal without
worker restart, CA overlap followed by old-root removal, and rejected stale
connections. Include missing/invalid update, unavailable agent at startup,
reconnection, expiry, no-SNI clients and TLS 1.3 retry/resumption negative controls.
Static generated certificates and mocked SDK snapshots cannot replace this proof.
No completed source-bound SPIRE issuance and rotation proof is recorded for
acceptance of this proposal.

We retain all existing hooks, 78 required contexts, coverage floors and scanner
policies. Lock resolution with pinned uv, warnings-as-errors, strict typing,
protocol coverage and source-bound CI are additional prerequisites, not waivers.
The entire `app/server/**` transport authentication boundary is explicitly
classified Tier 0 in `quality/ownership-mapping.json`. Its line, statement,
branch and function floors remain 100%; no exception or unsupported-metric
waiver is introduced. Classification is not evidence that those floors pass.

## Tradeoffs and rollback

We add a worker-local gRPC watcher and a TLS transport adapter. This avoids a
spoofable header boundary, but its fork, rotation and connection-lifetime
semantics require careful tests. The implementation recomputes the public-material
fingerprint on each snapshot read; throughput and memory are unmeasured. A future
optimization may cache updates only if callback failure remains fail-closed.
We do not raise the existing memory limits.

A failed release rolls back the complete compatible image/config set. A
production failure must not automatically disable mTLS or restore plaintext.
Mounted-certificate-only operation would require a separate explicit policy
decision and is not an alternative accepted by this ADR.

## Sources

- [ADR-043](ADR-043-retire-python-spiffe-mtls.md)
- [Pinned SDK source](https://github.com/HewlettPackard/py-spiffe/blob/spiffe-v0.3.2/spiffe/src/spiffe/workloadapi/x509_source.py)
- [Pinned SDK metadata](https://github.com/HewlettPackard/py-spiffe/blob/spiffe-v0.3.2/spiffe/pyproject.toml)
- [Python SSL context rules](https://docs.python.org/3.14/library/ssl.html#ssl-contexts)
