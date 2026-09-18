# ADR-037: CDC Outbox Transport Ownership and Lifecycle Boundary

## Status

Accepted — deferred until the integration gates below are complete.

## Date

2026-09-10

## Context

The repository contains two outbox transport implementations:

1. `app/workers/outbox.py` is the production polling/LISTEN-NOTIFY worker. It
   is the only outbox worker provided by Dishka and the only worker started by
   `app/core/lifespan.py`.
2. `app/workers/cdc_outbox.py` contains a PostgreSQL logical-replication
   (`pgoutput`) implementation. It is covered by hermetic decoder and dispatch
   tests, but it has no settings flag, Dishka provider, application-lifespan
   task, replication preflight, or production deployment owner.

Starting both transports would create two independent consumers of
`stored_events`. JetStream message IDs may suppress some duplicate publishes,
but that does not prove ordering, retry ownership, acknowledgement semantics or
replay safety. The CDC fallback currently creates an `OutboxWorker` internally,
which would be especially unsafe if an embedded polling worker were also
enabled.

Logical replication also has resources and privileges that the polling path
does not: a publication, a durable replication slot, replication-capable
credentials, slot-retention monitoring and an operator rollback procedure.
The replication stream uses asyncpg's private `_copy_out` API, so graceful
shutdown must explicitly own and close the active connection.

## Decision

The polling/LISTEN-NOTIFY `OutboxWorker` remains the sole default and sole
application-lifespan transport. CDC is not enabled by an undocumented or legacy
environment variable, and no second consumer is started.

The CDC implementation may be hardened and tested in isolation, but it is not
considered production-integrated until the acceptance contract below is met.
The lifecycle boundary for the current implementation is explicit:

- the active replication connection is retained by `CdcOutboxWorker` and
  closed exactly once during `stop()` or stream teardown;
- a connection that completes after shutdown is never used to start a WAL
  stream;
- a fallback worker is retained as a child resource and receives `stop()` from
  its parent, preventing a detached fallback task.

These safeguards reduce lifecycle risk without changing the current transport
selection or silently changing delivery semantics.

## Required acceptance contract before wiring CDC

Any future CDC enablement must be a separate, reviewable implementation slice
and satisfy all of the following:

1. Add an explicit `cdc_outbox_enabled`/transport setting defaulting to false;
   reject simultaneous polling and CDC ownership at configuration validation
   time. The setting must be documented in Compose, Helm and operator runbooks.
2. Provide exactly one APP-scoped transport through Dishka and start exactly
   one worker in the application lifecycle. The lifecycle must use structured
   task ownership and stop the worker before closing its dependencies.
3. Replace private-stream lifecycle assumptions with an explicit connection
   ownership/cancellation contract, including startup/stop races, reconnect,
   publication/slot loss and process cancellation. No fallback may create an
   unowned or second polling worker.
4. Define and test idempotency, ordering, replay and acknowledgement behavior
   across CDC, polling, NATS outage, malformed WAL, restart and duplicate
   delivery. JetStream deduplication alone is not sufficient evidence.
5. Add PostgreSQL preflight and integration coverage for logical replication
   privileges, publication and slot ownership, slot retention, upgrade,
   downgrade and operator remediation. Add readiness, lag and ownership
   metrics with actionable alerts.
6. Run async cancellation/race tests plus PostgreSQL/NATS integration tests and
   current-SHA staging smoke before promoting CDC from deferred to enabled.

## Consequences

### Positive

- The deployed platform has one unambiguous outbox owner and preserves the
  already-tested at-least-once polling semantics.
- No logical replication slot or publication is created by an ordinary API
  startup, avoiding unbounded WAL retention and privilege surprises.
- CDC code can continue to receive focused protocol/lifecycle tests without
  being mistaken for a production transport.

### Negative

- CDC's lower-latency path is not available in the MVP application process.
- A future enablement requires real PostgreSQL/NATS integration and deployment
  evidence rather than only unit tests.

## Verification

The current boundary is protected by:

- `tests/test_outbox_closure.py`, which verifies the legacy
  `ENABLE_CDC_OUTBOX` variable does not instantiate CDC;
- `tests/test_cdc_outbox.py` and `tests/test_cdc_outbox_closure.py`, which
  cover decoding, dispatch, fallback and lifecycle stop behavior;
- `app/core/lifespan.py` and `app/core/di/infrastructure.py`, which show the
  sole production worker wiring;
- `docs/audits/AUDIT_BE_DEFAULTS_CDC_2026-09-08.md`, which records the full
  lifecycle graph and the required integration evidence.

The focused CDC suite must remain green on every current-SHA certification;
green hermetic tests do not substitute for the integration gates above.

## Related decisions and audits

- [ADR-003: Background Jobs](ADR-003-background-jobs.md)
- [ADR-004: Notification System](ADR-004-notification-system.md)
- [ADR-022: Go Services Integration Testing with Testcontainers](ADR-022-go-services-integration-testing-with-testcontainers.md)
- [`AUDIT_BE_DEFAULTS_CDC_2026-09-08.md`](../audits/AUDIT_BE_DEFAULTS_CDC_2026-09-08.md)
- `AUDIT_PLATFORM_FULL.md`, Finding BE-08 (user-owned untracked audit)
