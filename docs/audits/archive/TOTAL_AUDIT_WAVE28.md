# TOTAL_AUDIT_WAVE28.md — Wave 28 Comprehensive Audit

## Context

Wave 27 claimed to fix all 44 Python 2 `except` syntax violations, but **introduced** the pattern instead of fixing it — using `except A, B:` (Python 2) instead of `except (A, B):` (Python 3 tuple form). This is a **SyntaxError** on Python 3.13+ and the CI gate (`MOD-27-01`) should reject it. Additionally, infrastructure review found a missing K8s seccompProfile, dual Renovate configs with conflicting rules, and a minor CSRF timing concern. The Go services, Rust code, frontend security, and CI/CD pipeline are all production-ready with no critical issues.

**Scope:** 43 code fixes across 21 Python files + 3 infrastructure files + CLAUDE.md updates
(Initial grep found 31 two-exception violations; 12 additional three-exception violations found during verification)

---

## 1. RED ZONE — Critical (must fix before deploy)

### RZ-28-01: Python 2 `except` syntax — 43 violations, 21 files
**Severity:** CRITICAL — `SyntaxError` at import time, application cannot start
**Root cause:** Wave 27 commit `85e90296c` used `except A, B:` instead of `except (A, B):`

**Transformation rule:** Every `except X, Y:` → `except (X, Y):`, preserving trailing comments.

| # | File | Line | Was | Should be |
|---|------|------|-----|-----------|
| 1 | `app/auth/security.py` | 56 | `except AttributeError, NotImplementedError:` | `except (AttributeError, NotImplementedError):` |
| 2 | `app/auth/mfa/challenge.py` | 90 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 3 | `app/core/observability.py` | 498 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 4 | `app/deps/cache.py` | 273 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 5 | `app/deps/cache.py` | 303 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 6 | `app/deps/cache.py` | 350 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 7 | `app/deps/cache.py` | 427 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 8 | `app/deps/cache.py` | 450 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 9 | `app/deps/cache.py` | 466 | `except RedisError, OSError:` | `except (RedisError, OSError):` |
| 10 | `app/utils/images.py` | 22 | `except ImportError, OSError:` | `except (ImportError, OSError):` |
| 11 | `app/utils/files.py` | 394 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 12 | `app/utils/files.py` | 399 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 13 | `app/utils/sanitization.py` | 193 | `except ValueError, OSError:` | `except (ValueError, OSError):` |
| 14 | `app/models/user_loaders.py` | 122 | `except TypeError, AttributeError:` | `except (TypeError, AttributeError):` |
| 15 | `app/graphql/queries.py` | 127 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 16 | `app/graphql/queries.py` | 175 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 17 | `app/graphql/queries.py` | 232 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 18 | `app/graphql/queries.py` | 280 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 19 | `app/api/deps/auth.py` | 161 | `except ValueError, TypeError:` | `except (ValueError, TypeError):` |
| 20 | `app/api/notifications.py` | 151 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 21 | `app/api/notifications.py` | 394 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 22 | `app/api/ws/presence.py` | 225 | `except ValueError, AttributeError:` | `except (ValueError, AttributeError):` |
| 23 | `app/services/webpush.py` | 130 | `except OSError, ConnectionError:` | `except (OSError, ConnectionError):` |
| 24 | `app/services/webpush.py` | 221 | `except ZoneInfoNotFoundError, ValueError:` | `except (ZoneInfoNotFoundError, ValueError):` |
| 25 | `app/services/webpush.py` | 324 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 26 | `app/services/webpush.py` | 358 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 27 | `app/services/webpush.py` | 383 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 28 | `app/services/webpush.py` | 428 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 29 | `app/services/webpush.py` | 603 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 30 | `app/services/file_scanner.py` | 132 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 31 | `app/services/file_scanner.py` | 144 | `except TypeError, ValueError:` | `except (TypeError, ValueError):` |
| 32 | `app/auth/security.py` | 67 | `except FileNotFoundError, ValueError, OSError:` | `except (FileNotFoundError, ValueError, OSError):` |
| 33 | `app/deps/cache.py` | 238 | `except RedisError, OSError, AttributeError:` | `except (RedisError, OSError, AttributeError):` |
| 34 | `app/deps/cache.py` | 408 | `except RedisError, OSError, AttributeError:` | `except (RedisError, OSError, AttributeError):` |
| 35 | `app/services/cache_warmup.py` | 272 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 36 | `app/api/notifications.py` | 77 | `except OverflowError, OSError, ValueError:` | `except (OverflowError, OSError, ValueError):` |
| 37 | `app/api/notifications.py` | 96 | `except OverflowError, OSError, ValueError:` | `except (OverflowError, OSError, ValueError):` |
| 38 | `app/api/ws/auth.py` | 238 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 39 | `app/services/chat/command_service.py` | 153 | `except ValueError, KeyError, TypeError:` | `except (ValueError, KeyError, TypeError):` |
| 40 | `app/services/storage.py` | 200 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 41 | `app/services/storage.py` | 263 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |
| 42 | `app/core/health.py` | 161 | `except TimeoutError, grpc.RpcError:` | `except (TimeoutError, grpc.RpcError):` |
| 43 | `app/graphql/extensions.py` | 96 | `except ConnectionError, TimeoutError, OSError:` | `except (ConnectionError, TimeoutError, OSError):` |

**Tag:** Update existing `# RZ-27-01` comments to `# RZ-28-01` on each fixed line.

---

## 2. SECURITY HARDENING — Medium

### RZ-28-02: CSRF anonymous nonce validation — timing side-channel
**Severity:** MEDIUM (defense-in-depth)
**File:** `app/core/csrf.py`, lines 181–184

**Problem:** The nonce validation uses short-circuit boolean checks (`not anon_nonce`, `len()`, `all()`) that exit at different times depending on input. While `secrets.token_hex(16)` on line 180 dominates the timing budget (~1ms CSPRNG), the validation branch itself leaks which check failed.

**Was (lines 181–184):**
```python
if (
    not anon_nonce
    or len(anon_nonce) != _ANON_NONCE_HEX_LEN
    or not all(c in "0123456789abcdef" for c in anon_nonce)
):
```

**Should be:**
```python
import re
_ANON_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
# ...
if not (anon_nonce and _ANON_NONCE_RE.fullmatch(anon_nonce)):
```

**Rationale:** `re.fullmatch` on a fixed-length pattern has more uniform timing than short-circuit chains. The regex is compiled once at module level (zero runtime cost).

### TD-28-01: Frontend K8s deployment missing seccompProfile
**Severity:** LOW-MEDIUM
**File:** `k8s/frontend/deployment.yaml`

Backend deployment has `seccompProfile: RuntimeDefault` at pod level. Frontend does not. Kyverno policy `require-seccomp-profile` enforces this — frontend would fail admission in Enforce mode.

**Was (lines 19–25):**
```yaml
    spec:
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      containers:
```

**Should be:**
```yaml
    spec:
      automountServiceAccountToken: false
      securityContext:                    # TD-28-01
        seccompProfile:
          type: RuntimeDefault
      terminationGracePeriodSeconds: 30
      containers:
```

---

## 3. TECH DEBT

### TD-28-02: Dual Renovate configs — conflicting rules
**Severity:** MEDIUM
**Files:** `renovate.json` (root, 70 lines) + `.github/renovate.json` (127 lines)

**Problem:** Renovate merges both files. Conflicts:
- Root extends `":automergeMinor"` + `"schedule:weekends"` — `.github` has `"schedule": ["after 3am and before 7am on Monday"]`
- Root groups Python deps via `pep621` manager — `.github` uses `uv` manager
- Root auto-merges GitHub Actions — `.github` does not
- Crypto manual-review rule (RZ-22-02) is **only** in `.github/renovate.json`

**Fix:** Merge all rules into root `renovate.json`. The `.github/renovate.json` has the more comprehensive rules (Rust/Go grouping, crypto manual-review, Docker security images, OSV alerts). Consolidate by:
1. Copy crypto, Docker security, Go, Rust, and OSV rules from `.github/renovate.json` into root `renovate.json`
2. Keep root's `":automergeMinor"` and update schedule to Monday early morning
3. Delete `.github/renovate.json`

### TD-28-03: Ingress hardcoded example domains
**Severity:** LOW
**File:** `k8s/ingress.yaml`, lines 24–25, 28, 38

Add `# TODO(TD-28-03): Replace with actual domain or Helm .Values.ingress.hosts` comment above each hardcoded `university.example.com` occurrence.

### TD-28-04: Docker Compose ACME_EMAIL empty default
**Severity:** LOW
**File:** `docker-compose.yml`, ~line 32

`ACME_EMAIL: ${ACME_EMAIL:-}` defaults to empty string. Add comment: `# Required for production — Caddy will fail cert issuance without valid email`.

### TD-28-05: pyproject.toml — passlib deprecation filter may be dead code
**Severity:** LOW
**File:** `pyproject.toml`, ~line 304

Filter `"ignore::DeprecationWarning:passlib"` exists but bcrypt/passlib removed in Wave 21 (TD-21-04). Verify if any test imports passlib; if not, remove the filter.

---

## 4. PERFORMANCE — No issues found

### PERF-28-01: React.memo() cleanup — VERIFIED COMPLETE
All 18 grep hits are **comments** about removed `React.memo()` (pattern: `// PERF-27-02: Removed React.memo()`). No actual `memo()` wrapper calls remain except 2 with custom `areEqual` comparators. **No action required.**

### PERF-28-02: SQLAlchemy lazy="noload" — VERIFIED COMPLETE
All relationships have `lazy="noload"`. No N+1 regression. **No action required.**

### PERF-28-03: Go services — no performance issues
ws-hub: proper connection pooling, 60KB message limits at ingress and broadcast, backpressure eviction.
file-processor: HTTP transport MaxIdleConnsPerHost=20, MaxConnsPerHost=50.
Gateway: rate-limit fails closed. **No action required.**

---

## 5. MODERNIZATION — Suggestions

### MOD-28-01: Add pre-commit hook for Python 2 except syntax
**Severity:** Suggestion
**File:** `.pre-commit-config.yaml`

The CI gate catches this post-push. A local pre-commit hook would catch it before. Add:
```yaml
- repo: local
  hooks:
    - id: no-python2-except
      name: Reject Python 2 except syntax
      entry: python -c "import sys,re;files=[f for f in sys.argv[1:] if f.endswith('.py')];bad=[f'{f}:{i+1}' for f in files for i,l in enumerate(open(f)) if re.search(r'except\s+\w+\s*,\s*\w+\s*:', l)];sys.exit('\n'.join(bad)) if bad else None"
      language: system
      types: [python]
```

### MOD-28-02: Renovate — add `uv` manager support to root config
**Severity:** Suggestion
After TD-28-02 consolidation, ensure the merged config includes `matchManagers: ["uv"]` for Python crypto packages (currently only in `.github/renovate.json`).

---

## Verified — No Issues Found

| Area | Status | Detail |
|------|--------|--------|
| **Frontend XSS/Sanitization** | ✅ | Trusted Types + WASM sanitizer + SafeHtml fallback |
| **Frontend CSRF** | ✅ | Cookie + header tokens via Axios config |
| **WebSocket validation** | ✅ | Valibot runtime schemas, message type allowlist |
| **ETag cache security** | ✅ | HMAC integrity, session isolation, in-memory payloads |
| **WS-Hub goroutines** | ✅ | WaitGroup lifecycle, panic recovery, ctx cancellation |
| **WS-Hub JWT auth** | ✅ | Algorithm-confusion fixed (RS256-only, no HMAC fallback) |
| **File-processor auth** | ✅ | Mirrors ws-hub; RS256-only with algorithm pre-check |
| **Path traversal** | ✅ | `path.Clean()` + `..` rejection at gRPC boundary |
| **Rust code** | ✅ | No unsafe, no unwrap, panic boundaries, overflow guards |
| **CI/CD pipeline** | ✅ | SHA-pinned actions, SLSA L3, OIDC auth, Trivy + SBOM |
| **K8s backend** | ✅ | seccompProfile, drop ALL, IMDS protection, NetworkPolicies |
| **Secret management** | ✅ | detect-secrets + gitleaks, ExternalSecrets, no hardcoded creds |
| **HIBP client cleanup** | ✅ | `close_hibp_client()` called in lifespan `finally` block |
| **RSA key cache** | ✅ | TOCTOU correctly handled (returns from `new_cache`) |
| **Rate-limit fail-closed** | ✅ | Double failure → 503, metric incremented |

---

## Implementation Sequence

| Order | Issue | Files | Estimate |
|-------|-------|-------|----------|
| 1 | **RZ-28-01** — Python 2 except syntax | 21 files, 43 changes | ~25 min |
| 2 | **TD-28-02** — Consolidate Renovate configs | 2 files (merge + delete) | ~15 min |
| 3 | **TD-28-01** — Frontend seccompProfile | 1 file | ~2 min |
| 4 | **RZ-28-02** — CSRF timing hardening | 1 file | ~10 min |
| 5 | **TD-28-03/04/05** — Low-priority cleanup | 3 files | ~10 min |
| 6 | **MOD-28-01** — Pre-commit hook | 1 file | ~5 min |
| 7 | **CLAUDE.md** — Update audit trail | 1 file | ~10 min |

**Total: ~19 files changed, ~72 min estimated**

---

## Verification Plan

1. **Syntax check all 14 Python files:** `python -m py_compile <file>` for each
2. **Ruff lint:** `python -m ruff check app/`
3. **Grep for remaining violations:** `grep -rn "except \w\+, \w\+:" app/` should return 0 results
4. **Frontend typecheck:** `cd frontend && npx tsc --noEmit`
5. **K8s dry-run:** `kubectl apply --dry-run=server -f k8s/frontend/deployment.yaml`
6. **Renovate validate:** `npx renovate-config-validator renovate.json`

---

## CLAUDE.md Updates

After completion, add to CLAUDE.md:
- **Audit Trail:** `Wave 28: 31+5 fixes, ~19 files — Python 2 except syntax (RZ-28-01, fixes Wave 27 regression), K8s seccompProfile (TD-28-01), Renovate consolidation (TD-28-02), CSRF timing (RZ-28-02)`
- **Gotchas:** `Wave 27 introduced Python 2 except syntax instead of fixing it — Wave 28 corrected all 31 remaining violations`
- **Code Conventions:** Update `except (A, B):` convention note to reference RZ-28-01
