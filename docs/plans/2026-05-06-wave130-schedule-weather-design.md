# Wave 130 — /schedule SSR + Weather TanStack Query refactor — Design Doc

**Status**: SHIPPED. Captured post-execution from approved plan + actual implementation.
**Date**: 2026-05-06
**Plan source**: `C:\Users\egorribun\.claude\plans\wave-130-melodic-moth.md` (user-approved via ExitPlanMode + auto mode)
**Related**: `docs/plans/2026-05-01-wave125-ssr-design.md` §3 Phase 5 — this is a continuation

---

## 1. Why Wave 130

W129 closed Phase 5 SSR continuation: /events + /events/$id + /news + /news/$id all SSR-enabled. 5 SSR routes total counting W128 /dashboard. 5 sibling routes still `ssr: false` opt-down (messenger × 2, profile, settings, schedule).

Per `docs/plans/2026-05-01-wave125-ssr-design.md` §3 Phase 5, the natural next step is to enable SSR on /schedule. /schedule is the next-most-trafficked authenticated route after /dashboard + /news + /events.

W129 honest deferral #6 also flagged `useWeather` (dashboard hook, NOT `useMapWeather`) as having a render-time `useMemo` reading `sessionStorage`. While not actually crashing on SSR (typeof window guard returns null), the bespoke fetch + sessionStorage cache + AbortController plumbing diverges from project's TanStack Query convention.

User chose **Option B (combined /schedule SSR + Weather refactor)** + **full TanStack Query migration** for Weather + standard 60-90 min polish budget. Sub-decisions deferred to me: picked partial SSR for /schedule per the recommendation below.

---

## 2. Recommendation on /schedule loader scope

**Recommendation: partial SSR for /schedule** (NOT full SSR with /users/me + lessons sequential prefetch).

### Approach

- Remove `ssr: false` from `routes/_auth/schedule.tsx` → inherits `_auth.tsx ssr: true` (W128 SW2). Schedule.tsx is verified SSR-safe (Explore agent confirmed all browser APIs guarded inside `useEffect`).
- Loader prefetches **only `GET /groups`** (auth-only — no group_id required). Lessons fetch client-side post-hydration once `useScheduleData` auto-selects the user's group from the populated cache.

### Why not full SSR with /users/me + lessons prefetch?

1. **Cookie forwarding risk**: the `@/api/client` axios instance is browser-configured. Calling `/users/me` from server (Node SSR runtime) requires forwarding the incoming `access_token_v2` cookie — currently no such mechanism exists. Adding it is real engineering work that should be scoped as its own concern, not blended into a per-route SSR enablement.

2. **+1 backend round-trip per render**: even if cookie-forwarding were trivial, sequential `/users/me → /schedule/{group_id}` doubles server-side TTFB on the most data-heavy route. Backend latency budget under SSR load is unmeasured.

3. **Matches Phase 3a "lightweight" design**: the W125 SSR design doc explicitly chose Strategy 3a over 3b for "minimal disruption". Server-side cookie-forwarding is structurally Strategy 3b.

4. **Hydration safety**: `useScheduleData`'s auto-select effect (lines 91-105) doesn't run on SSR (effects don't), so server renders empty schedule grid; client hydrates, runs effect, fetches lessons. No hydration mismatch.

5. **Migration path is clear**: if measurement shows lessons-on-hydrate is a real LCP problem, W131+ can add /users/me prefetch with proper cookie-forwarding work as its own focused scope. **Don't combine the two.**

**Tradeoff accepted**: schedule grid paints client-side after JS hydration (~200-500 ms after LCP). Same pattern as W127 SW6 `/map` + `/activity` `'data-only'` annotations (which we're NOT using here because Schedule.tsx is SSR-safe and full SSR of the shell is preferable to data-only).

---

## 3. SW arc

5 SW commits + 1 docs commit. Mirrors W129 SW1-SW6 + SW8 cadence.

### SW1 — Extract schedule queryOptions factories (`6efa841df`)

NEW `frontend/src/api/hooks/schedule.ts` (~95 lines):
- Pure `scheduleGroupsQueryOptions()` factory: queryKey `["schedule", "groups"] as const`, queryFn dynamically calls `api.get("/groups", { signal })`, staleTime 60_000, gcTime 5*60_000, retry 2, retryDelay (FIX-68-05 exponential backoff capped at 10s).
- Pure `pageScheduleQueryOptions(groupId: string | null)` factory: queryKey `["schedule", "group", groupId | "none"]`, enabled `groupId != null`, queryFn returns `[]` if groupId null else fetches `/schedule/{groupId}`.

`useScheduleData.ts` refactored to spread the factories. Public API unchanged. Mirrors W129 events.ts/news.ts placement convention.

### SW2 — /schedule SSR enablement (`94804567a`)

`routes/_auth/schedule.tsx`:
- Removed `ssr: false` opt-down.
- Added `loader: async ({ context }) => Promise.allSettled([context.queryClient.ensureQueryData(scheduleGroupsQueryOptions())])`.

### SW3 — Weather useQuery refactor + factory (`5faa0ef6a`)

NEW `frontend/src/api/hooks/weather.ts` (60 lines):
- `weatherQueryKey(coordinates)` returns 4-tuple `["weather", "snapshot", lat.toFixed(4), lon.toFixed(4)]` (4-decimal precision to dedupe near-equal coordinate sets).
- `weatherQueryOptions(coordinates, cacheTtlMs)`: queryFn delegates to existing `fetchWeatherSnapshot`. `placeholderData` reads sessionStorage cache via `readWeatherCache` for cold-mount fast paint. staleTime defaults to `WEATHER_CACHE_TTL_MS` (10 min); gcTime 30 min; retry 1; refetchOnWindowFocus + refetchOnMount disabled.

`useWeather.ts` refactored 175 → 91 lines (-84):
- Replaced bespoke fetch + sessionStorage cache + AbortController + 4 useState/useEffect calls with single `useQuery(weatherQueryOptions(coordinates, cacheTtlMs))`.
- Public `UseWeatherResult` shape unchanged.

24 new tests added in `ssrFactories.test.ts` (16 → 40).

### SW4 — Verification (no commit + `1879cc474` npm audit fix)

Build × 3 PROD reproducibility + tree-shake invariant + 11-route curl + chrome-devtools-mcp visual smoke on 4 SSR routes (/dashboard + /schedule + /events + /news).

**npm audit regression discovered + fixed**: `ip-address` 10.1.0 → 10.2.0 transitive dev-dep patch bump (XSS in Address6, GHSA-v2v4-37r5-5v8g — recently disclosed CVE).

### SW5 — Audit + memory + N+3 rotation

`docs/audits/AUDIT_WAVE130.md` + `INDEX.md` + this design doc + `CLAUDE.md` (Audit Trail + 4 new gotchas) + `memory/MEMORY.md` + `memory/wave130_backlog.md` + `memory/wave131_opening_prompt.md` + N+3 rotation `git mv docs/audits/AUDIT_WAVE127.md docs/audits/archive/AUDIT_WAVE127.md`.

---

## 4. Verification metrics

- tsc 0 / lint 0 (each SW)
- vitest 983p / 12s / 0f (W129 baseline 959 + 24 new factory tests = 983)
- npm audit 0 vulnerabilities post-fix (W119 SW5 baseline restored)
- Build × 3 reproducible PROD `index-CWTPTT9L.js` 138,974 bytes + `_shell.html` 65,872 bytes
- VITE_LHCI build `index-Bhkc6J1_.js` 137,769 bytes + `_shell.html` 65,954 bytes
- Tree-shake invariant: PROD 0 mock-user references, VITE_LHCI 1
- /schedule curl 70,847 bytes (NEW SSR vs ~10,500 shell pre-W130 = +577% content)
- chrome-devtools-mcp 4 SSR routes: 0 React hydration errors each
- 6 total SSR routes after W130 — W125 Phase 4 deploy infra threshold MET

---

## 5. Honest deferrals to W131+

12 caveats documented in AUDIT_WAVE130.md §Honesty probe. Top:

1. /users/me + /schedule/{group_id} sequential SSR DEFERRED (cookie forwarding own scope per W125 Strategy 3a vs 3b)
2. Weather forceRefresh semantics drift (refresh-button-click returns cached not fresh within 10-min TTL)
3. /schedule lessons paint timing NOT measured (no LHCI baseline pre-vs-post-W130)
4. 5 sibling explicit ssr:false routes preserved (4 of 5 closed via /schedule)

---

## 6. W131 candidates

Per `memory/wave131_opening_prompt.md`. Top:
1. Sequential /users/me + /schedule lessons SSR (~2-3h focused)
2. **Phase 4 deploy infrastructure** — threshold MET (≥6 SSR routes per W125 design). Caddy SSR forwarding + Nitro Node deploy + production SameSite=Lax migration. ~4-6h.
3. /profile or /settings SSR enablement (~1-2h each, design pass)
4. vite-plugin-pwa Windows hang structural fix (~3-5h)
5. LHCI baseline post-W130
6. Weather forceRefresh polish (close W130 §Honesty probe #6)

---

## 7. Sources

- W130 plan file `C:\Users\egorribun\.claude\plans\wave-130-melodic-moth.md`
- W125 SSR design doc `docs/plans/2026-05-01-wave125-ssr-design.md`
- TanStack Start v1 docs queried via Context7 MCP (`/websites/tanstack_start_framework_react`)
- W129 polish lessons (chrome-devtools-mcp `new_page` 30s timeout pattern)
- W128 SW3 SsrRoot per-request QueryClient pattern
- W128 polish #3 stale vite preview port-search trap
