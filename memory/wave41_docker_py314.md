---
name: Wave 41 — Python 3.14 compat + Docker env fixes
description: Pydantic/Strawberry/redis-py upgrades for Python 3.14, Docker compose env alignment, SpiceDB setup
type: project
---

## Wave 41 (2026-03-29) — Python 3.14 Docker Startup

### Problem
Backend failed to start on Python 3.14 with three separate `Field.__init__() missing 'doc'` and recursion errors.

### Python 3.14 Compatibility Fixes (FIX-41-01/02/03)
| Package | Old | New | Issue |
|---------|-----|-----|-------|
| pydantic | 2.12.5 | 2.13.0b2 | `Field.__init__(doc=)` — PEP 749 added `doc` param to dataclasses |
| strawberry-graphql | 0.282.0 | 0.312.2 | Same `doc` param in `StrawberryField.__init__()` — fix in 0.283.2 |
| redis-py | 5.3.1 | 7.4.0 | `check_health` ↔ `connect` mutual recursion on Python 3.14 |

**Why:** Python 3.14 (PEP 749) changed `dataclasses.Field.__init__()` signature — `doc` is now required.
**How to apply:** When upgrading Python minor versions, check all libs that subclass `dataclasses.Field`.

### Docker Compose Env Fixes
- **Dual env file problem**: `.env` (compose interpolation) vs `.env.docker` (container env_file) had different passwords
- **`!` in passwords**: shell history expansion mangles `!` to `/!` inside Docker containers — never use `!` in compose-interpolated passwords
- **Redis auth**: `CACHE_REDIS_URL` and `RATE_LIMIT_STORAGE_URI` now include `${REDIS_PASSWORD}` in the URL
- **Redis healthcheck**: uses `-a ${REDIS_PASSWORD} --no-auth-warning` flag
- **SpiceDB**: added `SPICEDB_ENDPOINT=spicedb:50051` + `SPICEDB_INSECURE=true` for dev compose
- **SpiceDB DB**: fresh postgres volumes need `CREATE DATABASE spicedb` + `spicedb migrate head`

### Test User
- email: `test@university.dev`, password: `TestPass@2024x`, role: student <!-- pragma: allowlist secret -->

### Image Cleanup
- Removed 15 old/duplicate Docker images (~3.5GB): old caddy, imgproxy, grafana, loki, tempo, nats, prometheus, temporal tags + unused trivy, trufflehog, pyroscope, valkey, alpine

### Commits
- `3fba77a3e` feat(wave35-41): frontend polish + all waves 35-41
- `79c7848ae` fix(wave41): pydantic 2.13.0b2, strawberry >=0.283.2, redis >=6
- `902bf2fe4` fix(wave41): Docker Redis auth + SpiceDB insecure + password escaping
