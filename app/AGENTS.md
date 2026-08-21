# AGENTS.md — Backend Domain Standards (`app/`)

This document defines the architectural invariants, framework constraints, security rules, and code conventions for the Python backend (`app/`). All agents modifying backend code must adhere strictly to these rules.

---

## 1. Runtime & Environment Standards

- **Python Runtime**: Standardized on **Python 3.14** (`requires-python = ">=3.13,<3.15"`, `target-version = "py314"`).
- **Type Checking**: Strict `mypy` enforcement (`python_version = "3.14"`, `strict = true`) with plugins for `pydantic.mypy`, `sqlalchemy.ext.mypy.plugin`, and `strawberry.ext.mypy_plugin`. Code must also be compatible with `pyright` standard mode.
- **Linting & Formatting**:
  - `python -m ruff check app/`
  - `python -m ruff format app/`
  - Ruff version is pinned to `v0.14.14` (prevents `except` parentheses stripping regressions).
  - S104 / S105 are suppressed in test files only via `pyproject.toml` `per-file-ignores`.

---

## 2. SQLAlchemy 2.0 & Database Invariants

### 2.1. Mandatory `lazy="noload"` on Relationships (CI Gate MOD-30-01)
- **Invariant**: **ALL** relationship declarations in SQLAlchemy ORM models **MUST** explicitly specify `lazy="noload"`.
- **Rationale**: Implicit lazy loading in async SQLAlchemy triggers `MissingGreenlet` exceptions or unmonitored N+1 query storms.
- **Eager Loading Call Sites**: Endpoints and repositories requiring related entities must explicitly declare eager loading using `.options(selectinload(...))` or `.options(joinedload(...))`.
- **Exemptions**: Any legitimate exception to `lazy="noload"` must include the inline comment `# noload-exempt: <reason>`.

```python
# CORRECT
class Chat(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "chats"
    
    participants: Mapped[list[User]] = relationship(
        "User",
        secondary=chat_participants,
        backref="chats",
        lazy="noload",
    )

# FORBIDDEN (will be rejected by CI Gate MOD-30-01)
class Chat(Base, UUID7PrimaryKeyMixin):
    participants: Mapped[list[User]] = relationship("User", secondary=chat_participants)
```

### 2.2. Dual Default Declarations (Python Default + SQL Server Default)
- **Invariant**: Any model column with default values must provide **BOTH** Python-level default (`default=...`) AND DDL server default (`server_default=...`).
- **Rationale**: Freshly inserted ORM entities validated against Pydantic DTOs (`model_validate(from_attributes=True)`) will fail with `MissingGreenlet` if the Python-side attribute is unpopulated and requires a DB roundtrip to resolve.

```python
# CORRECT
chat_type: Mapped[str] = mapped_column(
    String(20),
    CheckConstraint("chat_type IN ('dm', 'group')", name="ck_chats_chat_type"),
    default="dm",
    server_default="dm",
    nullable=False,
)

# FORBIDDEN (lacks Python-side default -> triggers MissingGreenlet during validation)
chat_type: Mapped[str] = mapped_column(
    String(20),
    server_default="dm",
    nullable=False,
)
```

### 2.3. Models & Primary Keys
- Use `UUID7PrimaryKeyMixin` (`app/models/mixins.py`) for all new tables requiring time-ordered UUIDv7 identifiers.
- Dual foreign keys referencing the same target table must explicitly specify `foreign_keys=[...]`.
- SQLite test isolation: `_set_rls_user` must gracefully catch SQLite `OperationalError` during localized unit tests.

---

## 3. Dishka Dependency Injection & Narrow Services

### 3.1. Narrow Domain Providers (`app/core/di/`)
- DI containers are split into domain-scoped providers:
  - `AuthProvider` (`app/core/di/auth.py`)
  - `ChatProvider` (`app/core/di/chat.py`)
  - `ContentProvider` (`app/core/di/content.py`)
  - `CQRSProvider` (`app/core/di/cqrs.py`)
  - `InfrastructureProvider` (`app/core/di/infrastructure.py`)
  - `SearchProvider` (`app/core/di/search.py`)
  - `SpiceDBProvider` (`app/core/di/spicedb.py`)
  - `UserProvider` (`app/core/di/users.py`)
- **Monolithic Wrappers Forbidden**: Monolithic wrapper services (such as legacy ChatService wrappers) are strictly forbidden (TD-30-01).

### 3.2. Rule TD-33-08: NotificationService Exclusivity
- **Rule**: `NotificationService` is provided **ONLY** by `ContentProvider` (`app/core/di/content.py`).
- **AST Linter Enforcement**: `scripts/custom_ast_linter.py` validates all AST import nodes. Importing `NotificationService` from `app.deps.user`, or defining a duplicate provider in `users.py`, will immediately fail the CI build.

```python
# CORRECT
from app.deps.content import NotificationService

# FORBIDDEN (rejected by custom_ast_linter.py)
from app.deps.user import NotificationService
```

---

## 4. Exception Handling & Narrowing

### 4.1. Tuple Exception Syntax (Convention Enforced Since Wave 23)
- Always use the tuple form for multiple exception catches: `except (A, B):`.
- The deprecated Python 2 comma syntax `except A, B:` is strictly blocked by pre-commit gate `no-python2-except` (`scripts/check_no_python2_except.py`).

### 4.2. Narrowed Exception Domains (`# RZ-20-04` / `# RZ-22-01`)
Narrow all exception handling to specific error classes:
- **Database / Network**: `except (OSError, ConnectionError):`
- **File System Operations**: `except (FileNotFoundError, OSError):`
- **Redis Operations**: `except (ConnectionError, TimeoutError, OSError):`
- **PyO3 / Rust FFI**: `except (RuntimeError, ImportError, OSError):`
- **SMTP Operations**: `except (OSError, smtplib.SMTPException):`

### 4.3. Broad Exception Justification Tagging
- Catching broad `Exception` is strictly forbidden unless required for:
  1. Transaction cleanup before re-raising (`raise`).
  2. Domain exception conversion.
  3. Consumer handler NAKing.
  4. Fail-closed security/auth fallback.
- **Every** broad `except Exception` catch **MUST** be tagged with `# RZ-22-01-JUSTIFIED: <reason>`.

```python
# CORRECT
try:
    await self._redis.set(key, value, ex=ttl)
except (ConnectionError, TimeoutError, OSError) as err:  # RZ-22-01: Narrowed Redis error
    logger.warning("redis_cache_write_failed", error=str(err))

# CORRECT BROAD WITH JUSTIFICATION
try:
    await self._execute_critical_pipeline()
except Exception as err:  # RZ-22-01-JUSTIFIED: fail-closed auth fallback with audit log
    logger.error("auth_pipeline_unexpected_failure", error=str(err))
    raise AuthenticationFailedError("Internal authentication error") from err
```

---

## 5. Configuration & Redis Cache Separation

### 5.1. Namespace View Composition
- Access application settings through `@cached_property` namespace views on `settings`:
  - `settings.db`
  - `settings.security`
  - `settings.cache`
  - `settings.redis`
  - `settings.storage`
- Phase 2 implementation returns `_NamespaceView[T]` proxy objects instead of leaking monolithic `self`.

### 5.2. Redis Eviction Isolation (Cache vs. Revocation)
- **`CACHE_REDIS_URL`**: Used for application and query caching. Configured with `volatile-lru` eviction policy.
- **`REVOCATION_REDIS_URL`**: Used for JWT session and JTI revocation (`session:revocations`, `revoked:jti:*`).
- **CRITICAL INVARIANT**: `REVOCATION_REDIS_URL` **MUST** target an independent, persistent Redis instance configured with AOF persistence and `noeviction`. **NEVER** store revocation tokens in the eviction-enabled cache Redis.

### 5.3. Cache Decorator & Clustering
- The `@cached()` decorator forwards `_l1_ttl` parameter to the `TieredCache` in-memory L1 layer (TD-33-09).
- `RedisClusterCache.invalidate()` supports glob patterns via `SCAN` iteration (TD-33-10).
- Rate limiter uses `RedisCircuitBreaker` (`app/core/ratelimit/circuit_breaker.py`) with 3-state machine and exponential backoff (PERF-30-01).

---

## 6. Authentication, Security & Cryptography

### 6.1. Password Hashing (Argon2id Only)
- **Argon2id** is the sole password hashing algorithm (`argon2-cffi`).
- **Bcrypt Verification Removed**: Legacy bcrypt support has been completely excised (TD-21-04).
- **Concurrency Limiting**: Argon2 hashing operations are capped at a maximum of 4 concurrent operations per worker process.

### 6.2. Dual JWKS Architecture (RS256)
- Private RSA signing key: `.secrets/jwt_rs256.pem`.
- Outbound tokens: Signed using RS256 algorithm.
- `LoginSessionManager.finalize_login` injects claims: `sub`, `exp`, `aud`, and `role` (`user.role.value`).
- Dual JWKS Endpoints:
  - `/.well-known/jwks.json`: Public RSA JWKS (`kty=RSA`, `n`, `e`) for external and edge consumers.
  - `/api/v1/.well-known/jwks.json`: HMAC stub (`kty=oct`) for backward compatibility.
- Cookies: `access_token_v2` must be issued as an `HttpOnly` cookie with `cookie_samesite="lax"`.

### 6.3. Storage Path Traversal Prevention
- `StaticFSStorage._validate_resolved_path()` resolves symlinks and verifies `is_relative_to(base_dir)`.

---

## 7. Outbox Pattern & Event Publishing

- **Transactional Outbox**: Business mutations record domain events using `EventEmitterMixin` and `domain_events.py` within the active DB transaction.
- **Serialization**: Outbox payloads must be serialized using `orjson.dumps(payload, default=str)`.
- **NATS Publisher Guard**:
  ```python
  if self._nc is None or not self._nc.is_connected:
      logger.warning("nats_publish_skipped_not_connected")
      return
  ```

---

## 8. GraphQL Defense Layers

GraphQL queries (via Strawberry GraphQL) pass through 5 protective middleware layers:
1. **`QueryDepthLimiter`**: Rejects queries exceeding max depth of 10.
2. **`MaxTokensLimiter`**: Rejects queries with excessive token counts.
3. **`QueryCostExtension`**: Calculates query complexity and rejects expensive requests.
4. **`RequestTimeoutExtension`**: Hard 30s timeout per GraphQL request.
5. **`PersistedQueryExtension`**: Enforces pre-registered queries in production.

---

## 9. Chat & Real-Time Messaging Rules

- **Chat Types**: `Chat.chat_type` must be `'dm'` or `'group'` (enforced by DB check constraint).
- **Cache Invalidation**: Adding or removing participants must immediately invalidate `chat:{id}:participants` and user presence state.
- **Participant Authorization**: Removals allow owner-kick or self-leave only. Adding a participant uses check-then-insert.
- **Read Receipts**:
  - DMs: `Message.read_status`.
  - Groups: `ChatReadReceipt(chat_id, user_id, last_read_at)` with `group_unread_cte` (`sender_id != me`).
- **Reply Targets**: `send_message` must validate that `reply_to_message_id` belongs to the same chat, loads `selectinload(replied_to)`, and serializes `ReplyPreview.from_message(replied_to)`.
- **Message Deletion Tombstone**: Deleted messages set `content=""` while preserving metadata.

---

## 10. Backend Anti-Patterns Summary

| Anti-Pattern | Why It Is Forbidden | Correct Pattern |
|---|---|---|
| `relationship(..., lazy="select")` | Causes unmonitored N+1 queries and async MissingGreenlet | `relationship(..., lazy="noload")` + explicit `selectinload` |
| Column default without DDL `server_default` | Causes MissingGreenlet during Pydantic validation of new instances | Provide both `default=val` and `server_default=val` |
| `from app.deps.user import NotificationService` | Violates DI encapsulation rule TD-33-08 (AST linter fails) | `from app.deps.content import NotificationService` |
| `except Exception:` without tag | Swallows unexpected bugs and violates exception policy | Use narrowed exceptions or tag `# RZ-22-01-JUSTIFIED: <reason>` |
| `except A, B:` | Python 2 syntax rejected by `no-python2-except` hook | `except (A, B):` |
| Storing `revoked:jti:*` in cache Redis | Cache eviction (volatile-lru) can resurrect revoked tokens | Store exclusively in persistent `REVOCATION_REDIS_URL` |
| Bcrypt password hashing | Bcrypt removed in TD-21-04; violates security standards | Use Argon2id via `argon2-cffi` |
| Monolithic DI service wrappers | High coupling, slow tests, violates SRP | Narrow Dishka domain providers (`app/core/di/`) |
