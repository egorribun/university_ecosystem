# Review workload registrations before applying them

`register-workloads.sh` is now **plan-only**. It does not run `kubectl`, create
entries, grant access, generate credentials or enable mTLS. There is no `--apply`
option. The former script guessed a cluster-wide parent ID and registered bare
service accounts in `default`; neither matched the Helm deployment contract.

Provide a reviewed rendered Helm manifest, its explicit release and namespace,
and one **already-attested concrete agent ID** obtained from the intended SPIRE
server. The parent must identify a real node/pod in the same trust domain, not
just the `/spire/agent/k8s_psat/<cluster>` prefix. An operator must independently
verify its attestation, cluster and eligible workload nodes. The planner checks
syntax and consistency only; it cannot establish that an agent exists.

```sh
k8s/spire/register-workloads.sh \
  --rendered reviewed-render.yaml \
  --namespace university-ecosystem \
  --release university-ecosystem \
  --parent-id "$VERIFIED_ATTESTED_AGENT_ID" > registration-plan.json
```

The selected backend/gateway and any selected ws-hub/internal-JWKS file-processor
must have explicit enabled transport configuration in this **offline render**.
This is not permission to change a deployed release or to enable release values.
The planner emits the render hash and command argument arrays. Selectors come
from the actual namespace and `serviceAccountName`; SPIFFE URIs come from the
actual identity environment. A logical backend ID ending in `/sa/app` is valid
even though its Kubernetes service account is `<release>-backend`.

Backend authorized clients must exactly equal the active identity set including
its own probe. Clients must expect that exact backend ID. Duplicate identities,
accounts, components or environment names fail closed. Inactive public-JWKS
file-processors receive no entry. Unrelated secrets are not emitted. The
bounded YAML parser rejects duplicate mapping keys and does not print source
snippets on failure.

After source-bound tests and issued-SVID/rotation proof, the owner must separately
review current SPIRE entries, the desired per-node plan, intended selectors and
release changes. Apply or reconcile reviewed entries only through that explicit
operation. Do not pipe this output into a shell, append automatic execution, or
treat repeated `entry create` as idempotent reconciliation. A plan for one agent
does not authorize every cluster node; additional verified nodes require their
own plans. No administrator, downstream, federation or node-alias grants are
included. X.509 SVID TTL is 3600 seconds; it is not an expiry for registration
authority and does not replace deliberate entry retirement.

References: SPIRE [1.15.3 entry CLI](https://github.com/spiffe/spire/blob/v1.15.3/doc/spire_server.md#spire-server-entry-create)
and [k8s_psat identity format](https://github.com/spiffe/spire/blob/v1.15.3/doc/plugin_server_nodeattestor_k8s_psat.md).


## Workload attestor RBAC boundary

The pinned SPIRE 1.15.3 agent uses the default PID-based `k8s` workload attestor.
It fetches `/pods` from the local kubelet, not by listing or watching Kubernetes
API-server pods. The default manifest therefore grants no API-server `pods`
permissions to the agent. Enabling broker object references, API-server caching
or namespace-label selectors requires a separate configuration and RBAC review.
See the [pinned attestor documentation](https://github.com/spiffe/spire/blob/v1.15.3/doc/plugin_agent_workloadattestor_k8s.md)
and [kubelet client](https://github.com/spiffe/spire/blob/v1.15.3/pkg/agent/plugin/workloadattestor/k8s/kubeletclient.go).

The agent holds only `nodes/pods` `get`. The pinned attestor's `GET /pods` on
the kubelet secure port is authorized as `nodes/pods` `get` when
`KubeletFineGrainedAuthz` is enabled; the `nodes/proxy` grant is removed because
it authorizes every other kubelet endpoint, including WebSocket exec. Every
deployed kubelet must have `KubeletFineGrainedAuthz` enabled (default-on from
Kubernetes v1.36 per the [kubelet authorization](https://kubernetes.io/docs/reference/access-authn-authz/kubelet-authn-authz/)
docs). The AUD-373 kind job exercises SVID issuance under this grant. The
AUD-251 finding stays Open in [docs/audits/INDEX.md](../../docs/audits/INDEX.md)
until the owner closes it on live evidence.

## SPIFFE CSI driver socket path

The chart mounts the SPIRE Workload API into pods through the `csi.spiffe.io` driver.
The driver is not part of these manifests. Operators must install `spiffe-csi-driver`
with `agentSocketPath=/run/spire/sockets/agent.sock`, which matches the agent
`socket_path` in `spire-agent.yaml` and its `/run/spire/sockets` hostPath. The upstream
default (`/run/spire/agent-sockets/spire-agent.sock`) points at a different directory, so
pods get no SVID when the value is left unset. The kind proof sets the same value at
install time (`scripts/kind/aud373_internal_mtls_proof.sh`, `AGENT_SOCKET_PATH`);
`tests/test_spire_csi_driver_contract.py` asserts that both agree.

```sh
helm upgrade --install spire-csi <spiffe/spire 0.30.4 chart dir> --namespace spire \
  --set spire-server.enabled=false --set spire-agent.enabled=false \
  --set spiffe-oidc-discovery-provider.enabled=false --set spire-identity-exchange.enabled=false \
  --set spike-keeper.enabled=false --set spike-nexus.enabled=false \
  --set spike-pilot.enabled=false --set tornjak-frontend.enabled=false \
  --set spiffe-csi-driver.agentSocketPath=/run/spire/sockets/agent.sock
```
