# Temporal network access

This runbook describes the listener and network boundaries in the pinned
Temporal Server 1.30.7 Compose configuration. It records a scoped runtime proof
and its evidence boundaries; it is not a claim that every other container can
reach only port 7233.

## Listener inventory

| Port | Listener | Network binding and boundary |
| --- | --- | --- |
| 7233 | Frontend gRPC | Bound to `0.0.0.0`; configured JWT authorization applies to frontend RPC requests. |
| 6933 | Frontend membership | Bound with the frontend address on attached networks; it is not covered by the JWT checks. |
| 7243 | Frontend HTTP API | Bound with the frontend address on attached networks; HTTP calls forwarded to RPC handlers use the configured authorization. Full Compose publishes this port on host loopback. |
| 8000 | Prometheus metrics | Bound to `0.0.0.0`; has no Temporal JWT authorization and is used by the container-local health check. It is not host-published in the reviewed Compose profiles. |
| 7936 | pprof | Configured by port in source; Temporal Server 1.30.7 defaults its omitted host to `localhost`. The runner's intended checks do not include a live probe of this socket. |
| 6934, 6935, 6936, 6939, 7234, 7235, 7236, 7239, 7246 | Internal service listeners | Bound to `127.0.0.1` inside the Temporal container. These are the nine ports targeted by the runner's peer-negative checks. |

The worker scanner's system client uses `internal-frontend`. That listener has
the `NoopClaimMapper` and must remain loopback-only; do not publish its ports or
change its bind address. The entrypoint also enforces the fixed single-container
service list and requires HTTPS for JWKS retrieval.

## Host publications and Compose peers

The normal Compose profile publishes gRPC 7233 on host loopback. Full Compose
publishes 7233 and HTTP API 7243 on host loopback. These publications constrain
access through the host; they do not filter direct connections from other
containers attached to Temporal's networks. The listener bind addresses above
define the peer-reachability boundary.

## Starting the managed namespace bootstrap

Use the PowerShell 7 launcher for the normal full stack, following the
[Ignition instructions in the README](../../README.md#2-ignition):

```powershell
.\start-docker.ps1 -Build
```

Before namespace initialization, the launcher issues a short-lived
`default:admin` profile. The initializer first tries the worker's
`default:write` credentials and uses the bootstrap profile only when namespace
administration is required. Keep the long-running worker at `default:write`.
The public frontend JWT and loopback-only internal frontend configuration stay
unchanged.

Direct `docker compose up` and the `scripts/dc.ps1` / `scripts/dc.sh` wrappers
do not issue the profile. If `.temporal-bootstrap/profile.toml` is absent, the
initializer's bind uses `create_host_path: false` and startup fails closed.
Keep this short-lived profile local: `.gitignore` and `.dockerignore` must
exclude `.temporal-bootstrap/` from commits and Docker build contexts.

## Runner scope and evidence boundary

A source-bound runtime proof on a separately recorded source snapshot passed in 46.292 seconds. Public gRPC
7233 connected, five JWT denial controls passed, and the `jwks` peer was refused
on each of the nine internal ports listed above. The file processor used
`default:write` to process a permissioned workflow; a traversal job was rejected
before any MinIO request. Both built-in scanner workflow-start markers appeared,
with no fatal marker. This confirms scanner startup markers, not scanner polling.

The proof does not cover unlisted ports or a live pprof check on 7936. It is bound
to a separately recorded source snapshot and does not establish hosted required
checks for the post-CAS source. The earlier retry failed during Go test compilation
before its test body ran; that separate failed receipt remains preserved and does
not change this later scoped pass.

Cleanup was independently verified: Compose down exited successfully, no resources
with the exact project label remained, the bootstrap lease was scrubbed, and the
runtime-input directory was empty with its protected ACL retained. Synthetic
inputs were removed. These results do not establish the full repository gate or
hosted acceptance.

If the required boundary changes to “all other peers can reach only 7233,”
host-loopback publications do not satisfy that requirement. A network ACL or
topology change needs its own design and owner approval. Keep the current JWT,
JWKS, scanner, and loopback internal-listener settings intact while evaluating
such a change.

## Source references

- [README startup instructions](../../README.md#2-ignition)
- [PowerShell 7 startup launcher](../../start-docker.ps1)
- [Namespace initializer](../../scripts/temporal/namespace-init.sh)
- [PowerShell Compose wrapper](../../scripts/dc.ps1) and [shell Compose wrapper](../../scripts/dc.sh)
- [Bootstrap runtime contract tests](../../tests/test_temporal_bootstrap_runtime.py)
- [Temporal listener and authorization configuration](../../services/temporal/config.yaml)
- [Temporal entrypoint and fixed service list](../../services/temporal/entrypoint.sh)
- [Normal Compose profile](../../docker-compose.yml)
- [Full Compose profile](../../docker-compose.full.yml)
