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

## Addendum 2026-11-12: AUD-189 public TCP/443 egress exception (Helm profile)

Scope: the Helm chart's `networkPolicy.httpsEgress` rules, which apply only to the
`backend` and `backup` workloads. Each may open TCP/443 to public IPv4 and IPv6
destinations, excluding RFC 1918 private ranges, carrier-grade NAT (100.64.0.0/10),
and link-local ranges (`169.254.0.0/16`, `fe80::/10`) plus `fc00::/7`. Every other workload
keeps its explicit allow-list and gets no public TCP/443 egress. The exception does
not apply to the Compose target described above.

Reason: the owner accepted the residual AUD-189 risk for the backend's declared
public dependencies (HIBP password checks, Spotify OAuth, and object storage) and
for the backup job's object-storage upload. A FQDN or proxy allow-list cannot be
enforced by a standard NetworkPolicy, so the destination set stays broad.

Evidence: the kind runtime proof (`scripts/k8s/networkpolicy_runtime_proof.sh`)
must show that backend reaches a public TCP/443 control, and that every other
probed workload is denied the same destination. The exception does not count as
proof of any specific provider.

Revisit: after MVP, replace the broad public range with an egress proxy or an
FQDN-aware policy (for example, Cilium FQDN rules or a dedicated egress gateway),
then remove this addendum.

## Addendum 2026-11-13: notifications-worker public egress for Web Push

Finding: `notifications-worker` sends Web Push itself (`app/workers/notifications.py`
through `app.services.webpush`). On the full local and live stand
(`docker-compose.full.yml`, plus `docker-compose.live.yml`) it was attached only to
the internal `internal` network. From that container `fcm.googleapis.com` did not
resolve, while `backend`, which is on `public`, reached it. Push deliveries
therefore never left the live stand. The MVP base (`docker-compose.yml` with the
production overlay) already attaches the worker to `public`.

Decision (owner, 2026-11-13): `notifications-worker` gets public egress in every
Compose topology. `docker-compose.full.yml` now also attaches it to `public`, so the
live stand matches the MVP base. The worker still publishes no host port, and its
monitoring endpoint stays on the internal network for Prometheus.

Reason and accepted risk: browser push services (FCM, Mozilla autopush, Apple, WNS)
have no fixed address set, so the worker needs broad outbound HTTPS, the same
posture as `backend`. The Helm chart has no notifications-worker workload today,
so the AUD-189 Helm egress exception above is unchanged.

Revisit: after MVP, move push egress behind an egress proxy or an FQDN-aware
policy together with the AUD-189 follow-up.
