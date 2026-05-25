# Wave 133 design — Phase 5 SSR continuation: cookie forwarding + /schedule + /profile + /settings

**Date**: 2026-05-08
**Branch**: `egorribun`
**Wave**: 133 (Tier 2 → Option C + D combined)
**Mechanism**: Interceptor + AsyncLocalStorage (user-approved Q3)
**Plan file**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-cheerful-valiant.md`
**Audit**: [`docs/audits/AUDIT_WAVE133.md`](../audits/AUDIT_WAVE133.md)

---

## Context

W125–W131 shipped the TanStack Start v1 SSR migration arc through Phase 4 deploy infrastructure. After W131, **6 SSR routes** were live: /dashboard (W128), /events + /events/$id + /news + /news/$id (W129), /schedule (W130 partial — /groups only, lessons defer to client). W132 shipped Phase 6 canary rollout INFRASTRUCTURE (Caddy lb_policy weighted_round_robin SPA-fallback canary + k8s rolling-update + comprehensive operator runbook) but did NOT enable any new SSR routes.

**The blocker for finishing /schedule SSR + enabling /profile + /settings SSR**: the frontend axios client (`frontend/src/api/client.ts:52-63`) is browser-only (`withCredentials: true`, no Node cookie jar). SSR loaders running in the Node runtime cannot make authenticated `GET /users/me` calls because Node's `http.ClientRequest` doesn't auto-forward the `access_token_v2` HttpOnly cookie. W126 SW3 stashed JWT-validated auth state in `requestAuthStorage` but never exposed the raw `Cookie` header. W130 §Honesty probe #2 explicitly deferred sequential `/users/me + /schedule/{group_id}` SSR for this reason.

**Why now**: the SSR migration arc only delivers user-visible LCP wins on routes that can prefetch their authenticated data server-side. /schedule's lessons are the largest authenticated payload on the page; full SSR completes the W130 partial-SSR design and demonstrates the cookie-forwarding pattern that all future authenticated SSR loaders will reuse. /profile + /settings piggyback on the same infrastructure for almost no marginal cost.

**Intended outcome (post-W133)**:
- Total SSR routes: **6 → 8** (`/schedule` upgraded from partial to full + `/profile` + `/settings` newly enabled).
- Remaining `ssr: false` opt-downs: 4 → 2 (messenger × 2 stay client-only by design — heavy WebSocket + IndexedDB at render time).
- New reusable infrastructure: SSR cookie forwarding + `currentUserQueryOptions()` factory unblocks **any future** authenticated route SSR.
- W130 §Honesty probe #2 closed.

---

## Decision: chosen mechanism (interceptor + AsyncLocalStorage)

User-approved via Q3 of the AskUserQuestion 3-question flow at session start. Mirrors W126 SW3 + W127 SW4 patterns exactly — continuity over novelty for production-critical code.

### Alternatives considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A. Interceptor + AsyncLocalStorage** ✅ | Single axios instance; queryFn unchanged; transparent. Mirrors existing W126/W127 pattern. ALL existing W129 + W130 + W133 SW2 factories work transparently in BOTH SSR loaders + browser useQuery without any branching. | Side-channel coupling; SSR cookie injection happens in interceptor not at queryFn callsite. | **Chosen**. |
| B. Separate `ssrApi` instance + explicit threading | Explicit + auditable. | Two clients to maintain; queryOptions factories need to detect which to use; risk of forgetting an SSR branch in a future factory. | Rejected: too much per-factory maintenance cost. |
| C. queryFn signature receives optional cookie header | Most testable in isolation. | Most invasive; touches every existing factory; breaks the queryOptions factory abstraction. | Rejected: too invasive. |
| D. Use TanStack Start request/headers context API | Would reduce custom infrastructure. | Investigation overhead; upstream API may have changed since W125-W127 design; risks divergence from existing pattern. | Rejected: not worth divergence from established W126 pattern. |

### Architecture summary

**Server side** (`frontend/src/server.ts`):
- New `requestCookieStorage = new AsyncLocalStorage<string>()` (4th storage, parallel to W126/W127 auth/theme/lang).
- New `globalThis.__ssrCookieGetter__: (() => string | undefined) | undefined` (mirrors `__ssrAuthGetter__`).
- Read `request.headers.get("cookie") ?? ""` once at the top of `fetch()`, stash via 4th-level `.run()` in the nesting chain (auth → cookie → theme → lang → handler.fetch).
- Healthz fast path (`/healthz` early-return) preserved, no cookie storage overhead for probes.

**Client side** (`frontend/src/api/client.ts`):
- Augment the existing single request interceptor (line 135-197) with a new SSR cookie-forwarding step that fires ONLY when `typeof window === "undefined"` AND `globalThis.__ssrCookieGetter__?.()?.length > 0`.
- Sets the outgoing request's `Cookie` header from the per-request store via `AxiosHeaders.from(config.headers ?? {}).set("Cookie", cookie)`.
- Browser path provably unaffected: the interceptor branch is gated by `typeof window === "undefined"` which is statically false in the browser bundle. Vite's environments build keeps server-side cookie forwarding logic in the server chunk.
- VITE_LHCI mock adapter at line 65-76 stays — auth bypass continues to short-circuit the entire axios stack on Lighthouse builds.

### `currentUserQueryOptions()` factory

**New `frontend/src/api/hooks/users.ts`** (mirrors W130 SW1 schedule.ts):
- `currentUserQueryKey: readonly ["users", "me"]`
- `currentUserQueryOptions()` returning `{ queryKey, queryFn: ({ signal }) => fetchCurrentUser({ signal }), staleTime: 60_000, gcTime: 5*60_000, networkMode: "online", retry: 2, retryDelay: <exponential capped at 10s> }`.
- `queryFn` delegates to existing `fetchCurrentUser` (`useProfileSync.ts:485-515`) — preserves cache-envelope header logic + retry-on-500-with-cleared-cache. No duplication.
- `useProfileSync` continues to use `fetchCurrentUser` directly for its lifecycle bootstrap (synchronous reads from localStorage envelope + async crypto verify); the factory is purely for SSR loader / future client useQuery consumers.

### Per-route loaders

- **`/schedule`**: phase 1 parallel `[currentUserQueryOptions, scheduleGroupsQueryOptions]` via Promise.allSettled; phase 2 conditional `pageScheduleQueryOptions(user.group_id)` if userResult resolved with string group_id, wrapped in `.catch(() => undefined)` for best-effort behavior.
- **`/profile`**: minimal `Promise.allSettled([currentUserQueryOptions])`. Per-subpage data deferred to W134+.
- **`/settings`**: same minimal loader. Per-subpage data deferred to W134+.

---

## Implementation phases (executed)

| Phase | SW | Commit | Files | Status |
|-------|-----|--------|-------|--------|
| 1 | SW1 | `ec8068453` | server.ts + client.ts + setupTests.ts + ssrCookie.test.ts | ✅ |
| 2 | SW2 | `33f6747a9` | users.ts (NEW) + ssrFactories.test.ts | ✅ |
| 3 | SW3 | `485a212cc` | schedule.tsx route + useScheduleData.cache.test.tsx | ✅ |
| 4 | SW4 | `93f788891` | profile.tsx route | ✅ (combined commit) |
| 5 | SW5 | `93f788891` | settings.tsx route | ✅ (combined commit) |
| 6 | SW6 | (no commit) | build × 3 + curl + chrome-devtools + cross-cutting gates | ✅ |
| 7 | SW7 | (this commit) | audit + memory + N+3 rotation + design doc + handoff | ✅ |

Total wall clock: ~4 h core (SW1 + SW2 + SW3 + SW4-5 + SW6) + ~30 min SW7. Plan estimate was 4–6h core + 60–90 min polish; on-budget.

---

## Verification (post-execution)

| Gate | W132 baseline | W133 SW6 | Delta |
|------|---------------|----------|-------|
| `npm run typecheck` | 0 | 0 | preserved |
| `npm run lint` | 0 warnings | 0 warnings | preserved |
| `npm run test` | 988p / 12s / 0f | **1008p / 12s / 0f** | +20 (10 SW1 + 9 SW2 + 1 SW3) |
| `pytest` (5-file slice) | 78p / 0f | 78p / 0f | preserved (0 backend changes) |
| `npm audit` | 0 vulnerabilities | 0 vulnerabilities | preserved |
| `cargo check` | success + no Cargo.lock drift | success + no drift | idempotent ≥ 23 waves |
| Storybook build | 17.08 s (W131) | 16.91 s | within ±10% noise |
| PROD bundle × 3 | 138,974 b | **139,549 b** | **+575 bytes** (SW1 client-tree weight) |
| VITE_LHCI build × 3 | 137,769 b | **138,344 b** | +575 (consistent with PROD) |
| `_shell.html` (PROD) | 65,872 b | 65,872 b | byte-identical |
| `_shell.html` (VITE_LHCI) | 65,954 b | 65,954 b | byte-identical (≥ 5 waves stable) |
| Tree-shake invariant (PROD) | 0 mock-user | 0 | preserved |
| Tree-shake invariant (VITE_LHCI) | 1 (W116 SW3 useFocusTrap) | 1 | preserved |
| SSR routes | 6 | **8** | +2 (/profile + /settings; /schedule upgraded) |
| `ssr: false` siblings | 4 | **2** (messenger × 2 only) | -2 |
| chrome-devtools-mcp visual smoke (/schedule + /profile + /settings) | n/a | **0 React hydration errors** | clean |

---

## Honest deferrals (12, see audit § Honesty probe)

Pre-emptively listed rather than papered-over. Real tradeoffs:

1. /schedule SSR HTML shrank −55 bytes vs W130 baseline because LHCI mock user has no group_id; lessons phase-2 doesn't fire under bypass. Real users with group_id would see SSR-rendered lessons. Verifying real-user-flow lessons SSR requires Docker chain or augmented mock — W134+ candidate.
2. chrome-devtools-mcp `navigate_page` timed out on /profile + /settings (W129 §Honesty pattern); used `new_page` workaround. SSR HTML rendered cleanly per curl + new_page console smoke.
3. `useProfileSync` NOT migrated to consume `currentUserQueryOptions()` — own-wave refactor of auth bootstrap path. Disjoint cache state risk documented.
4. W128 SW1 `readSsrAuthHint()` interaction with new factory documented; not actionable in W133.
5. HttpOnly cookie security caveat — NEVER log `globalThis.__ssrCookieGetter__()` raw value. Server.ts inline comment + audit doc + new CLAUDE.md gotcha.
6. LHCI numerical baseline post-W133 DEFERRED to Linux CI (W129 SW6 lhci-linux.yml workflow_dispatch). Local Windows + headless Chrome NO_FCP family blocks lighthouse_audit.
7. chrome-devtools-mcp visual smoke through real Docker chain — separate W133+ Option B scope (per W132 closing prompt).
8. `security_cookie_samesite_override` rollback knob (W131 SW6) NOT exercised in prod. W133 doesn't change cookie SameSite contract.
9. Build × 3 reproducibility caveat — `wave127-build-x3.sh` watch+kill workaround still required on Windows (W126 polish #3 vite-plugin-pwa hang).
10. **PROD bundle delta is `+575 bytes`, NOT `byte-identical`** — honest framing per `feedback_perfectionism.md`. SW1 cookie interceptor + globalThis decl in main chunk. NOT a regression.
11. No new SSR routes beyond C+D — messenger × 2 stay `ssr: false` opt-down by design.
12. Storybook NOT explicitly verified for SSR cookie infrastructure interaction. `typeof window` gate makes SSR branch dead-code in browser. Build time 16.91 s within ±10% noise.

---

## Cross-references

- W125 design `docs/plans/2026-05-01-wave125-ssr-design.md` § Phase 5 (per-route enablement strategy 3a vs 3b)
- W130 backlog `memory/wave130_backlog.md` § Honesty probe #2 (this wave closes)
- W126 SW3 audit `docs/audits/AUDIT_WAVE126.md` (jose + JWKS + AsyncLocalStorage pattern this wave extends)
- W128 SW1 audit (readSsrAuthHint pattern; W133 currentUserQueryOptions complements but does not replace)
- `memory/feedback_perfectionism.md` — anticipate "безупречно?" probe at end-of-wave
- `memory/feedback_planning_estimates.md` — range estimates over single numbers; "production-grade polish" anchor 3–5 h base + variance
