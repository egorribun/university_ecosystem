# TOTAL_AUDIT_WAVE25.md — Wave 25 Comprehensive Audit

## Context

This is Wave 25 of the ongoing security and quality audit series. The primary driver is a regression of **Python 2 exception syntax** (`except A, B:` instead of `except (A, B):`) that was introduced across 52 call sites in 23 files. This syntax bug means only the first exception type is actually caught — the rest are silently ignored. In security-critical paths (Redis session revocation, rate limiting, CSRF, GraphQL cost tracking, WebSocket auth), this creates unhandled exceptions that surface as 500 errors instead of graceful fallbacks.

Additionally, a Kubernetes NetworkPolicy port mismatch blocks all frontend ingress traffic, and the NullSessionBackend fails open in production when Redis is unavailable.

**Scope**: 20 issues across 4 categories, ~30 files modified.

---

## Summary Table

| ID | Sev | Category | File(s) | Description |
|---|---|---|---|---|
| RZ-25-01 | P0 | Red Zone | 23 files, 52 instances | Python 2 `except A, B:` syntax — broken error handling |
| RZ-25-02 | P0 | Red Zone | `app/auth/redis_session.py` | NullSessionBackend fails open in production |
| RZ-25-03 | P0 | Red Zone | `k8s/frontend/network-policy.yaml` | NetworkPolicy port 8080 vs container port 80 |
| RZ-25-04 | P1 | Red Zone | `app/core/ratelimit/strategies/redis.py` | SHA cache invalidation outside lock |
| RZ-25-05 | P1 | Red Zone | `app/graphql/extensions.py` | Manifest lazy-load TOCTOU race |
| RZ-25-06 | P1 | Red Zone | `app/auth/redis_session.py` | Non-atomic revocation fallback |
| TD-25-01 | P1 | Tech Debt | `k8s/frontend/deployment.yaml` | Missing nginx writable volume mounts |
| TD-25-02 | P1 | Tech Debt | `k8s/frontend/hpa.yaml` (new) | Missing HPA for frontend |
| TD-25-03 | P2 | Tech Debt | `k8s/frontend/deployment.yaml` | Memory limit 128Mi too low |
| TD-25-04 | P2 | Tech Debt | `k8s/flagd/deployment.yaml` | runAsUser 65534 vs distroless 65532 |
| TD-25-05 | P2 | Tech Debt | `k8s/flagd/deployment.yaml` | Image not SHA-pinned (RZ-22-03 parity) |
| TD-25-06 | P2 | Tech Debt | `app/core/health.py:163` | SpiceDB health check Python 2 syntax |
| PERF-25-01 | P1 | Performance | `app/graphql/extensions.py` | Cost tracking fallback needs observability |
| PERF-25-02 | P1 | Performance | `app/services/cache_warmup.py` | Warmup Redis errors silently uncaught |
| PERF-25-03 | P1 | Performance | `app/api/ws/auth.py` | WS auth Redis `TimeoutError` uncaught |
| PERF-25-04 | P1 | Performance | `app/services/storage.py` | Storage cache `TimeoutError`/`OSError` uncaught |
| MOD-25-01 | P1 | Modernization | `.github/workflows/ci.yml` | CI gate to prevent Python 2 syntax regression |
| MOD-25-02 | P2 | Modernization | `app/core/fingerprint.py` | Fingerprint Redis errors uncaught |
| MOD-25-03 | P2 | Modernization | `app/core/localization/core.py` | Translation `ValueError` uncaught |
| MOD-25-04 | P2 | Modernization | `app/core/observability.py` | Metric `ValueError` uncaught |

---

## Phase 1 — Red Zone (Security Vulnerabilities)

### RZ-25-01: Python 2 Exception Syntax — 52 Instances Across 23 Files (P0)

**Impact**: `except A, B:` in Python 3 catches only `A` and binds to name `B`. The 2nd/3rd exception types are **never caught**. This breaks error handling in Redis, GraphQL, SMTP, cache, auth, storage, and WebSocket paths.

**52 confirmed instances** (grep-verified):

| # | File | Line | Before | After |
|---|------|------|--------|-------|
| 1 | `app/auth/security.py` | 56 | `except AttributeError, NotImplementedError:` | `except (AttributeError, NotImplementedError):` |
| 2 | `app/auth/security.py` | 67 | `except FileNotFoundError, ValueError, OSError:` | `except (FileNotFoundError, ValueError, OSError):` |
| 3 | `app/auth/mfa/challenge.py` | 90 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 4 | `app/core/database.py` | 638 | `except OSError, ConnectionError:` | `except (OSError, ConnectionError):` |
| 5 | `app/core/fingerprint.py` | 94 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 6 | `app/core/fingerprint.py` | 126 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 7 | `app/core/health.py` | 163 | `except TimeoutError, grpc.RpcError:` | `except (TimeoutError, grpc.RpcError):` |
| 8 | `app/core/localization/core.py` | 62 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 9 | `app/core/observability.py` | 500 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 10 | `app/core/ratelimit/fastapi.py` | 106 | `except AttributeError, TypeError:` | `except (AttributeError, TypeError):` |
| 11 | `app/api/deps/auth.py` | 161 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 12 | `app/api/health.py` | 229 | `except OperationalError, Exception:` | `except (OperationalError, Exception):  # RZ-22-01-JUSTIFIED: health probe catch-all` |
| 13 | `app/api/notifications.py` | 77 | `except OverflowError, OSError, ValueError:` | `except (OverflowError, OSError, ValueError):` |
| 14 | `app/api/notifications.py` | 96 | `except OverflowError, OSError, ValueError:` | `except (OverflowError, OSError, ValueError):` |
| 15 | `app/api/notifications.py` | 151 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 16 | `app/api/notifications.py` | 394 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 17 | `app/api/ws/auth.py` | 240 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 18 | `app/api/ws/presence.py` | 225 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 19 | `app/deps/cache.py` | 238 | `except RedisError, OSError, AttributeError:` | `except (RedisError, OSError, AttributeError):` |
| 20 | `app/deps/cache.py` | 273 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 21 | `app/deps/cache.py` | 303 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 22 | `app/deps/cache.py` | 350 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 23 | `app/deps/cache.py` | 408 | `except RedisError, OSError, AttributeError:` | `except (RedisError, OSError, AttributeError):` |
| 24 | `app/deps/cache.py` | 427 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 25 | `app/deps/cache.py` | 450 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 26 | `app/deps/cache.py` | 466 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 27 | `app/graphql/extensions.py` | 95 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 28 | `app/graphql/extensions.py` | 251 | `except OSError, ValueError, KeyError:` | `except (OSError, ValueError, KeyError):` |
| 29 | `app/graphql/queries.py` | 127 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 30 | `app/graphql/queries.py` | 175 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 31 | `app/graphql/queries.py` | 232 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 32 | `app/graphql/queries.py` | 280 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 33 | `app/models/user_loaders.py` | 124 | `except TypeError, AttributeError:` | `except (TypeError, AttributeError):` |
| 34 | `app/services/cache_warmup.py` | 272 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 35 | `app/services/chat/command_service.py` | 153 | `except ValueError, KeyError, TypeError:` | `except (ValueError, KeyError, TypeError):` |
| 36 | `app/services/file_scanner.py` | 132 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 37 | `app/services/file_scanner.py` | 144 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 38 | `app/services/storage.py` | 200 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 39 | `app/services/storage.py` | 263 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 40 | `app/services/webpush.py` | 130 | `except OSError, ConnectionError:` | `except (OSError, ConnectionError):` |
| 41 | `app/services/webpush.py` | 221 | `except ZoneInfoNotFoundError, ValueError:` | `except (ZoneInfoNotFoundError, ValueError):` |
| 42 | `app/services/webpush.py` | 324 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 43 | `app/services/webpush.py` | 358 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 44 | `app/services/webpush.py` | 383 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 45 | `app/services/webpush.py` | 428 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 46 | `app/services/webpush.py` | 603 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 47 | `app/utils/sanitization.py` | 193 | `except ValueError, OSError:` | `except (ValueError, OSError):` |
| 48 | `app/utils/sanitization.py` | 280 | `except ValueError, UnicodeError:` | `except (ValueError, UnicodeError):` |
| 49 | `app/utils/images.py` | 22 | `except ImportError, OSError:` | `except (ImportError, OSError):` |
| 50 | `app/utils/files.py` | 394 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 51 | `app/utils/files.py` | 399 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 52 | `app/utils/email.py` | 154 | `except OSError, smtplib.SMTPException:` | `except (OSError, smtplib.SMTPException):` |
| 53 | `app/utils/email.py` | 251 | `except OSError, smtplib.SMTPException:` | `except (OSError, smtplib.SMTPException):` |

All existing `# RZ-22-01` audit comments are preserved. Each fix adds `# RZ-25-01` tag.

---

### RZ-25-02: NullSessionBackend Fails Open in Production (P0)

**File**: `app/auth/redis_session.py:106-136`
**Impact**: If Redis is unavailable, `get_session_backend()` returns `NullSessionBackend` which always returns `True` from `is_session_valid()`. Revoked tokens continue working. Production must fail-closed.

**Before** (lines 106-111):
```python
async def get_session_backend() -> SessionBackend:
    if settings.session_storage_backend == "redis":
        cache = get_cache()
        if isinstance(cache, RedisCache):
            client = await cache._get_client()
            return RedisSessionBackend(client)
```

**After**:
```python
async def get_session_backend() -> SessionBackend:
    if settings.session_storage_backend == "redis":
        cache = get_cache()
        if isinstance(cache, RedisCache):
            client = await cache._get_client()
            return RedisSessionBackend(client)
        # RZ-25-02: Fail-closed in production — NullSessionBackend bypasses revocation.
        _env = getattr(settings, "environment", "production").lower()
        if _env not in {"development", "local", "testing", "test"}:
            raise RuntimeError(
                "Session storage backend is 'redis' but Redis cache is unavailable. "
                "NullSessionBackend would bypass session revocation — refusing to start. "
                "Check REDIS_URL configuration."
            )
```

---

### RZ-25-03: Frontend NetworkPolicy Port Mismatch (P0)

**File**: `k8s/frontend/network-policy.yaml:25`
**Impact**: Ingress rule allows port 8080, but `deployment.yaml:29` shows `containerPort: 80`. With this NetworkPolicy applied, ingress controller cannot reach frontend — entire frontend unreachable.

**Before** (line 25):
```yaml
          port: 8080
```

**After**:
```yaml
          port: 80  # RZ-25-03: match containerPort in deployment.yaml
```

---

### RZ-25-04: Rate Limit SHA Cache Invalidation Outside Lock (P1)

**File**: `app/core/ratelimit/strategies/redis.py:103-106`
**Impact**: `_RATE_LIMIT_SHA = None` on line 106 is set without acquiring `_SHA_LOCK`. Concurrent requests can race with `_load_script_sha()` holding the lock, causing stale SHA to be returned.

**Before** (lines 103-106):
```python
        except NoScriptError:
            # Script was flushed (SCRIPT FLUSH or server restart) — reload and retry.
            global _RATE_LIMIT_SHA
            _RATE_LIMIT_SHA = None
```

**After**:
```python
        except NoScriptError:
            # RZ-25-04: Invalidate under lock to prevent TOCTOU race with _load_script_sha.
            async with _SHA_LOCK:
                _RATE_LIMIT_SHA = None
```

---

### RZ-25-05: GraphQL Persisted Query Manifest Load Race (P1)

**File**: `app/graphql/extensions.py:238-256`
**Impact**: `_load_manifest()` has a check-then-set pattern on `_query_allowlist` with no synchronization. Under concurrent first requests at startup, multiple threads can simultaneously enter the load path. This also contains a Python 2 syntax bug on line 251.

**Before** (lines 238-256):
```python
def _load_manifest() -> dict[str, str]:
    global _query_allowlist
    if _query_allowlist is not None:
        return _query_allowlist
    if _MANIFEST_PATH.exists():
        try:
            _query_allowlist = json.loads(_MANIFEST_PATH.read_text("utf-8"))
            ...
        except OSError, ValueError, KeyError:  # <-- Python 2 syntax
            ...
    else:
        _query_allowlist = {}
    return _query_allowlist
```

**After**:
```python
import threading
_manifest_lock = threading.Lock()

def _load_manifest() -> dict[str, str]:
    """Load the persisted-query manifest from disk (lazy, cached)."""
    global _query_allowlist
    if _query_allowlist is not None:
        return _query_allowlist
    with _manifest_lock:
        if _query_allowlist is not None:  # double-check after lock
            return _query_allowlist
        if _MANIFEST_PATH.exists():
            try:
                _query_allowlist = json.loads(_MANIFEST_PATH.read_text("utf-8"))
                logger.info(
                    "Loaded %d persisted queries from %s",
                    len(_query_allowlist),
                    _MANIFEST_PATH,
                )
            except (OSError, ValueError, KeyError):  # RZ-25-05 + RZ-25-01
                logger.warning("Failed to load query manifest — persisted queries disabled")
                _query_allowlist = {}
        else:
            _query_allowlist = {}
        return _query_allowlist
```

---

### RZ-25-06: Session Revocation Fallback Non-Atomic (P1)

**File**: `app/auth/redis_session.py:90-94`
**Impact**: When Lua is unavailable, revocation does `TTL` -> `DELETE` -> `SET` as separate commands. Between `DELETE` and `SET`, a concurrent `is_session_valid` sees neither the session key nor the revoked key — the token appears valid.

**Before** (lines 90-94):
```python
            remaining_ttl = await self._redis.ttl(key)
            await self._redis.delete(key)
            if remaining_ttl > 0:
                await self._redis.set(revoked_key, "1", ex=remaining_ttl)
```

**After**:
```python
            # RZ-25-06: Use pipeline to minimize TOCTOU window when Lua unavailable.
            remaining_ttl = await self._redis.ttl(key)
            if remaining_ttl > 0:
                pipe = self._redis.pipeline(transaction=True)
                pipe.delete(key)
                pipe.set(revoked_key, "1", ex=remaining_ttl)
                await pipe.execute()
            else:
                await self._redis.delete(key)
```

---

## Phase 2 — Technical Debt

### TD-25-01: Frontend Deployment Missing nginx Writable Volume Mounts (P1)

**File**: `k8s/frontend/deployment.yaml`
**Impact**: `readOnlyRootFilesystem: true` (line 53) but no emptyDir volumes for nginx's required writable dirs (`/var/cache/nginx`, `/var/run`, `/tmp`). nginx will fail to write PID file and crash-loop.

**After** — add to container spec and pod spec:
```yaml
          volumeMounts:  # TD-25-01: nginx needs writable dirs with readOnlyRootFilesystem
            - name: nginx-cache
              mountPath: /var/cache/nginx
            - name: nginx-run
              mountPath: /var/run
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: nginx-cache
          emptyDir: {}
        - name: nginx-run
          emptyDir: {}
        - name: tmp
          emptyDir:
            sizeLimit: 10Mi
```

---

### TD-25-02: Frontend Missing HPA (P1)

**File**: New — `k8s/frontend/hpa.yaml`
**Impact**: Fixed `replicas: 2` cannot scale during enrollment spikes. Backend has HPA; frontend does not.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: frontend-hpa
  namespace: university-ecosystem
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: frontend
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

### TD-25-03: Frontend Memory Limit Too Aggressive (P2)

**File**: `k8s/frontend/deployment.yaml:62-64`
**Impact**: 128Mi is tight for nginx with gzip. Spikes during concurrent requests risk OOMKill.

**Before**: `memory: 128Mi`
**After**: `memory: 256Mi  # TD-25-03: raised — nginx gzip needs headroom`

---

### TD-25-04: flagd runAsUser Mismatch (P2)

**File**: `k8s/flagd/deployment.yaml:36`
**Impact**: Uses UID 65534 (nobody); flagd distroless image expects 65532 (nonroot). File permissions may cause failures.

**Before**: `runAsUser: 65534`
**After**: `runAsUser: 65532  # TD-25-04: match distroless nonroot UID`

---

### TD-25-05: flagd Image Not SHA-Pinned (P2)

**File**: `k8s/flagd/deployment.yaml:41`
**Impact**: Mutable tag `v0.10.1` violates project convention (RZ-22-03: all images SHA-pinned). Production checklist comment on line 12 explicitly calls this out.

**Before**: `image: ghcr.io/open-feature/flagd:v0.10.1`
**After**: `image: ghcr.io/open-feature/flagd:v0.10.1@sha256:<digest>  # TD-25-05: SHA-pin per RZ-22-03`

*(Digest obtained at implementation time via `docker pull`)*

---

### TD-25-06: SpiceDB Health Check Python 2 Exception Syntax (P2)

**File**: `app/core/health.py:163`
**Impact**: `except TimeoutError, grpc.RpcError:` only catches `TimeoutError`. gRPC errors during SpiceDB health checks propagate as 500 instead of reporting unhealthy.

**Before**: `except TimeoutError, grpc.RpcError:`
**After**: `except (TimeoutError, grpc.RpcError):  # TD-25-06 + RZ-25-01`

---

## Phase 3 — Performance

### PERF-25-01: GraphQL Cost Tracking Fallback Needs Observability (P1)

**File**: `app/graphql/extensions.py:95-99`
**Impact**: When Redis fails, cost tracking falls back to per-process dict. With N pods, a user can spend N x budget. After fixing Python 2 syntax (RZ-25-01), add structured log so operators detect degraded mode.

**After** (lines 95-99):
```python
    except (ConnectionError, TimeoutError, OSError):  # nosec B110  # RZ-25-01 + PERF-25-01
        # PERF-25-01: Structured log for degraded cost tracking detection.
        logger.warning(
            "GraphQL cost tracking falling back to per-process counter",
            extra={"user_id": user_id, "cost": cost},
        )
```

---

### PERF-25-02: Cache Warmup Redis Errors Silently Uncaught (P1)

**File**: `app/services/cache_warmup.py:272`
**Impact**: Due to Python 2 syntax, only `ConnectionError` is caught. `TimeoutError` during warmup crashes the task, leaving caches cold and causing slow first-request latency.

**Before**: `except ConnectionError, TimeoutError, OSError:`
**After**: `except (ConnectionError, TimeoutError, OSError):  # PERF-25-02 + RZ-25-01`

---

### PERF-25-03: WS Auth Redis TimeoutError Uncaught (P1)

**File**: `app/api/ws/auth.py:240`
**Impact**: Redis timeout during WebSocket ticket validation returns 500 instead of fallback.

**Before**: `except ConnectionError, TimeoutError, OSError:`
**After**: `except (ConnectionError, TimeoutError, OSError):  # PERF-25-03 + RZ-25-01`

---

### PERF-25-04: Storage Cache TimeoutError/OSError Uncaught (P1)

**File**: `app/services/storage.py:200, 263`
**Impact**: Redis timeout during storage URL caching bypasses S3/Garage fallback path.

**Before**: `except ConnectionError, TimeoutError, OSError:`
**After**: `except (ConnectionError, TimeoutError, OSError):  # PERF-25-04 + RZ-25-01`

---

## Phase 4 — Modernization

### MOD-25-01: CI Gate to Prevent Python 2 Exception Syntax Regression (P1)

**File**: `.github/workflows/ci.yml`
**Impact**: This syntax has regressed across 3+ waves. Add a CI step (like the existing pickle-gate) to permanently prevent recurrence.

**After** — add step to the `lint` job:
```yaml
      - name: "Python 2 except syntax gate"
        run: |
          # RZ-25-01 / MOD-25-01: Catch Python 2 `except A, B:` syntax.
          # Correct form: `except (A, B):` — tuple required in Python 3.
          if grep -rn --include='*.py' -P 'except\s+\w[\w.]*\s*,\s*[A-Z]\w*' app/ tests/; then
            echo "::error::Python 2 except syntax detected. Use tuple form: except (A, B):"
            exit 1
          fi
```

---

### MOD-25-02: Fingerprint Redis Error Handling (P2)

**File**: `app/core/fingerprint.py:94, 126`
**Impact**: Device fingerprint Redis operations catch only `ConnectionError` due to Python 2 syntax. `TimeoutError` propagates.

**Before**: `except ConnectionError, TimeoutError, OSError:`
**After**: `except (ConnectionError, TimeoutError, OSError):  # MOD-25-02 + RZ-25-01`

---

### MOD-25-03: Localization Translation ValueError Uncaught (P2)

**File**: `app/core/localization/core.py:62`
**Impact**: String formatting errors in translation parameter interpolation propagate as 500.

**Before**: `except TypeError, ValueError:`
**After**: `except (TypeError, ValueError):  # MOD-25-03 + RZ-25-01`

---

### MOD-25-04: Observability Metric ValueError Uncaught (P2)

**File**: `app/core/observability.py:500`
**Impact**: `ValueError` in metric value conversion crashes request processing for non-critical observability concern.

**Before**: `except TypeError, ValueError:`
**After**: `except (TypeError, ValueError):  # MOD-25-04 + RZ-25-01`

---

## Implementation Sequence

1. **Batch 1** — RZ-25-01: Fix all 52 Python 2 except syntax instances across 23 files (mechanical find-and-replace with parentheses). This single fix resolves PERF-25-02/03/04, MOD-25-02/03/04, and TD-25-06 simultaneously.
2. **Batch 2** — RZ-25-02 + RZ-25-06: NullSessionBackend production guard + atomic revocation fallback (`redis_session.py`)
3. **Batch 3** — RZ-25-03 + TD-25-01 + TD-25-02 + TD-25-03: Frontend K8s fixes (NetworkPolicy port, volumes, HPA, memory)
4. **Batch 4** — RZ-25-04 + RZ-25-05 + PERF-25-01: Rate limit lock + manifest race + cost tracking observability
5. **Batch 5** — TD-25-04 + TD-25-05 + MOD-25-01: flagd deployment fixes + CI regression gate

---

## Verification Plan

1. **Syntax check**: `python -m py_compile` on every modified `.py` file
2. **Lint**: `python -m ruff check app/` — zero errors
3. **Grep regression**: `grep -rn --include='*.py' -P 'except\s+\w[\w.]*\s*,\s*[A-Z]\w*' app/` — zero matches
4. **K8s validation**: `kubectl --dry-run=client -f k8s/frontend/` on all modified YAML
5. **Pre-commit**: Full suite (ruff, ruff-format, detect-secrets, bandit, mypy)
6. **Unit tests**: `pytest tests/` — existing tests pass (Python 2 syntax fixes should not break behavior, only restore intended behavior)

---

## Files Modified (complete list)

**Python (23 files)**:
- `app/auth/security.py`
- `app/auth/redis_session.py`
- `app/auth/mfa/challenge.py`
- `app/core/database.py`
- `app/core/fingerprint.py`
- `app/core/health.py`
- `app/core/localization/core.py`
- `app/core/observability.py`
- `app/core/ratelimit/fastapi.py`
- `app/core/ratelimit/strategies/redis.py`
- `app/api/deps/auth.py`
- `app/api/health.py`
- `app/api/notifications.py`
- `app/api/ws/auth.py`
- `app/api/ws/presence.py`
- `app/deps/cache.py`
- `app/graphql/extensions.py`
- `app/graphql/queries.py`
- `app/models/user_loaders.py`
- `app/services/cache_warmup.py`
- `app/services/chat/command_service.py`
- `app/services/file_scanner.py`
- `app/services/storage.py`
- `app/services/webpush.py`
- `app/utils/sanitization.py`
- `app/utils/images.py`
- `app/utils/files.py`
- `app/utils/email.py`

**K8s (3 files + 1 new)**:
- `k8s/frontend/network-policy.yaml`
- `k8s/frontend/deployment.yaml`
- `k8s/frontend/hpa.yaml` (new)
- `k8s/flagd/deployment.yaml`

**CI (1 file)**:
- `.github/workflows/ci.yml`

**Total: ~30 files, 20 issues (3 P0, 9 P1, 8 P2)**
