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
