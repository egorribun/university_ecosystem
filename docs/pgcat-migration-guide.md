# pgcat Migration Guide

> MOD-21-07 (audit 2026-03-25 Wave 21)

## Why pgcat?

PgBouncer in transaction mode does not support prepared statements, forcing
`DATABASE_STATEMENT_CACHE_SIZE=0` in our configuration. This means every query
requires a full parse+plan cycle, adding ~10-20% overhead on hot paths.

**pgcat** (Rust-based) supports prepared statements in transaction mode, recovering
this overhead while maintaining connection pooling.

## Current State

```
Client → PgBouncer (transaction mode) → PostgreSQL
         statement_cache_size=0 (no prepared statements)
```

## Target State

```
Client → pgcat (transaction mode) → PostgreSQL
         statement_cache_size=1024 (prepared statements enabled)
```

## Prerequisites

- [ ] Benchmark current query latency (p50, p95, p99) with PgBouncer
- [ ] Test pgcat in staging environment for 1 week
- [ ] Verify all SQLAlchemy query patterns work with pgcat
- [ ] Confirm asyncpg compatibility with pgcat

## Migration Steps

### 1. Install pgcat

```bash
# Docker
docker pull ghcr.io/postgresml/pgcat:latest

# Or build from source
cargo install pgcat
```

### 2. Configure pgcat

Create `pgcat.toml`:

```toml
[general]
host = "0.0.0.0"
port = 6432
connect_timeout = 5000
idle_timeout = 30000
server_lifetime = 3600000
idle_client_in_transaction_timeout = 30000

[pools.university_ecosystem]
pool_mode = "transaction"
default_role = "primary"
prepared_statements = true     # KEY: enabled in transaction mode
query_parser_enabled = true
query_parser_max_length = 1024

[pools.university_ecosystem.shards.0]
servers = [["postgres", 5432, "primary"]]
database = "university_ecosystem"

[pools.university_ecosystem.users.0]
username = "app_user"
password = "from_env"  # pragma: allowlist secret
pool_size = 20
max_pool_size = 40
```

### 3. Update Application Config

```bash
# In .env or K8s secrets:
DATABASE_STATEMENT_CACHE_SIZE=1024    # Was 0 with PgBouncer
DATABASE_POOL_SIZE=10                  # Reduce — pgcat handles pooling
DATABASE_MAX_OVERFLOW=5                # Reduce — pgcat handles overflow
```

### 4. Update docker-compose.yml

Replace the PgBouncer service (if present) with pgcat:

```yaml
pgcat:
  image: ghcr.io/postgresml/pgcat:latest
  volumes:
    - ./pgcat.toml:/etc/pgcat/pgcat.toml:ro
  ports:
    - "6432:6432"
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - db_net
```

### 5. Update Kubernetes

Update the Helm values to deploy pgcat instead of PgBouncer.

### 6. Benchmark & Verify

```bash
# Compare query latency before/after
pgbench -c 20 -j 4 -T 60 -h pgcat-host -p 6432 university_ecosystem

# Verify prepared statements are being used
# Check pgcat admin: SHOW SERVERS; SHOW POOLS;
```

## Expected Improvements

| Metric | PgBouncer | pgcat | Improvement |
|--------|-----------|-------|-------------|
| Parse overhead | ~15% of query time | ~0% (cached) | 10-20% faster |
| Memory | ~50MB | ~30MB (Rust) | 40% less |
| Prepared stmts | Not supported | Supported | New capability |
| Connection reuse | Good | Good | Equivalent |

## Rollback Plan

1. Revert `DATABASE_STATEMENT_CACHE_SIZE` to `0`
2. Switch connection string back to PgBouncer
3. Restart application pods

## Risks

- pgcat is newer than PgBouncer — less battle-tested in production
- Some edge cases with savepoint handling in transaction mode
- Monitor pgcat metrics closely for the first 2 weeks
