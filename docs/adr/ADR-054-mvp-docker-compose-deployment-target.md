# ADR-054: Docker Compose is the MVP deployment target

## Status

Accepted by the owner on 2026-11-09.

## Context

The owner confirmed on 2026-11-07 that no target Kubernetes profile is selected and
no Kubernetes deployment is authorized. Several open audit findings can only be
proved on a real cluster, because they check how NetworkPolicy and RBAC behave on an
actual CNI. Other findings needed a named target topology to be judged at all.

## Decision

MVP v1.0.0 runs on Docker Compose on one host.

**Kubernetes findings stay open.** AUD-169, AUD-188, AUD-189, AUD-251 and AUD-438 are
not resolved and are not marked as not applicable. The Helm chart remains in the
repository but is not the MVP deployment path. Each finding's prepared check must
run before any first Kubernetes deployment.

**The Compose topology is the AUD-167 target topology.** That finding still needs its
check through the actual Caddy-to-gateway and Caddy-to-ws-hub paths.

**The owner accepts plaintext internal traffic for the MVP.** The mTLS transport in
[ADR-052](ADR-052-backend-spiffe-transport.md) exists only through the Helm chart, so
AUD-373 is accepted for the chart and not for Compose. In Compose the gateway calls
the backend at `http://backend:8000` without TLS, and tokens and identity travel in
that plaintext. In `docker-compose.full.yml`:

- the gateway and the backend share the `internal` and `revocation_net` networks,
  which are `internal: true`, and also the `public` network, which is not;
- `public` also holds Caddy, ws-hub, the image proxy, object storage and the
  observability services;
- only Caddy publishes ports on all host interfaces (80 and 443); the other published
  ports bind to 127.0.0.1.

Traffic is therefore not reachable from the internet except through Caddy. A
compromised service on `public`, or anyone with access to the host, can call the
backend directly and can try to intercept this traffic.

## Consequences

- Trust inside the host is an explicit MVP limitation and belongs in the release
  notes, together with the five open Kubernetes findings.
- The formal audit total cannot reach 512/512 while these findings stay open.

## Revisit

Revisit this decision before any Kubernetes deployment and before Compose services
span more than one host. Either change ends the accepted risk above.
