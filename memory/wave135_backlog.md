---
name: Wave 135 backlog
description: Wave 135 closed L scope — Aggressive cleanup (AbortController removal + sessions factory migration) + Docker chain verification (curl-only fallback) + build-orchestrated.mjs retiring wave127-build-x3.sh.
type: project
originSessionId: wave135-sw4
status: CLOSED
---
# Wave 135 backlog — CLOSED

**Status**: CLOSED L scope (B + Aggressive cleanup + Option E Path B per user-approved 3-question AskUserQuestion at session start: Q1=L, Q2=Aggressive, Q3=Path B full commitment).

Plan file: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-sprightly-quail.md`. Actual wall clock: ~3.5-4h (SW1 ~1h, SW2 ~1h, SW3 ~1.5h with two false-start iterations, SW4 ~30min).

## Closed in Wave 135

### SW1 — `feat(wave135-sw1-cleanup-aggressive)` (`6c5ada141`, 4 files +230/-34)

Aggressive cleanup. Closes W134 §Honesty #3 + #5 cleanly.

Files:
- `frontend/src/hooks/auth/useProfileSync.ts` (±65 net) — full AbortController removal: dropped `activeRequestRef = useRef<AbortController | null>(null)`; `clearProfile`'s `controller?.abort()` → `queryClient.cancelQueries`; auto-fetch effect's `new AbortController()` block removed; outer catch `controller.signal.aborted` → `isCancel(error)` (axios canonical); `finally` block collapsed to `setInitializing(false)`. `import { ..., isCancel } from "axios"` added.
- `frontend/src/api/hooks/sessions.ts` (+39) — new exports `updateSessionInCache(queryClient, userId, updated)` + `invalidateSessions(queryClient, userId)`. Mirrors W129 events.ts / W130 schedule.ts factory placement.
- `frontend/src/pages/settings/hooks/useSessionManagement.ts` (±30) — replaced inline `setQueryData/invalidateQueries` with factory helpers. Removed `sessionsKey` memo (factory derives key from primitive userId).
- NEW `frontend/src/api/hooks/__tests__/sessions.test.ts` (+130, 11 tests) — queryKey shape + queryOptions baseline + updateSessionInCache (4 cases) + invalidateSessions (2 cases).

Verification: tsc 0, lint 0 (max-warnings=0), vitest **1052p / 12s / 0f** (W134 1041 + 11 new sessions tests). 4 W134 SW1 bridge tests pass unchanged after AbortController removal — bridge contract holds.

### SW2 — Docker chain verification (no commit, curl-only fallback per plan)

Closes W134 §Honesty #1 + #8 partially (chrome-devtools-mcp visual smoke + real Docker chain).

Steps:
1. `start-docker.ps1 -Build` → all containers Up at 105s wall. Frontend healthcheck 14s.
2. Sanity-curl Caddy chain: `curl http://localhost/healthz` → 200/15b ✓ (W131 SW2 fast-path).
3. chrome-devtools-mcp `new_page` /login: page loaded, network log shows `GET /api/v1/users/me [pending]` (Bridge auto-fetch fires through real backend chain).
4. `take_snapshot` + `evaluate_script`: TIMED OUT (Windows + headless Chrome NO_FCP family wall, same as W132 polish round 2 perf APIs). Per plan risk-fallback: documented as deferred + moved on to curl-only.
5. Curl 12 routes through Caddy with byte counts + Server-Timing headers. Verified W131-W134 closures via runtime evidence.

Discovered out-of-W135-scope issues (filed for W136):
- **Gateway+backend JWT protocol mismatch**: `services/gateway/middleware/auth.go:720` checks `claims.IsActive` from JWT, but backend JWT only embeds `sub/aud/iat/nbf/exp/jti`. ALL authed gateway requests → 403 "user account is not active". Backend direct returns 200 with `is_active: true` correctly.
- **`failed_login_attempts.user_id` NOT NULL constraint** rejects rows when login fails for non-existent emails.

Artifacts saved: `/tmp/wave135-sw2-verification.md` (52 lines, full chain proof + 2 discovered issues).

### SW3 — `feat(wave135-sw3-build-orchestrated)` (`d58b5c74b`, 4 files +363/-42)

Retires `wave127-build-x3.sh` Windows watch+kill workaround via integrated `frontend/scripts/build-orchestrated.mjs`. Closes W126 polish #3 at orchestration level.

Files:
- NEW `frontend/scripts/build-orchestrated.mjs` (~280 LoC + ~70 explanatory) — 6-step orchestrator: wasm + sync-tokens + vite build subprocess with kill-after-artifacts + esbuild sw.ts + workbox-build.injectManifest standalone + post-build-shell.mjs.
- `frontend/vite.config.mts` (+14) — `VitePWA({ disable: process.env.BUILD_SKIP_PWA === "true", ... })` env-flag gate. Default no-op (CI Linux + dev mode unaffected).
- `frontend/package.json` (+3/-1) — `build` script switched run-build.mjs → build-orchestrated.mjs; `build:legacy` preserves old script for rollback.
- DELETED `frontend/scripts/wave127-build-x3.sh` (-41).

Empirical findings during execution:
- Programmatic `vite.build()` exits cleanly but does NOT fire tanstackStart's prerender → no `_shell.html` (W128 polish round 2 reproduced).
- Subprocess `vite build` CLI DOES fire prerender + emits all artifacts, AND **STILL hangs** after `[prerender] Prerendered 1 pages: /` even with `BUILD_SKIP_PWA=true`. So vite-plugin-pwa is NOT the sole hang culprit (W126 polish #3's diagnosis was incomplete). A second hang point lives in tanstackStart's plugin chain. **W136 candidate** to investigate.

Pragmatic strategy: kill-after-artifacts pattern in JS — poll for `_shell.html` + `server.js` to be stable for 4 × 500ms ticks (2s debounce), then SIGTERM the vite subprocess. Same pattern as wave127-build-x3.sh, but cross-platform + integrated.

Build × 3 reproducibility (Windows, no watch+kill):
- `index-DqqHVXgy.js` 139,808 × 3 (BYTE-IDENTICAL to W134 baseline `index-AUQP2Hdb.js` 139,808)
- `_shell.html` 65,864 × 3 (BYTE-IDENTICAL)
- `sw.js` 53,181 × 3 (real compiled SW, was 1,872-byte placeholder pre-W135)
- `server.js` 39,373 × 3
- Build duration ~26s × 3 (vs wave127's ~95s × 3)
- Workbox: 209 files / 4.80 MB precached (verified via 209 `"revision":"..."` entries in sw.js)

Verification gate: tsc 0, lint 0, vitest 1052p/12s/0f (preserved from SW1).

### SW4 — `docs(wave135-sw4-audit-handoff)` — this commit

Files:
- NEW `docs/audits/AUDIT_WAVE135.md` (~330 lines)
- NEW `memory/wave135_backlog.md` (this file)
- NEW `memory/wave136_opening_prompt.md`
- `CLAUDE.md` ## Audit Trail W135 row + 3 new W135 gotchas
- `git mv docs/audits/AUDIT_WAVE132.md docs/audits/archive/AUDIT_WAVE132.md` (N+3 rotation)
- `memory/MEMORY.md` updated

## Honest §Honesty caveats

12 items total. 4 CLOSED via SW1+SW2+SW3; 8 REMAIN (3 W135-discovered + 3 carry-forward + 2 by-design / no-deploy).

### CLOSED via implementation

1. ✅ W134 §Honesty #3 (AbortController preservation defensive) — SW1 full removal.
2. ✅ W134 §Honesty #5 (useSessionManagement mutation paths NOT migrated) — SW1 factory exports.
3. ✅ W134 §Honesty #1 / #8 + W131 §Honesty #2 (chrome-devtools-mcp through Docker chain) — SW2 partial closure: Caddy chain + Server-Timing + auth-at-edge proven via curl + chrome-devtools `list_network_requests` succeeded; chrome-devtools `take_snapshot` Windows wall documented as sub-deferral.
4. ✅ W126 polish #3 (vite-plugin-pwa Windows hang) — SW3 orchestration-level closure: wave127-build-x3.sh retired, integrated build-orchestrated.mjs reproducible. Sub-deferral: kill-after-artifacts is improvement NOT structural fix.

### REMAINING — W135-discovered + carry-forward + structural

1. **chrome-devtools-mcp `take_snapshot`/`evaluate_script` Windows wall** — same family as W132 polish round 2 perf APIs. CDP backchannel timeout. W136 candidate.
2. **Gateway+backend JWT protocol mismatch** (W135 SW2 DISCOVERY) — `claims.IsActive` vs JWT payload mismatch. Fix priority: HIGH (ALL authed gateway requests fail). W136 candidate.
3. **`failed_login_attempts.user_id` NOT NULL constraint** (W135 SW2 DISCOVERY) — INSERT fails for non-existent email. W136 candidate.
4. **build-orchestrated.mjs kill-after-artifacts not structural fix** — second hang point in tanstackStart-core not investigated. W136 candidate.
5. **Workbox config drift risk** — hardcoded mirror in build-orchestrated.mjs. W136 candidate (~30min export PWA_INJECT_CONFIG named constant).
6. **W134 §Honesty #2 (bundle delta +259 bytes NOT byte-identical)** — carry-forward honest framing. W135 produces BYTE-IDENTICAL to W134 baseline (neutral net delta).
7. **W134 §Honesty #6 (MEMORY.md `../../../../docs/audits/` paths)** — carry-forward documentation-style. W136 candidate.
8. **W134 §Honesty #10 (/messenger Phase 5 punted)** — no-deploy "production-as-is" decision unchanged.
9. **build-orchestrated.mjs not exhaustively cross-platform tested** — verified Windows only. Linux CI validation = W136 candidate.
10. **SW2 verified 8 SSR routes via curl, not authed browser session** — gateway is_active blocker. Bridge mechanism's "1 vs 2 /users/me" reduction structurally proven via 15 unit tests; runtime observation = W136 once gateway issue closes.
11. **build-orchestrated.mjs not yet validated by CI** — local Windows passes; pushing to CI tests Linux behavior. W136 audit follow-up.
12. **Cross-session vitest 5-run NOT executed** (W134 polish pattern). Recommendation: run at end of W135 polish-pass (~30-90 min "безупречно?" pass).

## W136 candidates

See [`memory/wave136_opening_prompt.md`](wave136_opening_prompt.md) for full list. Highlights:
- **HIGH**: gateway+backend JWT protocol mismatch fix.
- **HIGH**: chrome-devtools-mcp Windows snapshot wall investigation.
- **MEDIUM**: failed_login_attempts schema fix.
- **MEDIUM**: build-orchestrated.mjs structural hang trace.
- **LOW**: Workbox config drift (export PWA_INJECT_CONFIG).
- **HOUSEKEEPING**: MEMORY.md `../../../../` path normalization (carry-forward W134 #6).
- **TIER 4 carry-forward**: test infra (a11y-public WebKit, mobile-webkit /404), LHCI gate ratchet, a11y deep-audit, i18n parity, per-page visual audit, Storybook/Chromatic activation.
- **TIER 5 explicit decision**: /messenger × 2 OR /admin polish arcs.
