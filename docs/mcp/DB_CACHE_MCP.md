# Database & Cache State Verification Guide (Postgres & Redis MCP)

## 1. Overview & Data Layer Architecture

The **University Ecosystem Platform** utilizes a resilient persistence and caching topology designed for high-concurrency academic operations:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Application Backend / Agent                                │
└──────────────────────────────┬───────────────────────────────┬──────────────────────────────┘
                               │                               │
                               ▼                               ▼
               ┌───────────────────────────────┐ ┌───────────────────────────────┐
               │         PostgreSQL 16+        │ │         Redis / Valkey        │
               │         (Port 15433)          │ │         (Port 63791)          │
               ├───────────────────────────────┤ ├───────────────────────────────┤
               │ • Multi-tenant RLS Policies   │ │ • L1 Memory + L2 Valkey Cache │
               │ • Alembic Migrations          │ │ • Session Revocations (JTI)   │
               │ • Foreign Key & Check Constr. │ │ • Cache Tag Invalidation      │
               │ • EXPLAIN ANALYZE Diagnostics │ │ • XFetch Probabilistic TTL    │
               └───────────────────────────────┘ └───────────────────────────────┘
```

- **Postgres MCP (`postgres`)**: Enables direct SQL query execution over port `15433` for schema migration validation, index scan efficiency analysis, and Row Level Security (RLS) enforcement.
- **Redis MCP (`redis`)**: Enables key-value inspection over port `63791` for verifying token revocation sets (`session:revocations`, `revoked:jti:*`), cache tag invalidation triggers, and memory eviction safety.

---

## 2. Postgres MCP Recipes & Diagnostics

### 2.1 Server Connection Specification
- **Host Port**: `15433`
- **Database**: `university`
- **Username**: `postgres`
- **Connection URI**: `postgresql://postgres:postgres@127.0.0.1:15433/university`
- **Tool**: `postgres/query` (`sql: string`)

---

### 2.2 Recipe 1: Alembic Schema Migration Head Verification

Verifies that the live database schema matches the expected Alembic revision head from `alembic/versions/`.

```json
{
  "ServerName": "postgres",
  "ToolName": "query",
  "Arguments": {
    "sql": "SELECT version_num FROM alembic_version LIMIT 1;"
  },
  "toolAction": "Query database",
  "toolSummary": "Verify Alembic migration head"
}
```

**Diagnostic Assertions**:
- Verify returned `version_num` matches the latest revision identifier in `alembic/versions/`.
- Verify no pending migrations with `python -m alembic check` or `python -m alembic heads`.

---

### 2.3 Recipe 2: `EXPLAIN (ANALYZE, BUFFERS)` Query Optimization

Analyzes execution plans for complex queries (e.g. Chat messages, Group unread counts, Schedule slot conflicts) to verify that queries utilize index scans instead of costly sequential table scans.

```json
{
  "ServerName": "postgres",
  "ToolName": "query",
  "Arguments": {
    "sql": "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT m.id, m.content, m.sender_id, m.created_at, m.read_status FROM messages m WHERE m.chat_id = '01912a7f-4f2b-7b29-8f3e-4b95f62c0192' ORDER BY m.created_at DESC LIMIT 50;"
  },
  "toolAction": "Analyze query plan",
  "toolSummary": "Verify index scan on chat messages"
}
```

**Diagnostic Assertions**:
- Confirm `Node Type` is `Index Scan` or `Bitmap Index Scan` (targeting `ix_messages_chat_id_created_at`).
- Verify `Total Cost` and `Execution Time` (< 5.0 ms).
- Ensure `Buffers: shared hit` is high and `shared read` is minimal.

---

### 2.4 Recipe 3: Row Level Security (RLS) Policy Audit

Asserts that Row Level Security policies are active and properly partition student and faculty tenant data.

```json
{
  "ServerName": "postgres",
  "ToolName": "query",
  "Arguments": {
    "sql": "SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual FROM pg_policies WHERE schemaname = 'public';"
  },
  "toolAction": "Audit RLS policies",
  "toolSummary": "Check active RLS policies in Postgres"
}
```

**Diagnostic Assertions**:
- Ensure all multi-tenant tables (`grades`, `student_submissions`, `personal_schedules`) declare active RLS policies.
- Verify `cmd` covers `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.

---

### 2.5 Recipe 4: Constraint & Relationship Integrity Validation

Validates database constraints (e.g. `CheckConstraint("chat_type IN ('dm', 'group')")`) and foreign key relationships.

```json
{
  "ServerName": "postgres",
  "ToolName": "query",
  "Arguments": {
    "sql": "SELECT conname, contype, pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'public' AND conrelid::regclass::text IN ('chats', 'messages', 'users');"
  },
  "toolAction": "Check constraints",
  "toolSummary": "Verify DB check constraints and foreign keys"
}
```

---

## 3. Redis / Valkey MCP Recipes & Diagnostics

### 3.1 Server Connection Specification
- **Host Port**: `63791`
- **Connection URI**: `redis://:nViPWOrh7FhdYOE2gdhFBjJa@127.0.0.1:63791`
- **Tools**:
  - `redis/get` (`key: string`)
  - `redis/set` (`key: string`, `value: string`, `expire?: number`)
  - `redis/delete` (`key: string`)
  - `redis/list` (`pattern?: string`)

---

### 3.2 Recipe 1: Session Revocation & JTI Blacklist Verification

Validates that user compliance and logout actions correctly publish revocation identifiers to the Redis store (`session:revocations` and `revoked:jti:*`).

```json
// Step 1: List all active revocation keys
{
  "ServerName": "redis",
  "ToolName": "list",
  "Arguments": {
    "pattern": "revoked:jti:*"
  },
  "toolAction": "List keys",
  "toolSummary": "Inspect revoked JWT identifiers"
}

// Step 2: Get specific revocation record
{
  "ServerName": "redis",
  "ToolName": "get",
  "Arguments": {
    "key": "revoked:jti:01912a80-112a-7c9b-b6d4-839201948572"
  },
  "toolAction": "Get key",
  "toolSummary": "Verify revocation timestamp and user ID"
}
```

**Architecture Invariant**:
- Revocation keys MUST target an AOF-backed, persistent `noeviction` Redis process (`REVOCATION_REDIS_URL`).
- Application cache uses `volatile-lru`. Never store `revoked:jti:*` in the eviction-enabled cache.

---

### 3.3 Recipe 2: Cache Tag Invalidation (`@invalidates_cache`)

Tests that modifying an event correctly purges corresponding tagged keys (e.g. `cache:events:*`) via the cache invalidation decorator.

```json
// Step 1: Verify cached event list before update
{
  "ServerName": "redis",
  "ToolName": "list",
  "Arguments": {
    "pattern": "cache:events:*"
  },
  "toolAction": "List keys",
  "toolSummary": "Inspect active event cache keys"
}

// Step 2: Manually check cache hit content
{
  "ServerName": "redis",
  "ToolName": "get",
  "Arguments": {
    "key": "cache:events:dept_cs_2026"
  },
  "toolAction": "Get cache value",
  "toolSummary": "Inspect cached JSON payload"
}
```

---

### 3.4 Recipe 3: Cache Stampede & XFetch Probabilistic TTL Audit

Validates key TTLs and ensures TieredCache L1/L2 coherence using the XFetch probabilistic refresh algorithm (`shouldRefreshProbabilistic()`).

```json
// Step 1: List cache keys under academic schedule domain
{
  "ServerName": "redis",
  "ToolName": "list",
  "Arguments": {
    "pattern": "cache:schedule:*"
  },
  "toolAction": "List keys",
  "toolSummary": "List schedule cache entries"
}

// Step 2: Inspect key TTL and payload structure
{
  "ServerName": "redis",
  "ToolName": "get",
  "Arguments": {
    "key": "cache:schedule:group_cs401"
  },
  "toolAction": "Inspect key",
  "toolSummary": "Verify payload timestamp and computed delta"
}
```

---

## 4. Subsystem Gotchas & Verification Checklist

1. **SQLAlchemy Relationship Lazy Invariant**:
   - ALL relationships must declare explicit `lazy="noload"` (e.g. `relationship("User", lazy="noload")`) to prevent silent N+1 queries.
2. **Dual FK Specifications**:
   - Tables with multiple foreign keys to the same target (e.g. `Chat.owner_id` and `Chat.created_by_id`) must explicitly declare `foreign_keys=[...]` on relationships.
3. **Argon2id Only (No Bcrypt)**:
   - Password hashes in the database must begin with `$argon2id$`. Bcrypt verification has been completely removed.
4. **Redis SCAN vs KEYS**:
   - Key enumeration in production uses non-blocking `SCAN` iteration (via `RedisClusterCache.invalidate()`) rather than blocking `KEYS *`.
