---
name: Wave 136 backlog
description: Wave 136 closed Tier 1 + Tier 2 + Tier 3 (JWT (d) Hybrid + Playwright + build-orchestrated trace + healthchecks/nginx cleanup).
type: project
originSessionId: wave136-sw8
status: CLOSED
---
# Wave 136 backlog — CLOSED

**Status**: CLOSED. Tier 1 + Tier 2 + Tier 3 per user-approved 3-question
AskUserQuestion at session start (Q1=Tier 1+2+3, Q2=JWT (d) Hybrid,
Q3a=Medium process._getActiveHandles trace, Q3b=Playwright real-Chrome path).

Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-eventual-stallman.md`

Wall-clock: ~7-8h core (vs ~10-13h plan estimate; refined down by Explore
discovery that gateway already has Redis pub/sub revocation infrastructure).

## Closed in Wave 136

### SW0 — Design doc (`3fb5451cc`, 1 file +209)

NEW `docs/plans/2026-05-07-wave136-tier-1-2-3-design.md` per
`superpowers:brainstorming` skill convention. Architecture diagrams + SW
breakdown + verification approach + risks/mitigations.

### SW1 — JWT is_active embed (`b37e827e4`, 2 files +232)

Closes W135 §Honesty #2 (gateway+backend JWT mismatch).

- `app/services/auth/login_session_manager.py` (+6): `finalize_login`
  threads `extra_claims={"is_active": bool(user.is_active)}` to
  `session_service.create_access_token`.
- NEW `tests/test_auth_jwt_payload.py` (+226, 5 tests): contract tests
  for JWT payload shape.

Verification: 48 passed across auth slice + login_service +
auth_concurrency + utils_monster.

Pre-W136 JWTs invalidate on deploy (Go json defaults missing bool to
false → 403 → re-login). Acceptable under no-deploy scope.

### SW2 — Backend session revocation broadcast (`6989637f0`, 2 files +325)

Closes immediate-effect part of W135 §Honesty #2 by leveraging EXISTING
gateway revocation infrastructure (NO new NATS subject needed).

- `app/services/user/compliance_service.py` (+39): NEW
  `_revoke_user_sessions(user_id)` calls existing
  `revoke_sessions_matching` which already publishes JTIs to
  `session:revocations` Redis channel.
- NEW `tests/test_user_deactivation_revocation.py` (+286, 6 tests).

Architecture: gateway's `ListenForRevocations` consumes the Redis pub/sub
channel + adds JTIs to `revoked:jti:{jti}` keys with L1 cache + XFetch
probabilistic refresh. Backend just publishes — leverages all existing
infrastructure.

Verification: 65 passed (auth_service + auth_security + auth_jwt_payload
+ user_deactivation_revocation + login_service_coverage + user_service +
user_service_decomposed).

### SW3 — Playwright visual smoke (`7bccb5ee7`, 2 files +392)

Closes W135 §Honesty #1 at tool-availability level.

- NEW `frontend/scripts/playwright-visual-smoke.mjs` (~280 LoC + 75 LoC
  docs): real Chrome (`channel: "chrome"`) with bundled Chromium fallback;
  2-phase smoke (navigation `domcontentloaded` + best-effort screenshot);
  captures console + network + final URL + HTTP status + hydration error
  count.
- `frontend/package.json` (+1): NEW `visual:smoke` npm script.

Verification: ran against `npm run start` Node SSR :3000 (no backend);
/login + /404 status=OK with sidecar JSON saved (9.3KB + 8.5KB); 0 React
hydration errors.

Honest deferral: screenshot for /login fails fast (5s) due to
ParticleAuthBackground canvas physics loop; documented inline. Real
Docker chain authed visual smoke = polish-pass candidate or W137 first
task.

### SW4 — failed_login_attempts model+schema fix (`938c797a6`, 3 files +255)

Closes W135 §Honesty #3.

W135 SW2 NotNullViolation REPRODUCED in test SQLite (not Docker-only as
initial test docstring assumed). Real model-level drift between
original migration's intent (`nullable=True`) and inherited UserFK mixin's
NOT NULL.

- `app/models/auth.py` (+23): override `user_id` in `FailedLoginAttempt`
  with `nullable=True` + `ondelete="SET NULL"`.
- NEW `tests/test_failed_login_attempts.py` (+126, 4 tests).
- NEW `alembic/versions/202605070001_failed_login_attempts_user_id_nullable.py`
  (+106): drop FK + alter to nullable + recreate FK with SET NULL.
  Idempotent on re-run; downgrade purges NULL rows before NOT NULL.

Why model fix > conditional INSERT: preserves IP-based brute-force
detection signal (TD-3 from 2026-02-26, `ix_failed_login_attempts_ip_attempted_at`).

Verification: 28 passed (4 new + 24 regression auth slice).

### SW5 — build-orchestrated hang trace (`c67ac5cce`, 3 files +240/-9)

Closes W135 §Honesty #4 (DIAGNOSED, upstream fix W137+) + bonus mtime fix.

- `.gitignore` (+1): .wave136-trace/ exclusion.
- `frontend/scripts/build-orchestrated.mjs` (+~70/-~10): `isArtifactFresh`
  helper + WAVE136_HANG_TRACE=1 flag + IPC-enabled stdio.
- NEW `frontend/scripts/wave136-hang-trace-agent.cjs` (+155): NODE_OPTIONS
  --require injection + IPC trigger + watchdog + handle dump to stderr +
  .wave136-trace/dump-*.json + IPC reply.

**Two issues addressed**:

1. **W135 SW3 mtime regression FIXED**: kill-after-artifacts triggered at
   2s (too early) on STALE leftover artifacts. Build × 3 "reproducibility"
   was partly an artifact of this bug. Fixed via `mtime >= startTime`
   check.

2. **Hang root cause DIAGNOSED**: trace at 23.3s post-artifact-stable:
   `MessagePort + Pipe + Socket × 2`. The MessagePort is the smoking gun
   — Worker thread spawned by some plugin (likely Rolldown native or
   `@rolldown/plugin-babel`) not terminated post-build. Filed for upstream.

Verification: build × 2 BYTE-IDENTICAL to W135 baseline (139,808 main +
65,864 _shell.html + 53,181 sw.js + 39,373 server.js).

### SW6 — Workbox export + Linux CI (`3314364bd`, 4 files +251/-44)

Closes W135 §Honesty #5 + W135 §Honesty #8/#11 (consolidated).

- NEW `frontend/scripts/workbox-config.mjs` (+51): exports
  `PWA_INJECT_CONFIG` — single source of truth.
- `frontend/vite.config.mts` (-23/+5 net): imports + uses directly.
- `frontend/scripts/build-orchestrated.mjs` (-15/+6 net): imports + spreads
  `...PWA_INJECT_CONFIG`.
- NEW `.github/workflows/build-orchestrated-linux.yml` (+186): workflow_
  dispatch trigger, build × 3 with sha256sum BYTE-IDENTICAL assertion.

Drift impossible: both consumers reference same export.

Verification: BYTE-IDENTICAL to W135 baseline.

### SW7 — Tier 3 housekeeping (`51139c2e7`, 2 files +34/-148)

- DELETED `frontend/nginx.conf` (-148 LoC; obsolete since W131 SW3).
- `docker-compose.full.yml`: 3 healthcheck blocks (imgproxy CLI, grafana
  wget /api/health, prometheus wget /-/healthy) + Honesty comments for
  3 deferred services.

Honest deferrals (3 distroless services need Dockerfile changes):
- file-processor: needs grpc_health_probe binary in image
- tempo + loki: distroless grafana/* images, no wget/curl/nc/bash

Verification: yaml.safe_load_all valid.

### SW8 — Audit + memory + N+3 rotation (this commit)

- NEW `docs/audits/AUDIT_WAVE136.md` (~330 lines)
- NEW `memory/wave136_backlog.md` (this file)
- NEW `memory/wave137_opening_prompt.md` (BOTH USER `.claude` + REPO)
- `CLAUDE.md` ## Audit Trail W136 row + new gotchas (~5-7)
- `git mv docs/audits/AUDIT_WAVE133.md docs/audits/archive/AUDIT_WAVE133.md`
  (N+3 rotation; active waves now W134/W135/W136)
- `memory/MEMORY.md` updates

## Honest § Honesty caveats

**Pre-W136 9 W135 caveats; W136 closes 6 + introduces 3 NEW + carries 3**.

### CLOSED via SW1+SW2+SW3+SW4+SW5+SW6 (6 of 9)

1. ✅ W135 §Honesty #2 (Gateway+backend JWT mismatch) — SW1+SW2
2. ✅ W135 §Honesty #1 (chrome-devtools-mcp Windows wall) — SW3 tool-level
3. ✅ W135 §Honesty #3 (failed_login_attempts schema) — SW4 model+migration
4. ✅ W135 §Honesty #4 (build-orchestrated hang) — SW5 DIAGNOSED + mtime fix
5. ✅ W135 §Honesty #5 (Workbox config drift) — SW6 single-source export
6. ✅ W135 §Honesty #8/#11 (Linux CI) — SW6 workflow

### REMAINING from W135 (3 of 9)

7. **W135 §Honesty #6 (W134 #2 bundle delta carry-forward)** — honest
   framing recording. W136 BYTE-IDENTICAL to W135 baseline.
8. **W135 §Honesty #7 (W134 #10 /messenger Phase 5 punted)** — no-deploy
   "production-as-is" decision unchanged.
9. **W135 §Honesty #9 (curl-only verification, not authed browser)** —
   STILL deferred but now feasible with W136 SW1+SW2+SW4 + SW3 tool.
   Polish-pass or W137.

### NEW from W136 (3 caveats)

10. **build-orchestrated upstream hang fix** — SW5 diagnosed; local fix
    impractical without monkey-patching plugin internals. W137+ to file
    upstream issue at vitejs/rolldown.

11. **Tier 3 housekeeping partial** — 3 of 6 healthchecks done; 3
    distroless services (file-processor, tempo, loki) deferred to W137+
    (Dockerfile changes required).

12. **Playwright /login screenshot fragility** — ParticleAuthBackground
    canvas blocks Playwright stability check. Sidecar JSON captures
    diagnostic value regardless. Acceptable trade-off; not a fix target
    without VITE_E2E_MODE-style flag.

## W137 candidates

See [`memory/wave137_opening_prompt.md`](wave137_opening_prompt.md) for
full list. Highlights:

### Highest priority

- **Real Docker chain authed visual smoke** (~1-2h) — closes W135 §Honesty
  #9 fully via W136 infrastructure (JWT + Playwright + schema fix).
- **Upstream issue files** (~1-2h):
  - vitejs/rolldown hang (Worker MessagePort)
  - chrome-devtools-mcp Windows wall
  - tempo/loki distroless healthcheck

### Tier 3 carry-forward

- file-processor Dockerfile + grpc_health_probe (~30 min)
- tempo + loki distroless workaround (~30 min)

### Pre-existing W134/W135 carry-forward

- W134 §Honesty #2 + #10 (honest framing + explicit decision)

### Tier 4 cross-cutting + Tier 5 explicit decision

(see opening prompt)
