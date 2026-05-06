# Wave 129 — Phase 5 SSR continuation: /news + /events SSR + Linux CI Lighthouse — Design

**Date**: 2026-05-06
**Wave**: 129
**Status**: Approved + executed (8 SWs landed; see `docs/audits/AUDIT_WAVE129.md` for the post-execution narrative).
**Predecessor**: Wave 128 (`docs/audits/AUDIT_WAVE128.md`) — first per-route SSR enable on `/dashboard`.
**Successor**: Wave 130 (per `memory/wave130_opening_prompt.md`).

## Context

Wave 128 closed Phase 5 kickoff: `/dashboard` SSRs **75,086 bytes** (vs W127 10,751-byte shell = +598%) on the W125-W127 foundation (TanStack Start v1, AsyncLocalStorage cookie scheme, AuthProvider Strategy A, SsrRoot per-request QueryClient). 9 sibling routes remained explicit `ssr: false` opt-downs; LHCI numerical Perf/CLS/LCP measurement deferred (Lighthouse + headless Chrome + Windows = NO_FCP across all routes — structural environment limitation, addressed via `lhci-windows-fallback.mjs` workaround on dev machines).

Wave 129 picks up the next 4 highest-value content-heavy routes for per-route SSR enablement: `/events`, `/events/$id`, `/news`, `/news/$id`. Combined with a dedicated on-demand Linux CI Lighthouse workflow (Option C in the plan), this delivers measurable Phase 5 progression + closes the W128 LHCI deferral with honest re-framing.

## Decisions (user-approved)

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Option E = Phase 5 cont (A) + Linux CI Lighthouse (C) combined | Cumulative — A delivers SSR enablement, C delivers measurement infrastructure. Single-session feasible (~7-9h core). |
| prefetchInfiniteQuery scope | First page only (default, no `pages: N`) | ~200-400ms server-time, ~12-20 articles in SSR HTML. Multi-page risks hydration mismatch if user scrolled past + adds 200-400ms per extra page. |
| Per-route enable order | /events first, /news second | events.ts already exports `prefetchEventsListQuery` (W128 events team's proactive SSR prep, lines 261-272) — drop-in 15-min loader integration. /news needs ~45-min factory extraction mirroring same pattern. |
| LHCI Linux CI scope | Minimal — `workflow_dispatch` only, default 9-URL × 3-run sweep with `LHCI_URLS` input for subset | Complements existing `frontend-tests.yml lighthouse:` job (already runs on every PR). New workflow gives on-demand path without 20-min full CI matrix wait. |

## Architecture

### TanStack Start v1 SSR inheritance contract (re-verified W128)

Restriction order: `false > 'data-only' > true`. A child route can ONLY make MORE restrictive — never more permissive. With `_auth.tsx` set to `ssr: true` (W128 SW2), removing the explicit `ssr: false` annotation on a child route lets it inherit `ssr: true` automatically. No need to ADD `ssr: true` explicitly when parent is permissive (redundant + invites silent demotion if parent later changes).

### Per-request QueryClient (W128 SW3)

`__root.tsx` includes a `<SsrRoot />` sub-component that reads `useRouteContext({ from: "__root__" })` for the per-request QueryClient and wraps it in `<QueryClientProvider>`. Loaders MUST use `context.queryClient` (per-request) — NOT the `@/app/queryClient` singleton, which would be invisible to AuthProvider/components at render time.

### Loader pattern (W128 SW3 baseline)

```typescript
loader: async ({ context }) => {
  await Promise.allSettled([
    context.queryClient.prefetchInfiniteQuery(infiniteOpts),  // index routes
    context.queryClient.ensureQueryData(detailOpts),          // detail routes
  ])
}
```

`Promise.allSettled` (NOT `Promise.all`) — best-effort prefetch; backend-down doesn't crash the loader → no NO_FCP (W128 SW3-followup lesson).

### `resolveLoaderLang()` shared helper (W129 SW1, NEW)

Loaders run in BOTH server (SSR / build-time prerender) and client (SPA navigation) contexts. This helper resolves the user's language from the appropriate source per environment:

- SSR path: `globalThis.__ssrLangGetter__` (W127 SW4 — populated from `ue:language` HttpOnly cookie via AsyncLocalStorage)
- Client path: `localStorage.getItem("ue:language")` mirror (W127 SW3 cookie writer)
- Fallback: `"ru"` (per `fallbackLng` in `i18n/metadata.ts` + `ResolvedLang` default in `ssrTheme.ts:resolveLang`)

Single source of truth across all 4 W129 SSR loaders — no duplication.

### Factory extractions (W129 SW2 + SW3 + SW5)

Three pure factories added — all spread into the existing hooks for backward compatibility:

| Factory | File | Used by | Pattern |
|---|---|---|---|
| `prefetchEventsListQuery(qc, filters)` | events.ts:261-272 (pre-existing W128) | SW1 events.index loader | `qc.prefetchInfiniteQuery({ queryKey, queryFn, initialPageParam: null, getNextPageParam: ... })` |
| `eventDetailQueryOptions(id)` | events.ts (W129 SW2 NEW) | SW2 events.$id loader + `useEventDetailQuery` hook | Pure `{ queryKey, queryFn, staleTime, retry }` object — spread by hook + ensureQueryData |
| `prefetchNewsListQuery(qc, filters)` | news.ts (W129 SW3 NEW) | SW4 news.index loader | Mirrors events.ts:261-272 EXACTLY — reuses existing `createNewsListQueryFn` (news.ts:151-180) |
| `newsDetailQueryOptions(id, language)` | news.ts (W129 SW5 NEW) | SW5 news.$id loader + `pages/NewsDetail.tsx` `useQuery` | Pure factory; same queryKey shape `["news", id, language]` as prior inline useQuery (cache identity preserved) |

## SW arc executed (8 SWs, ~7 commits + audit)

See `docs/audits/AUDIT_WAVE129.md §SW arc` for full per-SW narrative + commits.

| SW | Title | SHA | Files | +/- |
|---|---|---|---|---|
| 1 | /events index SSR | `d70ac9ce2` | 2 | +69 / -3 |
| 2 | /events/$id detail SSR + factory | `0a25f82f5` | 2 | +47 / -16 |
| 3 | prefetchNewsListQuery factory | `ade0c4e88` | 1 | +30 / -0 |
| 4 | /news index SSR | `1312c593c` | 1 | +22 / -3 |
| 5 | /news/$id detail SSR + factory + NewsDetail.tsx refactor | `8a1e35113` | 3 | +59 / -16 |
| 6 | Linux CI Lighthouse on-demand workflow | `78b1b5f3d` | 1 | +199 / -0 |
| 7 | Verification (no commit) | — | — | — |
| 8 | Audit + memory + N+3 rotation + this design doc | `<TBD>` | ~9 | TBD |

## Verification

See `docs/audits/AUDIT_WAVE129.md §Verification metrics` for full data + §Honesty probe for ~12 caveats openly disclosed.

Headlines:
- **Build × 3 reproducible PROD**: `index-CT8C_A7Q.js` 138,845 bytes + `_shell.html` 65,778 bytes
- **VITE_LHCI build**: `index-DkB-8HF4.js` 137,640 bytes + `_shell.html` 65,860 bytes
- **Tree-shake invariant verified**: PROD = 0 mock-user references; VITE_LHCI = 1 (useFocusTrap chunk)
- **Curl 9 routes** (VITE_LHCI build): 4 new SSR routes return 200 with 68-90 KB content; /dashboard preserved at 75,290 bytes; /map + /activity + /404 + /login + / preserved
- **chrome-devtools-mcp /events visual smoke**: 0 React hydration errors
- **Gates preserved**: tsc 0, lint 0, vitest **931p / 12s / 0f** (W128 baseline exact), npm audit 0, Cargo.lock no drift

## Next steps (W130 candidates)

Top 8 forward-looking items, see `memory/wave130_opening_prompt.md` for full handoff:

1. /schedule SSR enablement (~1-2h, needs /users/me prefetch for group_id)
2. Weather TanStack Query refactor (~1-2h, would unblock weather SSR safety)
3. vite-plugin-pwa Windows hang structural fix (~3-5h, programmatic vite.build with Vite 8 environments)
4. LHCI baseline post-W129 SSR enablement (trigger lhci-linux.yml; document /events + /news Perf/CLS/LCP delta vs W128)
5. Search filter prefetch for /events + /news loaders (thread validateSearch output)
6. SSR loader test infrastructure
7. Phase 4 deploy infra (Caddy SSR forwarding + production SameSite=Lax migration)
8. chrome-devtools-mcp visual smoke completion on the 3 detail routes
