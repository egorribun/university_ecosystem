# ADR-011: PgBouncer in Transaction-Mode Pooling

## Status
Accepted (MOD-W14-06, 2026-03-18)

## Context

The Python backend uses SQLAlchemy 2.0 asyncio with `asyncpg`. Without connection pooling at the infrastructure level, each uvicorn worker maintains its own connection pool to PostgreSQL. Under load:

- 4 workers × 20 connections = 80 server-side PostgreSQL connections
- At 10 replicas: 800 connections — approaching PostgreSQL's `max_connections` default (100)
- Each PostgreSQL connection consumes ~5-10 MB of server RAM

The existing `pool_timeout=30s` in `app/core/database.py` mitigates worker-level exhaustion but does nothing for PostgreSQL server-side connection pressure.

## Decision

Deploy the maintained **edoburu/pgbouncer v1.25.2-p0** image in **transaction-mode pooling** between the application tier and PostgreSQL:

- `POOL_MODE=transaction` — each transaction gets a server connection; connection released immediately after `COMMIT`/`ROLLBACK`
- `MAX_CLIENT_CONN=1000` — supports burst of up to 1000 application connections
- `DEFAULT_POOL_SIZE=25` — at most 25 server-side PostgreSQL connections regardless of application replica count
- `AUTH_TYPE=scram-sha-256` — client authentication uses SCRAM; the generated userlist lives only on a container tmpfs
- `SERVER_TLS_SSLMODE=prefer` — works with the Compose-managed PostgreSQL instance and negotiates TLS when the upstream database offers it; real production deployments with a TLS-only external database should override this to `require`

**Application URL change:** `DATABASE_URL_FILE` must contain `host=pgbouncer` and port `5432` (not `postgres`) so connections route through the pooler.

## Transaction Mode Constraints

Transaction mode is incompatible with:
- `SET` / `RESET` statements outside a transaction (session-level state)
- `LISTEN` / `NOTIFY` (requires persistent connection)
- Prepared statements (disabled via `server_reset_query`)
- `SELECT pg_advisory_lock()` — advisory locks require a session connection

These patterns are not used in the current codebase; must be enforced via code review for future additions.

## Consequences

**Positive:**
- PostgreSQL server connection count capped at 25 regardless of replica count.
- Burst traffic no longer exhausts PostgreSQL `max_connections`.
- The PostgreSQL password is supplied by a Compose file secret and is absent from Compose environment metadata.

**Negative:**
- Session-level state (`SET LOCAL` used by RLS) must be within a transaction — already the case for RLS via SQLAlchemy session context.
- `LISTEN`/`NOTIFY` cannot use the pooled connection; would need a dedicated non-pooled connection.
- Additional infrastructure component to operate and monitor.

## Implementation

- `docker-compose.prod.yml` — PgBouncer service with pinned image, file-backed password, tmpfs-generated configuration, healthcheck, and migration dependency
- `k8s/backend/` — PgBouncer deployment and service (if running in K8s)
- `app/core/database.py` — `pool_timeout=30s`, `pool_size` tuned for post-bouncer throughput
