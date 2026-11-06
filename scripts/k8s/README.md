# AUD-169/188/189 evidence consistency checker

`aud169_188_189_evidence.py` is an **offline checker**, not a cluster test.
It does not deploy, contact Kubernetes, attach a container, issue traffic,
read a Secret, rotate a key, authenticate evidence, or accept an audit. A zero
exit code says only that the supplied, normalized records meet these checks.
Owner review and the separate observations required by
[`AUD169-188-189-networkpolicy-runtime-harness.md`](../../docs/audits/AUD169-188-189-networkpolicy-runtime-harness.md)
remain mandatory. Both the receipt and raw observations must be kept in an
access-controlled location outside this repository. Never include bearer
tokens, private keys, credentials, or Secret values in them.

In an owner-authorized isolated environment, obtain the observations described
in that protocol first. Normalize them to the JSON shape illustrated by
`receipt()` in `test_aud169_188_189_evidence.py`; all values in that fixture are
synthetic and are **not** evidence. Then run:

```sh
python scripts/k8s/aud169_188_189_evidence.py /private/path/receipt.json \
  --expected-source <40-character-lowercase-source-commit>
```

Incomplete and inconsistent sections produce a nonzero exit. The checker
prints reason codes only and does not echo receipt contents. It requires a
complete set of the supported checks; unsupported address families,
unavailable verdicts, an intentional private exception, or missing data remain
incomplete, not successful. Its fixed bounds are conservative: 30 seconds from
the first control through the last control, and the configured refresh interval
plus five seconds of HTTP timeout and 30 seconds of scheduling allowance.

## Records and trust boundaries

- The source commit, clean build source, signed image provenance reference and
  running image digest must agree. Verify the provenance signature and clean
  build context independently. The checker compares the supplied metadata; it
  cannot establish that the metadata is true or that a digest's artifact exists.
- Identify the cluster and CNI version, each deployed IP family, actual Pod and
  Service CIDRs and resolvers. Preserve inventories of every applicable
  Kubernetes and CNI-specific policy and include the policy UIDs in the
  normalized record. An inventory digest is not proof of completeness.
- For the separate canary and each denial, use distinct actual Pod identities
  for the isolated source, permitted control and listener. Record the actual
  container ID, restart count, start time, image digest, Pod IP and node before
  and after. Supply evidence that the non-root diagnostic container shares the
  source Pod's network namespace, uses a digest-pinned image, has no host
  network, host mounts, added capabilities, privileges or privilege escalation.
  The checker requires the resulting namespace IDs and diagnostic security
  attributes; it cannot independently inspect Kubernetes or the runtime.
- A denial needs successful controls to the same listener on both sides, the
  exact source, protocol and destination, and a contemporaneous egress
  drop/reject verdict tied to an inventoried policy UID. For DNS, the controls
  must return the expected response over the transport being tested. For a
  Service target, the isolated Service has exactly one ready endpoint and an
  unchanged EndpointSlice observation; record both pre- and post-DNAT
  addresses when the CNI reports translated traffic. Do not interpret a timeout
  or refusal as a policy verdict.
- For JWKS, record the exact credential-free configured endpoint, observed
  publication retaining key A while adding key B, and the actual effective
  refresh interval. Use independent issuer-side observations of each unchanged
  replica's successful fetch of the published JWKS document, including TLS and
  client identity verification when required. Exercise the actual
  `/file_processor.v1.FileProcessingService/ProcessFile` boundary directly at
  every replica. The same short-lived, synthetic token B must change from
  `Unauthenticated: invalid token` before publication to
  `InvalidArgument: id is required` after its correlated fetch; token A must
  reach the same validation error before and after. Independently validate the
  synthetic token's issuer, audience, signature, activation, revocation and
  lifetime. Record a SHA-256 digest of the synthetic token to correlate calls,
  never the token itself. Only use test identities; treat even their digests as
  private if local policy requires it.
- Pod UID alone is insufficient to demonstrate an unchanged process. Compare
  the actual container ID, restart count and start time before and after JWKS
  rotation, and correlate the fetch and direct gRPC calls to that container.
  The current source rejects an empty `ProcessFile` request before capability
  checks and before starting a Temporal workflow; reverify this against the
  exact source before an authorized run.

The checker covers an isolated enforcement canary, the listed non-resolver DNS
and private/link-local egress denials, and per-replica JWKS rotation. It does
**not** check all audit prerequisites: owner-verified effective policy and
Service translation, positive DNS and approved-public-HTTPS traffic, real
backend/Redis Service and Pod connectivity, cross-release ingress/egress,
authenticated Redis PING, startup, or the synthetic revoked/unrevoked
application token pair. It also cannot resolve explicitly reviewed private
allowances. Complete those observations separately for each source SHA and
environment; a checker success does not establish a passing live test.
