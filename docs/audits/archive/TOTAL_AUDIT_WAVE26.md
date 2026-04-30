# TOTAL_AUDIT_WAVE26.md — Wave 26 Comprehensive Audit Report

**Date:** 2026-03-25
**Auditor:** Claude Opus 4.6 (Principal Security Architect)
**Branch:** `egorribun`
**Scope:** Python backend, TypeScript frontend, Go services, Helm/K8s, CI/CD

---

## Executive Summary

Wave 26 identified and fixed **16 issues** across **~30 files** (1 false positive dropped).
Key finding: 44 instances of Python 2 `except` syntax tagged in Wave 25 were **never actually fixed** — only tagged with `# RZ-25-01`. This wave completes the fix.

| Category | Count | Severity Breakdown |
|----------|-------|--------------------|
| Red Zone (Security) | 8 | 1 CRITICAL, 4 HIGH, 2 MEDIUM, 1 HIGH |
| Tech Debt | 4 | 1 HIGH, 2 MEDIUM, 1 LOW |
| Performance | 2 | 1 MEDIUM, 1 LOW |
| Modernization | 2 | 2 MEDIUM |
| False Positive | 1 | — (dropped) |

---

## RED ZONE — Security (8 Issues)

### RZ-26-01 · CRITICAL · Python 2 `except` Syntax — 44 Occurrences, 21 Files

**Problem:** `except A, B:` (Python 2 comma form) instead of `except (A, B):` (tuple form). On Python 3.13+, the comma form is a `SyntaxError`. All 44 occurrences had `# RZ-25-01` tags from Wave 25 but the actual syntax was never corrected.

**Files (21):** `app/auth/security.py`, `app/deps/cache.py` (8), `app/services/webpush.py` (7), `app/api/notifications.py` (4), `app/graphql/queries.py` (4), `app/services/storage.py` (2), `app/services/file_scanner.py` (2), `app/utils/files.py` (2), `app/core/events.py`, `app/core/health.py`, `app/core/observability.py`, `app/graphql/extensions.py`, `app/models/user_loaders.py`, `app/services/cache_warmup.py`, `app/services/chat/command_service.py`, `app/auth/mfa/challenge.py`, `app/api/ws/auth.py`, `app/api/ws/presence.py`, `app/api/deps/auth.py`, `app/utils/sanitization.py`, `app/utils/images.py`

**Fix:** `except A, B:` → `except (A, B):` globally. Tags updated to `# RZ-26-01`.

---

### RZ-26-02 · HIGH · Helm `values.yaml` Plaintext DB Password

**File:** `charts/university-ecosystem/values.yaml:17`
**Was:** `DATABASE_URL: "postgresql+asyncpg://postgres:DevSecurePass2024!@postgres:5432/university"`
**Now:** `DATABASE_URL: ""` with comment requiring `--set` or ExternalSecret.

---

### RZ-26-03 · HIGH · Helm Secrets Template Accepts Empty `jwtSecret`

**File:** `charts/university-ecosystem/templates/secrets.yaml:9`
**Was:** `{{ .Values.gateway.config.jwtSecret | b64enc | quote }}`
**Now:** `{{ required "gateway.config.jwtSecret must be set" .Values.gateway.config.jwtSecret | b64enc | quote }}`

---

### RZ-26-04 · HIGH · File-Processor `sourceKey`/`destKey` Unbounded Length

**File:** `services/file-processor/internal/service/server.go`
**Problem:** Options key/value lengths bounded but sourceKey/destKey had no limit. DoS via Temporal history bloat.
**Fix:** Added `maxKeyLen = 1024` bound with `codes.InvalidArgument` rejection.

---

### RZ-26-05 · HIGH · File-Processor GraphQL Depth Estimation Bypass

**File:** `services/file-processor/internal/middleware/graphql_depth.go`
**Problem:** `estimateQueryDepth()` did not handle `\"` (escaped quotes) inside strings. Braces inside string literals were counted, allowing depth limit bypass.
**Fix:** Added `escaped` flag tracking — `\\` inside strings skips next character.

---

### RZ-26-06 · MEDIUM · SSRF `validate_and_resolve()` Missing Fail-Closed

**File:** `app/core/ssrf.py:162`
**Problem:** `ipaddress.ip_address(sockaddr[0])` could raise `ValueError` without being caught, unlike the identical pattern in `_check_resolved()` which has try-catch.
**Fix:** Added `try/except ValueError` with fail-closed `raise ValueError("SSRF blocked: unparseable address")`.

---

### RZ-26-07 · MEDIUM · Frontend `sendTyping`/`sendRead` TOCTOU

**File:** `frontend/src/hooks/useChatWebSocket.ts:441,450`
**Problem:** `readyState` check then `send()` can race if WS closes between the two.
**Fix:** Wrapped `send()` in `try/catch` on both `sendTyping` and `sendRead`.

---

### RZ-26-08 · HIGH · WS-Hub `WritePump` Missing `ctx.Done()` Select

**File:** `services/ws-hub/pkg/hub/client.go:167`
**Problem:** WritePump's select loop only listened on `c.Send` and `ticker.C` — not `c.ctx.Done()`. Goroutine leak when ReadPump exits.
**Fix:** Added `case <-c.ctx.Done(): return` to the select block.

---

## TECH DEBT (4 Issues)

### TD-26-01 · HIGH · Frontend K8s Port Mismatch

**Files:** `k8s/frontend/deployment.yaml:29`, `k8s/frontend/network-policy.yaml:25`
**Problem:** `containerPort: 80` but nginx-unprivileged listens on `8080`. Probes and NetworkPolicy targeted wrong port.
**Fix:** Changed both to `8080`.

---

### TD-26-02 · MEDIUM · Missing AbortController on `/ws/ticket` Fetch

**File:** `frontend/src/hooks/useChatWebSocket.ts:208`
**Fix:** Added `AbortController` with `signal` passed to `fetch()`. Cleanup on unmount.

---

### TD-26-03 · MEDIUM · Missing Timeout on `/ws/ticket` Fetch

**File:** `frontend/src/hooks/useChatWebSocket.ts:208`
**Fix:** Added 5s timeout via `setTimeout(() => controller.abort(), 5000)` with `clearTimeout` in `finally`.

---

### TD-26-04 · LOW · Unbounded Dependency Versions

**File:** `pyproject.toml`
**Fix:** Added upper bounds: `pillow-avif-plugin>=1.4.0,<2`, `pyasn1>=0.6.3,<1`.

---

## PERFORMANCE (2 Issues)

### PERF-26-01 · MEDIUM · Zustand `useAppShellActions` New Refs Per Render

**File:** `frontend/src/stores/appShellStore.ts:105-116`
**Problem:** Inline selector closure inside `useShallow()` created new object allocation every render.
**Fix:** Extracted `actionsSelector` to module scope — stable reference.

---

### PERF-26-02 · LOW · `typingUsers` Map Global Cap → Per-Chat Cap

**File:** `frontend/src/hooks/useChatWebSocket.ts:315`
**Problem:** Global 100-entry cap starved low-activity chats.
**Fix:** Replaced with per-chat cap of 20 (`MAX_TYPING_PER_CHAT`).

---

## MODERNIZATION (2 Issues)

### MOD-26-01 · MEDIUM · Go Test Coverage Threshold in CI

**File:** `.github/workflows/reusable-go-tests.yml`
**Problem:** Python had 80% coverage gate; Go had none.
**Fix:** Added coverage check step (60% threshold) after `go test -coverprofile`.

---

### MOD-26-02 · MEDIUM · CI Python 2 Except Syntax Gate Regex

**File:** `.github/workflows/ci.yml:187`
**Problem:** Regex `'except [A-Za-z]+, [A-Z]'` missed multi-exception cases.
**Fix:** Strengthened to Perl regex: `'except\s+[A-Za-z_][\w.]*\s*,\s*[A-Za-z_]'` with `grep -v 'except ('`.

---

## FALSE POSITIVE (Dropped)

| ID | Description | Reason |
|----|-------------|--------|
| FP-26-01 | Gateway JWT parsing race in `auth.go` | Token string is request-local (handler parameter `c`), not shared mutable state. No race under HTTP/2. |

---

## Verification Results

- `grep -rn ... 'except' ... | grep -v 'except ('` → **0 results** ✓
- `python -m py_compile` on all 21 modified `.py` files → **all pass** ✓
- `python -m ruff check app/` → **39 pre-existing UP037 warnings** (not introduced by Wave 26) ✓
- `grep -r 'DevSecurePass' charts/` → **0 results** ✓

---

## Summary

| Metric | Value |
|--------|-------|
| Issues Found | 17 (16 valid + 1 FP) |
| Issues Fixed | 16 |
| Files Modified | ~30 |
| Lines Changed | ~+166/-79 (est.) |
| Categories | 8 RZ + 4 TD + 2 PERF + 2 MOD |
